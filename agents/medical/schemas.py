"""Structured output models for pharmacy contact lookup."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class PharmacyOption(BaseModel):
    option_id: str
    pharmacy_id: int
    name: str
    city: str
    district: str
    address: str
    rating: float
    phone: str


class MedicalAssessment(BaseModel):
    status: Literal["needs_input", "completed", "failed"]
    stage: Literal["collecting_location", "contacts_ready", "failed"]
    message: str
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    pharmacy_options: list[PharmacyOption] = Field(default_factory=list)
