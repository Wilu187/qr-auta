# Import danych z polskiego dowodu rejestracyjnego

Działający proof of concept w Pythonie 3.12 i Streamlit. Użytkownik wgrywa
JPG/JPEG/PNG albo PDF dowodu rejestracyjnego, aplikacja odczytuje kod Aztec 2D,
wypełnia edytowalny formularz pojazdu i po zatwierdzeniu pokazuje JSON. Nic nie
trafia do bazy danych.

## Uruchomienie

Wymagany Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

Linux/macOS: aktywacja środowiska to `source .venv/bin/activate`, a kopia
konfiguracji to `cp .env.example .env`.

Testy:

```powershell
pytest
```

Minimalny zestaw komend wymagany do startu:

```text
python -m venv .venv
pip install -r requirements.txt
streamlit run app.py
pytest
```

## Pipeline

1. `image_processing.py` wykrywa rzeczywisty typ pliku i wystawia wspólny
   iterator obrazów. JPG/PNG daje jeden obraz; PDF jest otwierany przez PyMuPDF
   i renderowany kolejno po jednej stronie w 300 DPI, wyłącznie w RAM.
2. Każdy obraz trafia do tego samego `aztec_reader.py`, który przekazuje go do
   `zxing-cpp` z filtrem tylko na format
   Aztec. Próbuje kolejno oryginału, grayscale, zwiększonego kontrastu,
   binaryzacji i powiększenia. Dla dużej strony skanuje też pięć zachodzących
   na siebie regionów; obrót 90/180/270 stopni obsługuje ZXing.
3. Strony PDF są analizowane kolejno. Pierwszy poprawnie zdekodowany Aztec kończy
   iterację i zamyka dokument. Błędny lub obcy Aztec nie blokuje kolejnej strony.
4. `registration_decoder.py` odbiera surowe bajty payloadu, wykonuje ścisłe
   Base64 decode, odczytuje 4-bajtowy rozmiar wyjścia i uruchamia NRV2E.
   Akceptowany jest znany wariant bez paddingu z jednym dodatkowym znakiem
   czytnika oraz identyfikator skanera AIM `]z0` (także spotykane `z0`/`Z0`).
   Obsługiwane są reprezentacje `Barcode.bytes` i `Barcode.text`, Base64/
   Base64URL, pojedyncze opakowanie Base64 oraz surowy wariant binarny.
   Deklarowana długość NRV2E może być nieparzysta: pełny bufor jest wtedy
   rozpakowywany, a UTF-16LE pomija wyłącznie samotny bajt końcowy. Dane nadal
   muszą przejść walidację struktury dowodu.
   Żaden kandydat nie jest akceptowany na podstawie samego nagłówka: musi przejść
   udokumentowane NRV2E-8, ścisłe UTF-16LE i parser rozpoznanego układu dokumentu.
5. Wynik jest dekodowany jako UTF-16LE i dzielony po `|` lub końcach linii.
6. Parser rozpoznaje nowy układ `XXC1` albo starszy układ pozycyjny. Każdy ma
   osobną mapę indeksów. Nieznany znacznik nowego formatu jest odrzucany zamiast
   zgadywania danych.
7. `field_mapper.py` przenosi tylko dane pojazdu do `Vehicle`; formularz
   Streamlit pozostawia każde pole edytowalne.

Publiczna fasada, przeznaczona także do przyszłego użycia w Django:

```python
from src.registration_decoder import decode_registration_certificate

data = decode_registration_certificate(document_bytes)
```

Kod wywołujący nie musi znać sposobu detekcji Aztec, kompresji ani układu pól.

## Struktura

```text
app.py                         UI Streamlit
src/models.py                  modele RegistrationCertificateData i Vehicle
src/image_processing.py        JPG/PNG, render PDF i warianty obrazu
src/aztec_reader.py            detekcja Aztec i surowy payload
src/nrv2e.py                   izolowany dekompresor NRV2E
src/registration_decoder.py   fasada, pipeline i parser formatów
src/field_mapper.py            mapowanie dokumentu na Vehicle
tests/                         testy i wyłącznie syntetyczne dane
.streamlit/config.toml         limit uploadu Streamlit
.env.example                   limity dekodera
```

## Obsługiwane pola

- numer rejestracyjny A;
- data pierwszej rejestracji B;
- marka D.1, typ D.2 i model D.3;
- VIN / numer identyfikacyjny E;
- rok produkcji;
- pojemność P.1, moc P.2 i paliwo P.3;
- liczba miejsc S.1;
- dopuszczalna masa całkowita F.2 i masa własna G.

Brakujące, puste lub oznaczone `---` wartości pozostają puste. Aplikacja nie
wylicza i nie wymyśla danych. Pola C.* właściciela i posiadacza nie są dodawane
do `RegistrationCertificateData` ani `Vehicle`.

## NRV2E i licencja

