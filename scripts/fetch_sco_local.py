"""Local-government revenues and expenditures from the State Controller's Office
(bythenumbers.sco.ca.gov, Socrata SoQL API; no key needed).

Datasets (Financial Transactions reports, fiscal years 2002-03 on):
  city / county / special-district  x  revenues / expenditures

The full tables are millions of rows, so we aggregate server-side (SoQL group by)
into two committed CSVs per dataset under data/raw/sco/:
  <name>_statewide.csv   fiscal_year, category, subcategory_1, subcategory_2, value   (sum over all entities)
  <name>_by_entity.csv   entity, fiscal_year, category, value  (+ county/population when available)
  sd_*_by_type.csv       special districts only: by county/district type/activity instead of by district (size)
  city/county_revenues_tax_lines.csv  fiscal_year, category, line_description, value  (tax categories only)
Values are nominal dollars as reported by each government (SCO does not audit them).
Fiscal year is the END year (2024 = FY 2023-24).
"""
import io
import sys

import pandas as pd

from ca_taxes.io import RAW, get_with_retry, record

BASE = "https://bythenumbers.sco.ca.gov/resource"
PAGE = 50000

# name -> (dataset id, column names). Special districts use unseparated column names.
STD = dict(entity="entity_name", year="fiscal_year", value="value")
DATASETS = {
    "city_revenues": ("rrtv-rsj9", STD),
    "city_expenditures": ("ju3w-4gxp", STD),
    "county_revenues": ("emxv-k8xv", {**STD, "value": "values"}),
    "county_expenditures": ("uctr-c2j8", {**STD, "value": "values"}),
    "sd_revenues": ("nkv3-m73r", {**STD, "district_type": "district_type"}),
    "sd_expenditures": ("m9u3-wdam", dict(entity="entityname", year="fiscalyear", value="value",
                                          district_type="districttype2", compact=True)),
}
CATS = ("category", "subcategory_1", "subcategory_2")


def soql(ds_id: str, select: str, group: str, order: str) -> pd.DataFrame:
    frames, offset = [], 0
    while True:
        r = get_with_retry(f"{BASE}/{ds_id}.csv", timeout=300, params={
            "$select": select, "$group": group, "$order": order, "$limit": PAGE, "$offset": offset})
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), dtype=str)
        frames.append(df)
        if len(df) < PAGE:
            return pd.concat(frames, ignore_index=True)
        offset += PAGE


def fetch(name: str, ds_id: str, c: dict) -> None:
    cats = [x.replace("subcategory_", "subcategory") if c.get("compact") else x for x in CATS]
    year, ent, val = c["year"], c["entity"], c["value"]
    out = RAW / "sco"
    out.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/{ds_id}.csv"

    sel = ",".join([year, *cats, f"sum({val}) as value"])
    grp = ",".join([year, *cats])
    df = soql(ds_id, sel, grp, grp)
    df.columns = ["fiscal_year", *CATS, "value"]
    dest = out / f"{name}_statewide.csv"
    df.to_csv(dest, index=False)
    record(dest, url, f"SoQL: select {sel} group by {grp}")
    print(f"{name}_statewide: {len(df):,} rows, fy {df.fiscal_year.min()}-{df.fiscal_year.max()}")

    kind = name.split("_")[0]
    extra = {"city": ["county", "estimated_population"], "county": ["estimated_population"],
             "sd": ["county", c.get("district_type"), "activity"]}[kind]
    # ~200K special districts x years is too big to commit; keep county/type/activity detail instead
    keys = [year, cats[0], *extra] if kind == "sd" else [ent, year, cats[0], *extra]
    sel = ",".join([*keys, f"sum({val}) as value"])
    grp = ",".join(keys)
    df = soql(ds_id, sel, grp, grp)
    df.columns = [*(["fiscal_year", "category"] if kind == "sd" else ["entity", "fiscal_year", "category"]),
                  *[e.replace("districttype2", "district_type") for e in extra], "value"]
    suffix = "by_type" if kind == "sd" else "by_entity"
    dest = out / f"{name}_{suffix}.csv"
    df.to_csv(dest, index=False)
    record(dest, url, f"SoQL: select {sel} group by {grp}")
    print(f"{name}_{suffix}: {len(df):,} rows")


def fetch_tax_lines(name: str, ds_id: str, c: dict) -> None:
    """Statewide tax revenue by line item (property, sales, hotel, utility...).

    Category and subcategory names differ by era but line_description carries the
    tax type, so keep it for tax categories only (cities and counties).
    """
    year, val = c["year"], c["value"]
    where = "lower(category) like '%tax%'"
    sel = f"{year},category,line_description,sum({val}) as value"
    grp = f"{year},category,line_description"
    frames, offset = [], 0
    while True:
        r = get_with_retry(f"{BASE}/{ds_id}.csv", timeout=300, params={
            "$select": sel, "$where": where, "$group": grp, "$order": grp, "$limit": PAGE, "$offset": offset})
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), dtype=str)
        frames.append(df)
        if len(df) < PAGE:
            break
        offset += PAGE
    df = pd.concat(frames, ignore_index=True)
    df.columns = ["fiscal_year", "category", "line_description", "value"]
    dest = RAW / "sco" / f"{name}_tax_lines.csv"
    df.to_csv(dest, index=False)
    record(dest, f"{BASE}/{ds_id}.csv", f"SoQL: select {sel} where {where} group by {grp}")
    print(f"{name}_tax_lines: {len(df):,} rows")


def main():
    only = sys.argv[1:]
    for name, (ds_id, cols) in DATASETS.items():
        if only and name not in only:
            continue
        fetch(name, ds_id, cols)
        if name in ("city_revenues", "county_revenues"):
            fetch_tax_lines(name, ds_id, cols)


if __name__ == "__main__":
    main()
