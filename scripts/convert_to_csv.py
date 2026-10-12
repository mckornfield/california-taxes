"""Generic converter for manually downloaded Excel/PDF sources.

  python scripts/convert_to_csv.py book.xlsx                 # every sheet -> book__<sheet>.csv
  python scripts/convert_to_csv.py book.xlsx --sheet Data    # one sheet
  python scripts/convert_to_csv.py report.pdf --pages 12-14  # tables on pages 12-14

Output goes next to the input unless --out-dir is given. Add the source URL to
data/raw/MANIFEST.csv via ca_taxes.io.record when the file is a real source.
"""
import argparse
import re
from pathlib import Path

import pandas as pd

from ca_taxes.io import pdf_tables_to_csv


def page_list(spec):
    pages = []
    for part in (spec or "").split(","):
        if "-" in part:
            a, b = part.split("-")
            pages += range(int(a), int(b) + 1)
        elif part:
            pages.append(int(part))
    return pages or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--sheet")
    ap.add_argument("--pages")
    ap.add_argument("--out-dir", type=Path)
    a = ap.parse_args()
    out = a.out_dir or a.path.parent
    out.mkdir(parents=True, exist_ok=True)
    if a.path.suffix.lower() == ".pdf":
        pdf_tables_to_csv(a.path, out / f"{a.path.stem}.csv", page_list(a.pages))
        return
    sheets = pd.read_excel(a.path, sheet_name=a.sheet or None)
    if a.sheet:
        sheets = {a.sheet: sheets}
    for name, df in sheets.items():
        slug = re.sub(r"\W+", "_", name).strip("_")
        dest = out / f"{a.path.stem}__{slug}.csv"
        df.dropna(how="all").dropna(axis=1, how="all").to_csv(dest, index=False)
        print(f"wrote {dest} ({len(df):,} rows)")


if __name__ == "__main__":
    main()
