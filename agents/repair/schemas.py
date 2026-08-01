"""Repair-domain structured model output."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class PriceEstimate(BaseModel):
    low: int
    high: int
    currency: str = "TWD"
    sample_size: int
    basis: str
    disclaimer: str


class AvailableSlot(BaseModel):
    slot_id: str
    start_at: str


class ProviderOption(BaseModel):
    option_id: str
    provider_id: int
    name: str
    city: str
    district: str
    rating: float
    completed_jobs: int
    base_visit_fee: int
    available_slots: list[AvailableSlot]


class BookingResult(BaseModel):
    booking_code: str
    status: str
    provider_name: str
    scheduled_at: str
    estimate: dict[str, Any] | None = None


class RepairAssessment(BaseModel):
    status: Literal["needs_input", "completed", "failed"]
    stage: Literal["collecting_details", "awaiting_selection", "booked", "failed"]
    message: str
    issue_type: str
    urgency: Literal["low", "normal", "high", "emergency"]
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    ready_for_matching: bool = False
    estimate: PriceEstimate | None = None
    provider_options: list[ProviderOption] = Field(default_factory=list)
    booking: BookingResult | None = None
