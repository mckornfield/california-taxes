"""DOF Schedule 3, Comparative Yield of State Taxes (general + special funds, 1970-71 on).

An independent cross-check on the LAO revenue series (and a repair source: see
build_processed.py). The PDF is a single page of text; the table is parsed with
pdfplumber's text extraction. Writes data/raw/dof/schedule3_tax_yield.csv in long
form: fy (end year), tax_type, amount_k, estimate.

Update the URL's budget year (2026-27) when a newer Governor's Budget is out.
"""
import re

import pandas as pd
import pdfplumber

from ca_taxes.io import RAW, download, record

URL = "https://ebudget.ca.gov/2026-27/pdf/BudgetSummary/BS_SCH3.pdf"
# column order in the PDF header (left to right) -> our tax_type names
COLUMNS = ["Sales & use tax", "Personal income tax", "Corporation tax", "Tobacco taxes", "Estate & gift tax",
           "Insurance tax", "Alcohol taxes", "Motor fuel taxes", "Vehicle fees", "Cannabis taxes"]
ROW = re.compile(r"^(?P<year>(19|20)\d\d)(?P<est>e/)?\s+(?P<vals>[$\d,\s-]+)$")


def main():
    pdf = download(URL, RAW / "dof" / "BS_SCH3_2026-27.pdf", note="DOF Schedule 3, Comparative Yield of State Taxes")
    with pdfplumber.open(pdf) as doc:
        text = doc.pages[0].extract_text()
    rows = []
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        vals = [int(v.replace("$", "").replace(",", "")) for v in m["vals"].split()]
        # early years predate cannabis tax and have 9 columns
        for col, v in zip(COLUMNS, vals):
            rows.append({"fy": int(m["year"]) + 1, "tax_type": col, "amount_k": v, "estimate": bool(m["est"])})
    df = pd.DataFrame(rows)
    assert df.fy.nunique() >= 55, f"parsed only {df.fy.nunique()} years; PDF layout changed?"
    assert df.groupby("fy").size().isin([9, 10]).all(), "unexpected column count in a row"
    dest = RAW / "dof" / "schedule3_tax_yield.csv"
    df.to_csv(dest, index=False)
    record(dest, URL, "parsed from BS_SCH3_2026-27.pdf (fy = fiscal-year end year)")
    print(f"wrote {dest} ({len(df)} rows, fy {df.fy.min()}-{df.fy.max()})")


if __name__ == "__main__":
    main()