Do działania offline prototyp zawiera w `src/nrv2e.py` mały port dekompresora
NRV2E. Implementacja bazuje na UCL i referencyjnym projekcie
[`nrv2e-decompress`](https://github.com/dex4er/js-nrv2e-decompress), wskazujących
licencję GPL-2.0. Moduł ma nagłówek SPDX, a pochodzenie opisuje
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

To ważne ograniczenie, nie tylko informacja techniczna. Dystrybucja produktu
z tym modułem może wymagać udostępnienia całości na warunkach GPL-2.0. Przed
użyciem komercyjnym należy zweryfikować licencję z prawnikiem albo podmienić
backend dekodera na implementację lub API z odpowiednią licencją. Osobna fasada
ułatwia taką wymianę, lecz sama izolacja nie znosi obowiązków GPL.

`PyMuPDF`/MuPDF jest udostępniany na warunkach AGPL albo licencji komercyjnej
Artifex. To kolejna zależność copyleft wymagająca analizy przed wdrożeniem
zamkniętym lub sieciowym. `zxing-cpp` jest projektem Apache-2.0. Pozostałe
zależności także mają własne licencje wymagające sprawdzenia przed dystrybucją.

## Prywatność i bezpieczeństwo

- upload i wyrenderowane strony są przetwarzane w RAM; kod nie zapisuje ich do pliku;
- brak bazy i automatycznego zapisu wyniku;
- kod nie loguje payloadu, nazwisk, adresów, PESEL ani danych formularza;
- dozwolone rzeczywiste formaty to JPEG, PNG i PDF, niezależnie od rozszerzenia;
- domyślny limit JPG/PNG: 10 MB; PDF: 15 MB i 10 stron;
- PDF jest renderowany domyślnie w 300 DPI; zakres konfiguracji to 150-400 DPI;
- każda strona i obraz mają limit 25 mln pikseli; minimalny bok obrazu: 200 px;
- deklarowany wynik NRV2E ma limit 64 KiB, z kontrolą offsetów i długości;
- Streamlit ma osobny limit w `.streamlit/config.toml`. Przy zmianie
  `MAX_UPLOAD_MB` lub `MAX_PDF_MB` należy zmienić także `server.maxUploadSize`;
- żadne prawdziwe zdjęcia dokumentów ani prawdziwe dane osobowe nie występują
  w testach.

Wdrożenie sieciowe powinno dodatkowo wymuszać HTTPS, autoryzację, krótką retencję
logów reverse proxy, izolację procesu i politykę usuwania danych z pamięci.

## Obsługa błędów

Kontrolowane wyjątki obejmują zły lub za mały/duży obraz, uszkodzony, szyfrowany,
za duży lub zbyt długi PDF, błąd renderowania strony, brak Aztec, błędny Base64,
błąd NRV2E, zły UTF-16LE i nieobsługiwany format dokumentu. UI pokazuje krótkie
komunikaty bez stack trace. Po znalezieniu Aztec UI potwierdza działanie symbolu
i wskazuje, czy zatrzymał się Base64, nagłówek, NRV2E czy format dokumentu. Nie
wyświetla payloadu. Brak części pól daje ostrzeżenie i pusty, edytowalny formularz.

## Ograniczenia prototypu

- obsługiwany nowy układ jest jawnie ograniczony do rozpoznanego `XXC1`;
- starszy układ jest wykrywany po kompletnej strukturze pozycyjnej;
- nieznane przyszłe wersje wymagają nowej, zweryfikowanej mapy pól;
- skuteczność zależy od ostrości, perspektywy, odblasków i rozmiaru Aztec;
- render PDF używa lokalnego PyMuPDF i nie analizuje warstwy tekstowej dokumentu;
- brak OCR jako fallbacku, zgodnie z założeniem;
- brak walidacji danych z CEPiK, walidacji biznesowej i trwałego zapisu;
- upload całego dokumentu może nadal znajdować się w pamięci procesu Streamlit
  do końca sesji/requestu; prototyp nie gwarantuje kryptograficznego wymazania RAM;
- przed produkcją potrzebne są testy na legalnie pozyskanym, zanonimizowanym
  zbiorze różnych serii i jakości zdjęć.

## Źródła techniczne

- [Python bindings zxing-cpp](https://github.com/zxing-cpp/zxing-cpp/tree/master/wrappers/python)
- [Identyfikatory AIM — Aztec `]z0`](https://docs.zebra.com/us/en/scanners/general/sm72-ig/programming-reference/aim-code-identifiers.html)
- [PyMuPDF](https://pymupdf.readthedocs.io/)
- [UCL](https://www.oberhumer.com/opensource/ucl/)
- [Przykład układu pól polskiego dowodu](https://github.com/icedevml/decode-polish-aztec)
- [Referencyjny parser starego i nowego układu](https://github.com/dex4er/js-polish-vehicle-registration-certificate-decoder)
