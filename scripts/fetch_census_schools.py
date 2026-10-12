"""California public school-district finances from the Census Annual Survey of School System Finances.

K-12 districts report to the Dept. of Education / Census, not the State Controller, so
this fills the biggest gap in the SCO local-government data. Community colleges are NOT
in this survey.

Source: https://www2.census.gov/programs-surveys/school-finances/tables/<YYYY>/secondary-education-finance/
  elsecYY.txt (district-level CSV, FY1992-2024; the 2022 .txt is truncated, so 2022 uses elsec22.xlsx)
Fiscal year = year the school year ends (FY2022 = 2021-22), matching the rest of the repo.

Downloads go to data/raw/census/schools/_cache (gitignored, ~250 MB); only the California rows
are kept, as data/raw/census/schools/ca_school_districts.csv ($ thousands, one row per district-year).

Item codes (Census school finance): T06 property tax, T99 other taxes, T02 parent-government
contributions, D23 nonschool local government, D11 transfers from other school systems
(excluded from Census' published local total), U11/U22/U30/U50/U97 misc. local revenue,
A07/A08 tuition+transportation, A09 school lunch, A11/A13/A15/A20/A40 other charges.
"""
import sys

import pandas as pd
import requests

from ca_taxes.io import RAW, USER_AGENT, record

BASE = "https://www2.census.gov/programs-surveys/school-finances/tables/{y}/secondary-education-finance/elsec{yy}.{ext}"
CACHE = RAW / "census" / "schools" / "_cache"
OUT = RAW / "census" / "schools" / "ca_school_districts.csv"
YEARS = range(1992, 2025)
KEEP = ["IDCENSUS", "NAME", "CONUM", "V33", "TOTALREV", "TFEDREV", "TSTREV", "TLOCREV",
        "T06", "T99", "T02", "D23", "D11", "A07", "A08", "A09", "A11", "A13", "A15", "A20", "A40",
        "U11", "U22", "U30", "U50", "U97",
        "TOTALEXP", "Q11", "TCURELSC", "TCURINST", "TCURSSVC", "TCUROTH", "NONELSEC", "TCAPOUT",
        "Z32", "Z33"]


def fetch(y: int) -> pd.DataFrame:
    yy = f"{y % 100:02d}"
    ext = "xlsx" if y == 2022 else "txt"  # the 2022 .txt on the server is a truncated 1,729-row file
    url = BASE.format(y=1998 if y == 1999 else y, yy=yy, ext=ext)  # elsec99.txt is filed in the 1998 folder
    dest = CACHE / f"elsec{yy}.{ext}"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=300)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"downloaded {url} ({len(r.content):,} bytes)")
    if ext == "xlsx":
        df = pd.read_excel(dest, dtype={"IDCENSUS": str})
    else:
        # index_col=False: data rows have a trailing comma, which otherwise makes pandas shift every column by one
        df = pd.read_csv(dest, dtype={"STATE": str, "ID": str, "IDCENSUS": str, "FIPST": str}, low_memory=False,
                         encoding="latin-1", index_col=False)
    df.columns = [c.strip() for c in df.columns]
    df = df.copy()  # defragment
    if "ID" in df.columns:  # FY1992-2002 files call it ID
        df = df.rename(columns={"ID": "IDCENSUS"})
    if "IDCENSUS" not in df.columns and "PID6" in df.columns:  # FY2022+ files carry PID6 instead
        df["IDCENSUS"] = df["PID6"].astype(str)
    if "FIPST" in df.columns:  # FIPS state (CA = 6), present in FY2022+
        ca = df[pd.to_numeric(df["FIPST"], errors="coerce") == 6]
    else:  # STATE is Census' own state code (CA = 05)
        ca = df[df["STATE"].str.zfill(2) == "05"]
    missing = [c for c in KEEP if c not in ca.columns]
    if missing:
        print(f"  FY{y}: missing columns {missing}", file=sys.stderr)
    ca = ca[[c for c in KEEP if c in ca.columns]].copy()
    ca.insert(0, "fy", y)
    return ca


def main():
    frames = [fetch(y) for y in YEARS]
    df = pd.concat(frames, ignore_index=True)
    for c in df.columns.difference(["fy", "IDCENSUS", "NAME"]):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    record(OUT, BASE.format(y="<YYYY>", yy="<YY>", ext="txt"), "California rows only; FY1992-2024; $ thousands")
    print(df.groupby("fy").agg(districts=("NAME", "size"), rev_b=("TOTALREV", lambda s: s.sum() / 1e6),
                               prop_b=("T06", lambda s: s.sum() / 1e6)).round(1).to_string())


if __name__ == "__main__":
    main()
