"""Environment-backed specialist registry."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRegistration:
    name: str
    mode: str
    runtime_arn: str | None
    qualifier: str = "DEFAULT"


def repair_registration() -> AgentRegistration:
    runtime_arn = os.getenv("REPAIR_AGENT_RUNTIME_ARN")
    configured_mode = os.getenv("REPAIR_AGENT_MODE", "auto").lower()
    mode = "agentcore" if configured_mode == "auto" and runtime_arn else configured_mode
    if mode == "auto":
        mode = "fake"
    return AgentRegistration(
        name="repair-agent",
        mode=mode,
        runtime_arn=runtime_arn,
        qualifier=os.getenv("REPAIR_AGENT_QUALIFIER", "DEFAULT"),
    )


def medical_registration() -> AgentRegistration:
    runtime_arn = os.getenv("MEDICAL_AGENT_RUNTIME_ARN")
    configured_mode = os.getenv("MEDICAL_AGENT_MODE", "auto").lower()
    mode = "agentcore" if configured_mode == "auto" and runtime_arn else configured_mode
    if mode == "auto":
        mode = "fake"
    return AgentRegistration(
        name="medical-agent",
        mode=mode,
        runtime_arn=runtime_arn,
        qualifier=os.getenv("MEDICAL_AGENT_QUALIFIER", "DEFAULT"),
    )
