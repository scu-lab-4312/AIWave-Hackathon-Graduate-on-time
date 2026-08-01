"""Versioned contracts shared by the orchestrator and specialist agents."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


CONTRACT_VERSION = "1.0"


class IntentName(str, Enum):
    REPAIR = "repair"
    MEDICAL = "medical"
    PLATFORM_HELP = "platform_help"
    UNSUPPORTED_SERVICE = "unsupported_service"
    UNKNOWN = "unknown"


class RouteAction(str, Enum):
    DISPATCH = "dispatch"
    REPLY = "reply"
    CLARIFY = "clarify"
    CANCEL = "cancel"


class TaskStatus(str, Enum):
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RoutingDecision(BaseModel):
    contract_version: str = CONTRACT_VERSION
    intent: IntentName
    sub_intent: str | None = None
    confidence: float = Field(ge=0, le=1)
    target_agent: str | None = None
    action: RouteAction
    needs_clarification: bool = False
    safety_alert: str | None = None
    reason: str
    sticky_task_id: str | None = None


class ActiveTask(BaseModel):
    contract_version: str = CONTRACT_VERSION
    task_id: str
    target_agent: str = "repair-agent"
    intent: str
    status: TaskStatus = TaskStatus.NEEDS_INPUT
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)


class HandoffRequest(BaseModel):
    """Protocol-neutral request sent from the orchestrator to a specialist."""

    contract_version: str = CONTRACT_VERSION
    task_id: str
    actor_id: str
    conversation_id: str
    intent: str
    message: str
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    safety_alert: str | None = None


class SpecialistResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    task_id: str
    agent: str = "repair-agent"
    status: TaskStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
