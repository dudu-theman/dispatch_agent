"""Download the Census ZCTA Gazetteer file (ZIP code -> center point).

ZCTAs are the Census Bureau's approximations of ZIP code areas. The Gazetteer
file lists one row per ZCTA with its land area and an interior point
(INTPTLAT, INTPTLONG). load_providers.py loads it into the zip_centroids table.

Usage:
    python3 scripts/get_zip_centroids.py
"""

import argparse
import io
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2026_Gazetteer/2026_Gaz_zcta_national.zip"
)


def main():
    parser = argparse.ArgumentParser(description="Download the Census ZCTA Gazetteer file.")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "raw" / "zcta_gazetteer.txt")
    args = parser.parse_args()

    with urllib.request.urlopen(GAZETTEER_URL) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    (name,) = [n for n in archive.namelist() if n.endswith(".txt")]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(archive.read(name))
    rows = len(args.out.read_text().splitlines()) - 1
    print(f"Wrote {rows} ZCTAs to {args.out}")


if __name__ == "__main__":
    main()
