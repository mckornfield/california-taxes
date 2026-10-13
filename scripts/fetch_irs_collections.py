"""Federal tax collections in California, from the IRS Data Book (Table 5, 'Gross Collections, by Type of Tax and State').

One workbook per federal fiscal year (Oct-Sep), FY1998-2025:
  https://www.irs.gov/pub/irs-soi/<file>      index page:
  https://www.irs.gov/statistics/soi-tax-stats-gross-collections-by-type-of-tax-and-state-irs-data-book-table-5
Layouts differ across eras, but in every one the first numeric columns are
  total Internal Revenue collections | corporation (business) income tax | individual income and employment taxes (total)
so those three are read from the California and 'United States' rows. Everything else (excise, estate, gift,
other) is total minus those two, so it is derived, not read.

Caveat: IRS attributes collections to where the tax was filed or deposited (a multi-state company's
withholding and corporate tax follow its filing address), so state figures are not the final burden on
residents. A small 'undistributed' amount is not assigned to any state.

Output: data/raw/irs/ca_gross_collections.csv  ($ thousands)  columns fy, total_k, business_income_k, individual_employment_k, us_total_k
"""
import re
from pathlib import Path

import pandas as pd
import requests

from ca_taxes.io import RAW, USER_AGENT, record

BASE = "https://www.irs.gov/pub/irs-soi/"
FILES = {  # fiscal year -> workbook name on irs.gov
    1998: "98db08co.xls", 1999: "99db08co.xls",
    **{y: f"{y % 100:02d}db06co.xls" for y in range(2000, 2006)},
    **{y: f"{y % 100:02d}db05co.xls" for y in range(2006, 2019)},
    **{y: f"{y % 100:02d}dbs01t05co.xlsx" for y in range(2019, 2025)},
    2025: "25db-1-05-co.xlsx",
}
CACHE = RAW / "irs"


def num(v) -> float:
    """Cell to float; some years carry markers like '[r] 2,016,627,269' (revised) or thousands separators."""
    if isinstance(v, str):
        v = re.sub(r"\[[^\]]*\]|[,\s]", "", v)
    return float(v)


def parse(path: Path, fy: int) -> dict:
    x = pd.ExcelFile(path)
    d = x.parse(x.sheet_names[0], header=None)
    title = " ".join(str(v) for v in d.iloc[0].dropna())
    m = re.search(r"Fiscal Year (\d{4})", title) or re.search(r"(\d{4})", title)
    if m and int(m.group(1)) != fy:
        print(f"  note: {path.name} title says {m.group(1)}, expected {fy}")

    def row(label: str) -> list:
        r = d[d[0].astype(str).str.strip().str.startswith(label)].iloc[0]  # first match: some years print two panels side by side
        return [num(v) for v in r.iloc[1:4]]

    ca, us = row("California"), row("United States")
    return dict(fy=fy, total_k=ca[0], business_income_k=ca[1], individual_employment_k=ca[2], us_total_k=us[0])


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for fy, name in FILES.items():
        dest = CACHE / name
        if not dest.exists():
            r = requests.get(BASE + name, headers={"User-Agent": "Mozilla/5.0 " + USER_AGENT}, timeout=120)
            r.raise_for_status()
            dest.write_bytes(r.content)
        rows.append(parse(dest, fy))
    out = pd.DataFrame(rows)
    out_path = CACHE / "ca_gross_collections.csv"
    out.to_csv(out_path, index=False)
    record(out_path, "https://www.irs.gov/statistics/soi-tax-stats-gross-collections-by-type-of-tax-and-state-irs-data-book-table-5",
           "California and US rows of IRS Data Book Table 5, FY1998-2025, $ thousands")
    out["ca_share_pct"] = out.total_k / out.us_total_k * 100
    print(out.assign(total_b=out.total_k / 1e6).round(2)[["fy", "total_b", "ca_share_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
