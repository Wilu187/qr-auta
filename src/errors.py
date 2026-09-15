"""Kontrolowane błędy dekodera bez ujawniania danych i stack trace w UI."""


class RegistrationDecoderError(Exception):
    """Bazowy błąd dekodowania z bezpiecznym komunikatem dla użytkownika."""

    user_message = "Nie udało się odczytać danych z dokumentu."
    aztec_detected = False


class InvalidImageError(RegistrationDecoderError):
    user_message = "Plik nie jest poprawnym obrazem JPG lub PNG."


class UnsupportedDocumentTypeError(RegistrationDecoderError):
    user_message = "Plik nie jest poprawnym JPG, JPEG, PNG ani PDF."


class ImageTooLargeError(RegistrationDecoderError):
    user_message = "Obraz jest za duży. Wybierz plik zgodny z limitem aplikacji."


class ImageTooSmallError(RegistrationDecoderError):
    user_message = "Obraz jest za mały. Zrób wyraźniejsze zdjęcie dokumentu."


class InvalidPdfError(RegistrationDecoderError):
    user_message = "Nie udało się otworzyć PDF. Plik może być uszkodzony lub zabezpieczony."


class PdfTooLargeError(RegistrationDecoderError):
    user_message = "PDF jest za duży. Wybierz plik zgodny z limitem aplikacji."


class PdfPageLimitError(RegistrationDecoderError):
    user_message = "PDF ma za dużo stron. Wybierz krótszy dokument."


class PdfRenderError(RegistrationDecoderError):
    user_message = "Nie udało się przygotować stron PDF do odczytu."


class AztecNotFoundError(RegistrationDecoderError):
    user_message = (
        "Nie udało się odczytać kodu. Spróbuj zrobić zdjęcie dowodu na wprost, "
        "w dobrym świetle i bez odblasków."
    )


class AztecNotFoundInPdfError(AztecNotFoundError):
    user_message = (
        "Nie udało się odczytać kodu Aztec na żadnej stronie PDF. "
        "Użyj wyraźniejszego skanu bez odblasków."
    )


class InvalidPayloadError(RegistrationDecoderError):
    user_message = "Kod Aztec odczytano, ale nagłówek jego danych jest niepoprawny."
    aztec_detected = True


class InvalidBase64Error(InvalidPayloadError):
    user_message = "Kod Aztec odczytano, ale nie zawiera oczekiwanego payloadu Base64."


class PayloadHeaderError(InvalidPayloadError):
    """Nieobsługiwany nagłówek z anonimową metryką do lokalnej diagnozy."""

    def __init__(self, decoded_length: int, declared_size: int) -> None:
        super().__init__("unsupported registration payload header")
        self.diagnostic_code = f"HDR-B{decoded_length}-S{declared_size}"


class DecompressionError(InvalidPayloadError):
    user_message = "Kod znaleziono, ale nie udało się rozpakować jego danych."

    @property
    def diagnostic_code(self) -> str:
        reason = str(self)
        categories = (
            ("unexpected end", "NRV-01"),
            ("control buffer", "NRV-02"),
            ("operation limit", "NRV-03"),
            ("offset", "NRV-04"),
            ("back-reference", "NRV-04"),
            ("stream ended", "NRV-05"),
            ("match length", "NRV-06"),
            ("output", "NRV-07"),
            ("backend", "NRV-08"),
            ("no NRV2E variant", "NRV-09"),
        )
        return next((code for marker, code in categories if marker in reason), "NRV-00")


class UnsupportedFormatError(RegistrationDecoderError):
    user_message = "Ten format dowodu rejestracyjnego nie jest jeszcze obsługiwany."
    aztec_detected = True


class DecoderDependencyError(RegistrationDecoderError):
    user_message = "Brakuje składnika dekodera. Zainstaluj zależności z requirements.txt."
