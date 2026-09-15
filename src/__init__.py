"""Moduły prototypu importu danych z dowodu rejestracyjnego."""

from .models import RegistrationCertificateData, Vehicle
from .registration_decoder import decode_registration_certificate

__all__ = [
    "RegistrationCertificateData",
    "Vehicle",
    "decode_registration_certificate",
]

