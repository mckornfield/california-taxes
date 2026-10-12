"""LAO historical state revenues (1950-51 on) and expenditures (1984-85 on).

Source page: https://lao.ca.gov/policyareas/state-budget/historical-data
Writes data/raw/lao/{revenues_archive,revenues,expenditures}.csv (long format,
amounts in $ thousands, fiscal-year labels like '1984-85'). The .xlsx originals
are downloaded to the same dir but are gitignored; the CSVs are committed.
"""
from ca_taxes.io import RAW, download, excel_sheet_to_csv

BASE = "https://lao.ca.gov/sections/state-budget/econ_fiscal"
FILES = {
    "revenues_archive": ("Historical_Revenues_Archive.xlsx", "Pivot Table Raw Data"),
    "revenues": ("Historical_Revenues.xlsx", "Pivot Table Raw Data"),
    "expenditures": ("Historical_Expenditures.xlsx", "Pivot Table Data"),
}


def main():
    out = RAW / "lao"
    for name, (fname, sheet) in FILES.items():
        url = f"{BASE}/{fname}"
        xlsx = download(url, out / fname)
        excel_sheet_to_csv(xlsx, sheet, out / f"{name}.csv", url=url)


if __name__ == "__main__":
    main()
