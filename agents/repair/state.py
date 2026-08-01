"""Repair task state owned by the specialist runtime."""

from typing import Any

from pydantic import BaseModel, Field


class RepairTaskState(BaseModel):
    task_id: str
    issue_type: str | None = None
    urgency: str | None = None
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    selected_provider_id: str | None = None
    service_request_id: str | None = None
