"""Turn data/raw into tidy data/processed CSVs.

  macro.csv               fy, cpi (FY avg, Jul-Jun), cpi_factor (to base-year $), population
  state_revenue.csv       (repaired against DOF Sch. 3) fy, fund, category, source, tax_type, group, amount_k, series
  state_expenditures.csv  fy, area (stable), agency, department, fund, exp_type, debt_service, amount_k
  local_revenue.csv       govt (City|County|Special districts), fy, group, amount_k   (statewide)
  local_taxes.csv         govt (City|County), fy, tax_type, amount_k
  local_spending.csv      govt, fy, group, amount_k
  local_sd_activity.csv   kind (revenue|spending), fy, activity, district_type, amount_k
  local_entities.csv      kind (City|County), entity, county, fy, population, revenue_total_k, tax_k, spending_total_k

fy is the fiscal-year END year (2015-16 -> 2016). Amounts are $ thousands, nominal.
Real/per-capita values are derived in notebooks via ca_taxes.deflate.
"""
import pandas as pd

from ca_taxes.io import PROCESSED, RAW
from ca_taxes.local import is_tax_category, revenue_group, spending_group, tax_type
from ca_taxes.state import classify, spending_area


def fy_end(label: pd.Series) -> pd.Series:
    start = label.str[:4].astype(int)
    return start + 1


def macro() -> pd.DataFrame:
    cpi = pd.read_csv(RAW / "fred" / "CPIAUCSL.csv", parse_dates=["observation_date"])
    cpi["fy"] = cpi.observation_date.dt.year + (cpi.observation_date.dt.month >= 7)
    g = cpi.groupby("fy").CPIAUCSL.agg(["mean", "count"])
    g = g[g["count"] >= 10]  # near-complete FYs (Oct 2025 CPI was never published)
    out = g["mean"].rename("cpi").to_frame()
    base = out.index.max()
    out["cpi_factor"] = out.loc[base, "cpi"] / out["cpi"]
    pop = pd.read_csv(RAW / "fred" / "CAPOP.csv", parse_dates=["observation_date"])
    pop = pop.assign(y=pop.observation_date.dt.year).set_index("y").CAPOP  # thousands
    years = range(int(out.index.min()), int(out.index.max()) + 3)
    pop = pop.reindex(range(min(pop.index), max(years) + 1)).ffill()  # carry last estimate forward
    out = out.reindex(years)
    out["cpi_factor"] = out["cpi_factor"].ffill()  # budget years beyond CPI data: carry base factor
    out["population_k"] = [(pop[y - 1] + pop[y]) / 2 for y in out.index]
    out["base_fy"] = base
    return out.rename_axis("fy").reset_index()


def state_revenue() -> pd.DataFrame:
    a = pd.read_csv(RAW / "lao" / "revenues_archive.csv")[["Category", "Source", "Type of Fund", "Fiscal Year", "Amount"]]
    a["series"] = "archive 1950-2016"
    b = pd.read_csv(RAW / "lao" / "revenues.csv")
    b["series"] = "current 2017-"
    df = pd.concat([a, b]).dropna(subset=["Amount"])
    df["fund"] = df["Type of Fund"].str.replace("Special Funds", "Special Fund")
    df["fy"] = fy_end(df["Fiscal Year"])
    cls = df.apply(lambda r: classify(r.Category, r.Source), axis=1, result_type="expand")
    df["tax_type"], df["group"] = cls[0], cls[1]
    df = df.rename(columns={"Category": "category", "Source": "source", "Amount": "amount_k"})
    return df[["fy", "fund", "category", "source", "tax_type", "group", "amount_k", "series"]]


REPAIR_TOL = 0.05  # replace an LAO tax cell when it differs from DOF Schedule 3 by more than this


