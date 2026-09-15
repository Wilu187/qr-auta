from src.field_mapper import map_certificate_to_vehicle
from src.models import RegistrationCertificateData


def test_maps_all_vehicle_fields() -> None:
    certificate = RegistrationCertificateData(
        document_format="new:XXC1",
        registration_number="WX 1000",
        first_registration_date="2020-01-02",
        make="TESTMARKA",
        vehicle_type="TYP-X",
        model="MODEL-Y",
        vin="SYNTHETICVIN00001",
        production_year="2020",
        engine_capacity_cm3="1499,00",
        power_kw="88,00",
        fuel_type="P",
        seats="5",
        gross_vehicle_weight_kg="1900",
        curb_weight_kg="1300",
    )

    vehicle = map_certificate_to_vehicle(certificate)

    assert vehicle.to_dict() == {
        "registration_number": "WX 1000",
        "first_registration_date": "2020-01-02",
        "make": "TESTMARKA",
        "vehicle_type": "TYP-X",
        "model": "MODEL-Y",
        "vin": "SYNTHETICVIN00001",
        "production_year": "2020",
        "engine_capacity_cm3": "1499,00",
        "power_kw": "88,00",
        "fuel_type": "P",
        "seats": "5",
        "gross_vehicle_weight_kg": "1900",
        "curb_weight_kg": "1300",
    }


def test_missing_values_become_editable_empty_strings() -> None:
    certificate = RegistrationCertificateData(document_format="new:XXC1")

    vehicle = map_certificate_to_vehicle(certificate)

    assert all(value == "" for value in vehicle.to_dict().values())

