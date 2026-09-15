# Informacje o zależnościach i licencjach

## NRV2E / UCL

Plik `src/nrv2e.py` zawiera port dekompresora NRV2E opartego na algorytmie
z biblioteki UCL oraz na otwartej implementacji `nrv2e-decompress`.

- UCL: Copyright (C) 1996-2004 Markus Franz Xaver Johannes Oberhumer.
- `nrv2e-decompress`: Copyright (c) 2018-2025 Piotr Roszatycki.
- Licencja wskazana przez oba źródła dla tej implementacji: GPL-2.0.
- Źródło UCL: <https://www.oberhumer.com/opensource/ucl/>
- Źródło implementacji referencyjnej:
  <https://github.com/dex4er/js-nrv2e-decompress>
- Pełny tekst GPL-2.0: <https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt>

Port zmienia język i dodaje ścisłe limity bufora. Nie zmienia to obowiązków
licencyjnych. Przed dystrybucją, połączeniem z aplikacją zamkniętą lub użyciem
komercyjnym trzeba przeprowadzić analizę licencji. Izolacja interfejsu ułatwia
wymianę implementacji, ale sama nie usuwa obowiązków GPL.

## zxing-cpp

`zxing-cpp` jest używany przez zależność Python do wykrywania i odczytu kodu
Aztec. Projekt źródłowy publikuje kod na licencji Apache-2.0:
<https://github.com/zxing-cpp/zxing-cpp>.

## PyMuPDF / MuPDF

`PyMuPDF` renderuje strony PDF lokalnie i wyłącznie w pamięci procesu. Projekt
jest oferowany na warunkach GNU AGPL albo odrębnej licencji komercyjnej Artifex:
<https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright>.

AGPL jest silną licencją copyleft, obejmującą także użycie aplikacji przez sieć.
Przed wdrożeniem zamkniętym, SaaS lub komercyjnym trzeba potwierdzić zgodność
całej aplikacji z AGPL albo uzyskać odpowiednią licencję komercyjną.
