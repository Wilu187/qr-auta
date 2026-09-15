"""Streamlit UI prototypu. Logika dekodera znajduje się w pakiecie src."""

from __future__ import annotations

import hashlib
from contextlib import closing

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.errors import RegistrationDecoderError  # noqa: E402
from src.field_mapper import map_certificate_to_vehicle  # noqa: E402
from src.image_processing import (  # noqa: E402
    PreparedImage,
    detect_document_type,
    get_processing_limits,
    prepare_document_images,
)
from src.models import Vehicle  # noqa: E402
from src.registration_decoder import decode_registration_certificate  # noqa: E402

FORM_FIELDS = (
    ("registration_number", "Numer rejestracyjny (A)"),
    ("first_registration_date", "Data pierwszej rejestracji (B)"),
    ("make", "Marka (D.1)"),
    ("vehicle_type", "Typ pojazdu (D.2)"),
    ("model", "Model (D.3)"),
    ("vin", "VIN / numer identyfikacyjny (E)"),
    ("production_year", "Rok produkcji"),
    ("engine_capacity_cm3", "Pojemność silnika (P.1) [cm³]"),
    ("power_kw", "Moc (P.2) [kW]"),
    ("fuel_type", "Rodzaj paliwa (P.3)"),
    ("seats", "Liczba miejsc (S.1)"),
    ("gross_vehicle_weight_kg", "Dopuszczalna masa całkowita (F.2) [kg]"),
    ("curb_weight_kg", "Masa własna (G) [kg]"),
)


def _clear_vehicle_state() -> None:
    st.session_state.pop("vehicle_loaded", None)
    st.session_state.pop("missing_fields", None)
    st.session_state.pop("confirmed_vehicle", None)
    for field_name, _label in FORM_FIELDS:
        st.session_state.pop(f"vehicle_{field_name}", None)


def _show_form() -> None:
    missing_fields = st.session_state.get("missing_fields", ())
    st.success("✓ Dane zostały odczytane. Sprawdź je przed zatwierdzeniem.")
    if missing_fields:
        st.warning("Części danych nie było w kodzie. Brakujące pola pozostawiono puste.")

    with st.form("vehicle_form"):
        left, right = st.columns(2)
        for index, (field_name, label) in enumerate(FORM_FIELDS):
            column = left if index % 2 == 0 else right
            with column:
                st.text_input(label, key=f"vehicle_{field_name}")
        submitted = st.form_submit_button("Zatwierdź dane", type="primary")

    if submitted:
        result = Vehicle(
            **{
                field_name: st.session_state.get(f"vehicle_{field_name}", "").strip()
                for field_name, _label in FORM_FIELDS
            }
        )
        st.session_state["confirmed_vehicle"] = result.to_dict()

    confirmed = st.session_state.get("confirmed_vehicle")
    if confirmed:
        st.success("Dane zatwierdzone. Prototyp nie zapisuje ich w bazie.")
        st.json(confirmed)


def _prepare_preview(document_bytes: bytes) -> PreparedImage:
    document_type = detect_document_type(document_bytes)
    prepared_images = prepare_document_images(
        document_bytes,
        detected_type=document_type,
    )
    with closing(prepared_images):
        return next(prepared_images)


def main() -> None:
    st.set_page_config(page_title="Import danych z dowodu rejestracyjnego", page_icon="🚗")
    st.title("Import danych z dowodu rejestracyjnego")
    st.caption("Dodaj pojazd ze zdjęcia lub PDF polskiego dowodu rejestracyjnego.")

    limits = get_processing_limits()

    uploaded = st.file_uploader(
        "Przeciągnij zdjęcie lub PDF dowodu rejestracyjnego",
        type=("jpg", "jpeg", "png", "pdf"),
        help=(
            f"JPG/JPEG/PNG do {limits.max_image_upload_mb} MB; "
            f"PDF do {limits.max_pdf_upload_mb} MB i {limits.max_pdf_pages} stron."
        ),
    )
    if uploaded is None:
        st.info("Dokument jest przetwarzany wyłącznie w pamięci i nie trafia do bazy.")
        return

    image_bytes = uploaded.getvalue()
    digest = hashlib.sha256(image_bytes).hexdigest()
    if st.session_state.get("source_digest") != digest:
        _clear_vehicle_state()
        st.session_state["source_digest"] = digest

    try:
        preview = _prepare_preview(image_bytes)
    except RegistrationDecoderError as exc:
        st.error(exc.user_message)
        return

    preview_caption = "Podgląd dokumentu"
    if preview.source_type == "pdf":
        preview_caption = f"Podgląd strony 1 z {preview.page_count}"
    st.image(preview.image, caption=preview_caption, width="stretch")

    if st.button("Odczytaj dane", type="primary"):
        _clear_vehicle_state()
        with st.spinner("Analizuję dokument i szukam kodu Aztec…"):
            try:
                certificate = decode_registration_certificate(image_bytes)
                vehicle = map_certificate_to_vehicle(certificate)
            except RegistrationDecoderError as exc:
                # getattr chroni także przed częściowym hot-reloadem Streamlit,
                # gdy app.py i moduł z klasami wyjątków mają różne wersje.
                if getattr(exc, "aztec_detected", False):
                    st.success(
                        "✓ Kod Aztec działa: został znaleziony i poprawnie "
                        "odczytany przez skaner."
                    )
                st.error(exc.user_message)
                diagnostic_code = getattr(exc, "diagnostic_code", None)
                if diagnostic_code:
                    st.caption(
                        f"Kod diagnostyczny: {diagnostic_code}. "
                        "Nie zawiera danych dokumentu."
                    )
            except Exception:
                st.error("Nie udało się odczytać danych. Spróbuj użyć wyraźniejszego zdjęcia.")
            else:
                for field_name, value in vehicle.to_dict().items():
                    st.session_state[f"vehicle_{field_name}"] = value
                st.session_state["missing_fields"] = certificate.missing_fields
                st.session_state["vehicle_loaded"] = True

    if st.session_state.get("vehicle_loaded"):
        _show_form()

    st.divider()
    st.caption("Brak trwałego zapisu dokumentu, stron PDF, payloadu i danych. OCR nie jest używany.")


if __name__ == "__main__":
    main()