def repair_with_schedule3(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-check LAO tax totals (all funds) against DOF Schedule 3; repair big misses.

    LAO's 2018-19 rows are shifted (e.g. General Fund personal income tax is 0 and
    its value sits under 'Retail Sales and Use Tax'). Where LAO disagrees with
    Schedule 3 by more than REPAIR_TOL, drop LAO's rows for that (year, tax) and
    use Schedule 3's total under fund='All funds (DOF Sch. 3)'. Everything compared
    and repaired is logged to data/processed/revenue_reconciliation.csv.
    """
    s3 = pd.read_csv(RAW / "dof" / "schedule3_tax_yield.csv").rename(columns={"amount_k": "s3_k"})
    lao = df[df.group == "Tax"].groupby(["fy", "tax_type"], as_index=False).amount_k.sum().rename(columns={"amount_k": "lao_k"})
    rec = s3.merge(lao, on=["fy", "tax_type"], how="left").fillna({"lao_k": 0})
    rec["ratio"] = rec.lao_k / rec.s3_k.where(rec.s3_k > 0)
    rec["repaired"] = (rec.s3_k > 5e5) & ((rec.ratio - 1).abs() > REPAIR_TOL) & ~rec.estimate
    rec.to_csv(PROCESSED / "revenue_reconciliation.csv", index=False)
    bad = rec[rec.repaired]
    for r in bad.itertuples():
        print(f"  repaired {r.tax_type} FY{r.fy}: LAO {r.lao_k/1e6:.1f}B -> DOF Sch.3 {r.s3_k/1e6:.1f}B")
    keys = set(zip(bad.fy, bad.tax_type))
    keep = df[[(f, t) not in keys or g != "Tax" for f, t, g in zip(df.fy, df.tax_type, df.group)]]
    fix = pd.DataFrame({"fy": bad.fy, "fund": "All funds (DOF Sch. 3)", "category": "Repaired from DOF Schedule 3",
                        "source": bad.tax_type, "tax_type": bad.tax_type, "group": "Tax",
                        "amount_k": bad.s3_k, "series": "repair"})
    return pd.concat([keep, fix], ignore_index=True)


def state_expenditures() -> pd.DataFrame:
    e = pd.read_csv(RAW / "lao" / "expenditures.csv", usecols=range(8), low_memory=False)
    e = e.dropna(subset=["Amount"])
    e = e[e.Amount != 0]
    e["fy"] = fy_end(e["Fiscal Year"])
    e = e.rename(columns={"Department": "department", "Fund": "fund", "DOF Agency": "agency",
                          "Function": "exp_type", "Debt Service?": "debt_service", "Amount": "amount_k"})
    e["area"] = [spending_area(a, d) for a, d in zip(e.agency, e.debt_service)]
    return e[["fy", "area", "agency", "department", "fund", "exp_type", "debt_service", "amount_k"]]


def _sco(name: str) -> pd.DataFrame:
    d = pd.read_csv(RAW / "sco" / f"{name}.csv", dtype={"fiscal_year": int})
    d["amount_k"] = d["value"].astype(float) / 1000
    return d.rename(columns={"fiscal_year": "fy"})


GOVT = {"city": "City", "county": "County", "sd": "Special districts"}


def local_revenue() -> pd.DataFrame:
    out = []
    for k, g in GOVT.items():
        d = _sco(f"{k}_revenues_statewide")
        d["group"] = d.category.map(revenue_group)
        out.append(d.groupby(["fy", "group"], as_index=False).amount_k.sum().assign(govt=g))
    return pd.concat(out)[["govt", "fy", "group", "amount_k"]]


def local_taxes() -> pd.DataFrame:
    out = []
    for k in ("city", "county"):
        d = _sco(f"{k}_revenues_tax_lines")
        d = d[d.category.map(is_tax_category)]
        d["tax_type"] = d.line_description.map(tax_type)
        out.append(d.groupby(["fy", "tax_type"], as_index=False).amount_k.sum().assign(govt=GOVT[k]))
    return pd.concat(out)[["govt", "fy", "tax_type", "amount_k"]]


def local_spending() -> pd.DataFrame:
    out = []
    for k in ("city", "county"):
        d = _sco(f"{k}_expenditures_statewide")
        d["group"] = [spending_group(k, c, s) for c, s in zip(d.category, d.subcategory_1.fillna(""))]
        other = d.loc[d.group == "Other"].groupby("fy").amount_k.sum() / d.groupby("fy").amount_k.sum()
        print(f"  {k} spending left in 'Other': max {other.max():.1%} of a year")
        out.append(d.groupby(["fy", "group"], as_index=False).amount_k.sum().assign(govt=GOVT[k]))
    sd = _sco("sd_expenditures_by_type")
    out.append(sd.groupby("fy", as_index=False).amount_k.sum().assign(govt="Special districts", group="All spending"))
    return pd.concat(out)[["govt", "fy", "group", "amount_k"]]


def local_sd_activity() -> pd.DataFrame:
    out = []
    for kind, name in (("revenue", "sd_revenues_by_type"), ("spending", "sd_expenditures_by_type")):
        d = _sco(name)
        out.append(d.groupby(["fy", "activity", "district_type"], as_index=False).amount_k.sum().assign(kind=kind))
    return pd.concat(out)[["kind", "fy", "activity", "district_type", "amount_k"]]


def local_entities() -> pd.DataFrame:
    frames = []
    for k in ("city", "county"):
        rev = _sco(f"{k}_revenues_by_entity")
        rev["is_tax"] = rev.category.map(is_tax_category)
        rev["is_internal"] = rev.category.str.contains("Internal Service", case=False)
        spend = _sco(f"{k}_expenditures_by_entity")
        spend["is_internal"] = spend.category.str.contains("Internal Service", case=False)
        keys = ["entity", "fy"]
        r = rev[~rev.is_internal].groupby(keys).amount_k.sum().rename("revenue_total_k").to_frame()
        r["tax_k"] = rev[rev.is_tax].groupby(keys).amount_k.sum()
        r["spending_total_k"] = spend[~spend.is_internal].groupby(keys).amount_k.sum()
        pop = rev.assign(p=pd.to_numeric(rev.estimated_population, errors="coerce")).groupby(keys).p.max()
        r["population"] = pop
        if "county" in rev.columns:
            r["county"] = rev.dropna(subset=["county"]).groupby(keys).county.first()
        else:
            r["county"] = r.index.get_level_values("entity")
        frames.append(r.reset_index().assign(kind=k.title()))
    return pd.concat(frames)[["kind", "entity", "county", "fy", "population", "revenue_total_k", "tax_k", "spending_total_k"]]


def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    for name, df in [("macro", macro()), ("local_revenue", local_revenue()), ("local_taxes", local_taxes()),
                     ("local_spending", local_spending()), ("local_sd_activity", local_sd_activity()),
                     ("local_entities", local_entities()), ("state_revenue", repair_with_schedule3(state_revenue())), ("state_expenditures", state_expenditures())]:
        df.to_csv(PROCESSED / f"{name}.csv", index=False)
        print(name, df.shape)


if __name__ == "__main__":
    main()
