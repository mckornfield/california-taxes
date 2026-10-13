"""California property tax assessed values from the Board of Equalization's open data portal.

The portal (https://www.boe.ca.gov/dataportal/) is a JavaScript page over a public OData API:
  https://www.boe.ca.gov/dataportal/api/odata/<ApiCall>        (catalog: .../odata/Catalog)
No key needed. Each dataset is one table with AssessmentYearFrom/To columns: a roll is the Jan 1
lien date of AssessmentYearFrom and funds fiscal year AssessmentYearFrom-AssessmentYearTo.
History is short: county tables start with the 2000-01 roll, the statewide summary with 2009-10,
allocations with 2012-13, secured residential detail with 2015-16.

Output: data/raw/boe/<ApiCall>.csv  (dollar columns are whole dollars as published)
"""
import pandas as pd

from ca_taxes.io import RAW, get_with_retry, record

BASE = "https://www.boe.ca.gov/dataportal/api/odata"
DATASETS = {
    "Assessed_Property_Values": "Table 5: land, improvements, personal property, exemptions, net value by county, 2000-01 on (state + county assessed)",
    "Summaries_of_Assessed_Values_by_Property_Class": "Table 4: statewide values by class, levies, average tax rate, 2009-10 on",
    "Property_Tax_Allocations": "Tables 14/15: levies allocated to city, county, school, other districts by county, 2012-13 on",
    "Gross_Assessed_Values_and_Homeowners_Exemptions": "Table 9: gross value, homeowners' exemptions, by county, 2000-01 on",
    "Secured_Residential_Vacant_Land_Single_Family_Condominiums": "Single-family and condo parcels and values by county, 2015-16 on",
}


def fetch(name: str, note: str) -> None:
    rows, skip, page = [], 0, 2000
    while True:
        r = get_with_retry(f"{BASE}/{name}", params={"$top": page, "$skip": skip}, timeout=120)
        r.raise_for_status()
        chunk = r.json()["value"]
        rows += chunk
        if len(chunk) < page:
            break
        skip += page
    df = pd.DataFrame(rows)
    dest = RAW / "boe" / f"{name}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest, index=False)
    record(dest, f"{BASE}/{name}", note)
    print(f"wrote {dest.relative_to(RAW.parent.parent)} ({len(df):,} rows, rolls {df.AssessmentYearFrom.min()}-{df.AssessmentYearFrom.max()})")


def main():
    for name, note in DATASETS.items():
        fetch(name, note)


if __name__ == "__main__":
    main()
