"""Download and table-conversion helpers shared by the fetch scripts."""
from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MANIFEST = RAW / "MANIFEST.csv"
USER_AGENT = "california-taxes/0.1 (research; github.com/mckornfield/california-taxes)"


def record(dest: Path, url: str, note: str = "") -> None:
    """Upsert a manifest row (url, retrieval date, sha256, size) for dest."""
    rel = str(dest.relative_to(ROOT))
    rows = []
    if MANIFEST.exists():
        with MANIFEST.open(newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["file"] != rel]
    rows.append({
        "file": rel,
        "url": url,
        "retrieved": date.today().isoformat(),
        "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "bytes": dest.stat().st_size,
        "note": note,
    })
    rows.sort(key=lambda r: r["file"])
    with MANIFEST.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "url", "retrieved", "sha256", "bytes", "note"])
        w.writeheader()
        w.writerows(rows)


def download(url: str, dest: Path, note: str = "", params: dict | None = None) -> Path:
    """Download url to dest and record it in the manifest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=180)
    r.raise_for_status()
    dest.write_bytes(r.content)
    record(dest, r.url, note)
    print(f"downloaded {dest.relative_to(ROOT)} ({len(r.content):,} bytes)")
    return dest


def excel_sheet_to_csv(xlsx: Path, sheet: str, dest: Path, url: str = "", note: str = "", **kw) -> pd.DataFrame:
    """Write one worksheet to CSV (drops fully-empty rows/cols) and record it."""
    df = pd.read_excel(xlsx, sheet_name=sheet, **kw).dropna(how="all").dropna(axis=1, how="all")
    df.to_csv(dest, index=False)
    record(dest, url or str(xlsx.name), note or f"sheet '{sheet}' of {xlsx.name}")
    print(f"wrote {dest.relative_to(ROOT)} ({len(df):,} rows)")
    return df


def pdf_tables_to_csv(pdf: Path, dest: Path, pages: list[int] | None = None) -> pd.DataFrame:
    """Extract every table on the given (1-indexed) pages of a PDF into one CSV.

    Output columns: page, table, row, then c0..cN. Rows are raw strings; cleaning
    (header rows, footnotes, number parsing) is source-specific and belongs in
    the caller. Always eyeball the result against the PDF.
    """
    import pdfplumber

    out = []
    with pdfplumber.open(pdf) as doc:
        for pno, page in enumerate(doc.pages, start=1):
            if pages and pno not in pages:
                continue
            for tno, table in enumerate(page.extract_tables()):
                for rno, row in enumerate(table):
                    out.append({"page": pno, "table": tno, "row": rno,
                                **{f"c{i}": v for i, v in enumerate(row)}})
    df = pd.DataFrame(out)
    df.to_csv(dest, index=False)
    print(f"wrote {dest} ({len(df):,} rows)")
    return df
