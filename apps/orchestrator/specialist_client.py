"""Select a real AgentCore specialist, with fake as an explicit fallback."""

import os
import logging

from adapters.agentcore_repair import AgentCoreRepairClient
from adapters.fake_repair import FakeRepairClient
from apps.orchestrator.agent_registry import repair_registration
from adapters.base import SpecialistClient
from shared.contracts import HandoffRequest, SpecialistResponse


logger = logging.getLogger("orchestrator.specialist_client")


def build_repair_client() -> SpecialistClient:
    registration = repair_registration()
    if registration.mode == "agentcore":
        if not registration.runtime_arn:
            raise RuntimeError("REPAIR_AGENT_MODE=agentcore requires REPAIR_AGENT_RUNTIME_ARN")
        return AgentCoreRepairClient(
            runtime_arn=registration.runtime_arn,
            region=os.getenv("AWS_REGION", "us-west-2"),
            qualifier=registration.qualifier,
        )
    if registration.mode == "fake":
        return FakeRepairClient()
    raise RuntimeError(f"Unsupported REPAIR_AGENT_MODE: {registration.mode}")


def invoke_repair(request: HandoffRequest) -> tuple[SpecialistResponse, str]:
    """Prefer AgentCore and use fake only when configured or as safe fallback."""
    registration = repair_registration()
    try:
        return build_repair_client().invoke(request), registration.mode
    except Exception:
        fallback_enabled = os.getenv("REPAIR_AGENT_FAKE_FALLBACK", "true").lower() == "true"
        if registration.mode != "agentcore" or not fallback_enabled:
            raise
        logger.exception("AgentCore Repair Agent failed; using non-side-effecting fake fallback")
        return FakeRepairClient().invoke(request), "fake-fallback"
