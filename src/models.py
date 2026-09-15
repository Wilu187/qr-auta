"""Modele niezależne od Streamlit i sposobu dekodowania dokumentu."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass(slots=True)
class RegistrationCertificateData:
    """Wyłącznie dane dokumentu potrzebne do utworzenia pojazdu.

    Dane właściciela/posiadacza C.* celowo nie występują w modelu.
    """

    document_format: str
    registration_number: str | None = None
    first_registration_date: str | None = None
    make: str | None = None
    vehicle_type: str | None = None
    model: str | None = None
    vin: str | None = None
    production_year: str | None = None
    engine_capacity_cm3: str | None = None
    power_kw: str | None = None
    fuel_type: str | None = None
    seats: str | None = None
    gross_vehicle_weight_kg: str | None = None
    curb_weight_kg: str | None = None
    missing_fields: tuple[str, ...] = ()


@dataclass(slots=True)
class Vehicle:
    """Edytowalny model formularza i wynikowego JSON."""

    registration_number: str = ""
    first_registration_date: str = ""
    make: str = ""
    vehicle_type: str = ""
    model: str = ""
    vin: str = ""
    production_year: str = ""
    engine_capacity_cm3: str = ""
    power_kw: str = ""
    fuel_type: str = ""
    seats: str = ""
    gross_vehicle_weight_kg: str = ""
    curb_weight_kg: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Vehicle:
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: str(value or "") for key, value in data.items() if key in allowed})
