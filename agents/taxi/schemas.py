"""Structured output models for Taxi matching and booking."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TaxiSlot(BaseModel):
    slot_id: str
    start_at: str


class DriverOption(BaseModel):
    option_id: str
    driver_id: int
    fleet_name: str
    driver_name: str
    vehicle_reg_number: str
    city: str
    phone: str
    rating: float
    description: str | None = None
    available_slots: list[TaxiSlot]


class TaxiBookingResult(BaseModel):
    booking_code: str
    status: str
    driver_name: str
    driver_phone: str
    fleet_name: str
    vehicle_reg_number: str
    scheduled_at: str
    pickup_city: str
    pickup_district: str
    destination: str
    special_needs: str


class TaxiAssessment(BaseModel):
    status: Literal["needs_input", "completed", "failed"]
    stage: Literal["collecting_trip", "awaiting_selection", "booked", "failed"]
    message: str
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    driver_options: list[DriverOption] = Field(default_factory=list)
    booking: TaxiBookingResult | None = None
