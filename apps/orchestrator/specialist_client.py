"""Select a real AgentCore specialist, with fake as an explicit fallback."""

import os
import logging

from adapters.agentcore_repair import AgentCoreRepairClient
from adapters.agentcore_medical import AgentCoreMedicalClient
from adapters.agentcore_taxi import AgentCoreTaxiClient
from adapters.fake_medical import FakeMedicalClient
from adapters.fake_repair import FakeRepairClient
from adapters.fake_taxi import FakeTaxiClient
from apps.orchestrator.agent_registry import medical_registration, repair_registration, taxi_registration
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


def build_medical_client() -> SpecialistClient:
    registration = medical_registration()
    if registration.mode == "agentcore":
        if not registration.runtime_arn:
            raise RuntimeError("MEDICAL_AGENT_MODE=agentcore requires MEDICAL_AGENT_RUNTIME_ARN")
        return AgentCoreMedicalClient(
            runtime_arn=registration.runtime_arn,
            region=os.getenv("AWS_REGION", "us-west-2"),
            qualifier=registration.qualifier,
        )
    if registration.mode == "fake":
        return FakeMedicalClient()
    raise RuntimeError(f"Unsupported MEDICAL_AGENT_MODE: {registration.mode}")


def invoke_medical(request: HandoffRequest) -> tuple[SpecialistResponse, str]:
    registration = medical_registration()
    try:
        return build_medical_client().invoke(request), registration.mode
    except Exception:
        fallback_enabled = os.getenv("MEDICAL_AGENT_FAKE_FALLBACK", "true").lower() == "true"
        if registration.mode != "agentcore" or not fallback_enabled:
            raise
        logger.exception("AgentCore Medical Agent failed; using non-side-effecting fake fallback")
        return FakeMedicalClient().invoke(request), "fake-fallback"


def build_taxi_client() -> SpecialistClient:
    registration = taxi_registration()
    if registration.mode == "agentcore":
        if not registration.runtime_arn:
            raise RuntimeError("TAXI_AGENT_MODE=agentcore requires TAXI_AGENT_RUNTIME_ARN")
        return AgentCoreTaxiClient(
            runtime_arn=registration.runtime_arn,
            region=os.getenv("AWS_REGION", "us-west-2"),
            qualifier=registration.qualifier,
        )
    if registration.mode == "fake":
        return FakeTaxiClient()
    raise RuntimeError(f"Unsupported TAXI_AGENT_MODE: {registration.mode}")


def invoke_taxi(request: HandoffRequest) -> tuple[SpecialistResponse, str]:
    registration = taxi_registration()
    try:
        return build_taxi_client().invoke(request), registration.mode
    except Exception:
        fallback_enabled = os.getenv("TAXI_AGENT_FAKE_FALLBACK", "true").lower() == "true"
        if registration.mode != "agentcore" or not fallback_enabled:
            raise
        logger.exception("AgentCore Taxi Agent failed; using non-side-effecting fake fallback")
        return FakeTaxiClient().invoke(request), "fake-fallback"


def invoke_specialist(
    target_agent: str,
    request: HandoffRequest,
    *,
    force_fake: bool = False,
) -> tuple[SpecialistResponse, str]:
    if force_fake:
        fake_clients: dict[str, SpecialistClient] = {
            "taxi-agent": FakeTaxiClient(),
            "medical-agent": FakeMedicalClient(),
            "repair-agent": FakeRepairClient(),
        }
        client = fake_clients.get(target_agent)
        if not client:
            raise RuntimeError(f"Unsupported specialist target: {target_agent}")
        return client.invoke(request), "fake"
    if target_agent == "taxi-agent":
        return invoke_taxi(request)
    if target_agent == "medical-agent":
        return invoke_medical(request)
    if target_agent == "repair-agent":
        return invoke_repair(request)
    raise RuntimeError(f"Unsupported specialist target: {target_agent}")
