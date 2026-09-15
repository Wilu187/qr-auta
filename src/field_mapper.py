"""Mapowanie danych dokumentu na model pojazdu."""

from __future__ import annotations

from .models import RegistrationCertificateData, Vehicle


def map_certificate_to_vehicle(data: RegistrationCertificateData) -> Vehicle:
    """Kopiuje tylko pola pojazdu; brakujące wartości pozostawia puste."""

    return Vehicle(
        registration_number=data.registration_number or "",
        first_registration_date=data.first_registration_date or "",
        make=data.make or "",
        vehicle_type=data.vehicle_type or "",
        model=data.model or "",
        vin=data.vin or "",
        production_year=data.production_year or "",
        engine_capacity_cm3=data.engine_capacity_cm3 or "",
        power_kw=data.power_kw or "",
        fuel_type=data.fuel_type or "",
        seats=data.seats or "",
        gross_vehicle_weight_kg=data.gross_vehicle_weight_kg or "",
        curb_weight_kg=data.curb_weight_kg or "",
    )

