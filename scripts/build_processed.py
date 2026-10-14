"""Turn data/raw into tidy data/processed CSVs.

  macro.csv               fy, cpi (FY avg, Jul-Jun), cpi_factor (to base-year $), population_k, base_fy, income_m (CA personal income, $M, FY avg)
  state_revenue.csv       (repaired against DOF Sch. 3) fy, fund, category, source, tax_type, group, amount_k, series
  state_expenditures.csv  fy, area (stable), agency, department, fund, exp_type, debt_service, amount_k
  local_revenue.csv       govt (City|County|Special districts), fy, group, amount_k   (statewide)
  local_taxes.csv         govt (City|County), fy, tax_type, amount_k
  local_spending.csv      govt, fy, group, amount_k
  local_sd_activity.csv   kind (revenue|spending), fy, activity, district_type, amount_k
  local_entities.csv      kind (City|County), entity, county, fy, population, revenue_total_k, tax_k, spending_total_k, population_repaired
  school_finance.csv      kind (revenue|spending), fy, group, amount_k   (K-12 districts, Census; FY1994 omitted)
  school_enrollment.csv   fy, enrollment   (fall enrollment, sum of districts)
  sacs_spending.csv       fy, group, category, amount_k   (K-12 spending by object, CDE SACS, FY2004+; see ca_taxes.school)
  sacs_function_group.csv fy, function_group, group, amount_k   (same spending by function x object group)
  highered_expenses.csv   fy, system (UC|CSU|Community colleges), function, amount_k, salaries_k   (IPEDS, FY2004+, FY2005+ for community colleges)
  highered_natural.csv    fy, system, group (Salaries and wages|Fringe benefits|Everything else), amount_k
  highered_revenue.csv    fy, system, source, amount_k
  highered_fte.csv        fy, system, fte, institutions   (12-month full-time-equivalent students, IPEDS)
  boe_assessed.csv        lien_year, county, land_k, improvements_k, personal_k, exemptions_k, net_k   (BOE Table 5, 2000+)
  boe_summary.csv         lien_year, agency, net_k, levies_k, avg_rate_pct   (BOE Table 4, statewide, 2009+)
  boe_allocations.csv     lien_year, county, recipient, amount_k, net_taxable_k   (BOE, 2012+)
  boe_single_family.csv   lien_year, county, parcels, assessed_k   (secured single-family homes, 2015+)
  housing_index.csv       lien_year, hpi   (FHFA California house price index, Q1, 1980Q1=100)
  federal_collections.csv fy, total_k, business_income_k, individual_employment_k, other_k, us_total_k   (IRS, federal FY)
  federal_benefits.csv    year, channel, kind (benefit|pay), federal_only, amount_k   (BEA, calendar year)
  federal_govt_receipts.csv  fy, recipient, amount_k   (federal money received by CA governments; overlaps, not additive)

fy is the fiscal-year END year (2015-16 -> 2016). Amounts are $ thousands, nominal.
Real/per-capita values are derived in notebooks via ca_taxes.deflate.
"""
import pandas as pd

from ca_taxes.io import PROCESSED, RAW
from ca_taxes.highered import FUNCTION_COLUMNS, RESIDUAL, REVENUE_GROUPS
from ca_taxes.local import is_tax_category, revenue_group, spending_group, tax_type
from ca_taxes.school import EXCLUDED_FUNDS, function_group, object_category, object_group
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
    # Personal income: BEA quarterly SAAR; a Jul-Jun fiscal year averages its four quarters (Jul, Oct, Jan, Apr starts)
    inc = pd.read_csv(RAW / "fred" / "CAOTOT.csv", parse_dates=["observation_date"])
    inc["fy"] = inc.observation_date.dt.year + (inc.observation_date.dt.month >= 7)
    ig = inc.groupby("fy").CAOTOT.agg(["mean", "count"])
    out["income_m"] = ig[ig["count"] == 4]["mean"].reindex(out.index)
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
    out = pd.concat(frames)[["kind", "entity", "county", "fy", "population", "revenue_total_k", "tax_k", "spending_total_k"]]
    return repair_city_population(out)


def repair_city_population(df: pd.DataFrame) -> pd.DataFrame:
    """SCO swaps some city populations (Mt. Shasta reports ~80k and Mountain View ~3.3k in the same years).

    A city can't be bigger than its county, so those city-years are flagged. The flagged city's true
    value is interpolated from its own series; if another city that year reports a population within
    15% of that and is abnormally small for itself (<20% of its median), the two values were swapped and are swapped back. Otherwise the interpolation is used.
    Repaired rows are flagged in population_repaired.
    """
    cty = df[df.kind == "County"].set_index(["entity", "fy"]).population.rename("county_pop")
    c = df.join(cty, on=["county", "fy"])
    bad = ((c.kind == "City") & (c.population > c.county_pop)).to_numpy()
    df = df.assign(population_repaired=bad)
    city = df.kind == "City"
    med = df.groupby(["kind", "entity"]).population.transform("median")
    for name in df.loc[df.population_repaired, "entity"].unique():
        m = (df.entity == name) & city
        ser = df.loc[m].set_index("fy")
        interp = ser.population.where(~ser.population_repaired).interpolate(limit_direction="both")
        for fy in ser.index[ser.population_repaired]:
            wrong = ser.population[fy]
            near = ((df.population / interp[fy] - 1).abs() < 0.15) & (df.population < 0.2 * med)  # and abnormally small for itself
            cand = df[city & (df.fy == fy) & (df.entity != name) & near]
            if len(cand) == 1:  # swapped with this city: give it the wrong (large) value back
                k = cand.index[0]
                df.loc[(df.entity == name) & city & (df.fy == fy), "population"] = cand.population.iloc[0]
                df.loc[k, ["population", "population_repaired"]] = [wrong, True]
            else:
                df.loc[(df.entity == name) & city & (df.fy == fy), "population"] = interp[fy]
    print(f"  repaired {int(df.population_repaired.sum())} city-year populations: {sorted(df.loc[df.population_repaired, 'entity'].unique())}")
    return df


def _boe(name: str) -> pd.DataFrame:
    d = pd.read_csv(RAW / "boe" / f"{name}.csv")
    d = d.rename(columns={"AssessmentYearFrom": "lien_year"})
    return d.drop(columns=["AssessmentYearTo"], errors="ignore")


def boe_tables() -> dict[str, pd.DataFrame]:
    """BOE roll tables. Dollars in the source are whole dollars; converted to $ thousands."""
    a = _boe("Assessed_Property_Values")
    a = a[~a.County.str.lower().str.startswith("total")]  # Table 5 carries a statewide "Total"/"Totals" row in 2000-2018; summing it with the counties doubles everything
    assessed = pd.DataFrame({"lien_year": a.lien_year, "county": a.County, "land_k": a.LandAssessedValue / 1e3,
                             "improvements_k": a.ImprovementsAssessedValue / 1e3,
                             "personal_k": a.PersonalPropertyAssessedValue / 1e3,
                             "exemptions_k": a.Exemptions / 1e3, "net_k": a.NetTotal / 1e3})
    t = _boe("Summaries_of_Assessed_Values_by_Property_Class")
    summary = pd.DataFrame({"lien_year": t.lien_year, "agency": t.Agency, "net_k": t.NetOfAllExemptions / 1e3,
                            "levies_k": t.PropertyTaxLevies / 1e3, "avg_rate_pct": t.StateAverageTaxRates})
    chk = assessed.groupby("lien_year").net_k.sum()
    tot = summary[summary.agency.str.startswith("Totals")].set_index("lien_year").net_k  # net of all exemptions; Table 5 is net of 'other' exemptions
    gap = (chk.reindex(tot.index) / tot - 1).abs().max()
    assert assessed.groupby("lien_year").county.nunique().eq(58).all() and gap < 0.02, f"BOE county sums vs statewide summary differ by {gap:.1%}"
    al = _boe("Property_Tax_Allocations")
    rec = {"CityPropertyTaxAllocationsandLevies": "City", "CountyPropertyTaxAllocationsandLevies": "County",
           "SchoolPropertyTaxAllocationsandLevies": "Schools", "OtherDistrictsPropertyTaxAllocationsandLevies": "Other districts"}
    alloc = al.melt(id_vars=["lien_year", "County", "NetTaxableAssessedValue"], value_vars=list(rec), var_name="recipient", value_name="amount_k")
    alloc["recipient"] = alloc.recipient.map(rec)
    alloc["amount_k"] /= 1e3
    alloc = alloc.rename(columns={"County": "county", "NetTaxableAssessedValue": "net_taxable_k"})
    alloc["net_taxable_k"] /= 1e3
    sf = _boe("Secured_Residential_Vacant_Land_Single_Family_Condominiums")
    single = pd.DataFrame({"lien_year": sf.lien_year, "county": sf.County, "parcels": sf.SingleFamilyNumberofParcels,
                           "assessed_k": sf.SingleFamilyAssessedValue / 1e3})
    h = pd.read_csv(RAW / "fred" / "CASTHPI.csv", parse_dates=["observation_date"])
    h = h[h.observation_date.dt.month == 1]  # Q1, closest to the Jan 1 lien date
    housing = pd.DataFrame({"lien_year": h.observation_date.dt.year, "hpi": h.CASTHPI})
    return {"boe_assessed": assessed, "boe_summary": summary, "boe_allocations": alloc, "boe_single_family": single, "housing_index": housing}


def federal_collections() -> pd.DataFrame:
    d = pd.read_csv(RAW / "irs" / "ca_gross_collections.csv")
    d["other_k"] = d.total_k - d.business_income_k - d.individual_employment_k  # excise, estate, gift, other
    return d


BEA_LINES = {  # SAINC35 line code -> (channel, federal program?)
    2110: ("Social Security", True), 2210: ("Medicare", True), 2221: ("Medicaid (federal + state share)", False),
    2310: ("Supplemental Security Income", True), 2330: ("SNAP (food stamps)", True), 2320: ("Earned Income Tax Credit", True),
    2400: ("Unemployment insurance (state + federal)", False), 2500: ("Veterans' benefits", True), 2230: ("Military medical insurance", True),
}


def federal_benefits() -> pd.DataFrame:
    """Government transfers to Californians (BEA SAINC35) and federal pay (SAINC6), calendar years, $ thousands.

    Only programs that are federal by design are flagged federal_only (Social Security, Medicare, SSI, SNAP,
    EITC, veterans, military medical). Medicaid and unemployment insurance are shared with the state;
    'Other government benefits' is the remainder of BEA's transfers from governments and mixes all levels.
    """
    def load(name):
        d = pd.read_csv(RAW / "bea" / f"{name}.csv", encoding="latin-1").dropna(subset=["Description"])
        yrs = [c for c in d.columns if c.isdigit()]
        d = d.melt(id_vars=["LineCode"], value_vars=yrs, var_name="year", value_name="v")
        d["year"] = d.year.astype(int)
        d["v"] = pd.to_numeric(d.v, errors="coerce")
        return d.dropna(subset=["v"])
    t = load("SAINC35_CA")
    t = t[t.LineCode.isin(list(BEA_LINES) + [2000])]
    wide = t.pivot(index="year", columns="LineCode", values="v")
    out = []
    for code, (name, fed) in BEA_LINES.items():
        out.append(wide[code].rename("amount_k").reset_index().assign(channel=name, kind="benefit", federal_only=fed))
    other = (wide[2000] - wide[list(BEA_LINES)].sum(axis=1)).rename("amount_k").reset_index().assign(
        channel="Other government benefits (mixed levels)", kind="benefit", federal_only=False)
    out.append(other)
    n, sic = load("SAINC6N_CA"), load("SAINC6S_CA")
    for code_n, code_s, name in ((2001, 910, "Federal civilian pay"), (2002, 920, "Military pay")):
        a = n[n.LineCode == code_n].set_index("year").v
        b = sic[sic.LineCode == code_s].set_index("year").v
        s_ = pd.concat([b[b.index < a.index.min()], a])  # NAICS series from 1998; SIC before (the two overlap 1998-2001)
        out.append(s_.rename("amount_k").reset_index().assign(channel=name, kind="pay", federal_only=True))
    return pd.concat(out)[["year", "channel", "kind", "federal_only", "amount_k"]].dropna()


def _is_federal(row) -> bool:
    cat, s1, s2 = (str(row.get(c, "")) for c in ("category", "subcategory_1", "subcategory_2"))
    return ("ederal" in s1) or ("ederal" in s2) or cat in ("Aid From Other Governmental Agencies - Federal",
                                                          "Intergovernmental - Federal", "Intergovernmental \u2013 Federal")


def federal_govt_receipts(school_fin: pd.DataFrame) -> pd.DataFrame:
    """Federal money received by each level of California government. NOT additive: state spending of
    federal funds is partly passed through to counties and schools, and counties' federal aid is largely
    administered programs (public assistance, health) that also run through the state."""
    parts = []
    e = pd.read_csv(PROCESSED / "state_expenditures.csv") if (PROCESSED / "state_expenditures.csv").exists() else state_expenditures()
    parts.append(e[e.fund == "Federal Funds"].groupby("fy", as_index=False).amount_k.sum().assign(recipient="State government (federal funds spent)"))
    for k, name in (("county", "Counties"), ("city", "Cities")):
        d = _sco(f"{k}_revenues_statewide")
        d = d[d.apply(_is_federal, axis=1)]
        parts.append(d.groupby("fy", as_index=False).amount_k.sum().assign(recipient=name))
    sc = school_fin[(school_fin.kind == "revenue") & (school_fin.group == "Federal")]
    parts.append(sc.groupby("fy", as_index=False).amount_k.sum().assign(recipient="School districts"))
    return pd.concat(parts)[["fy", "recipient", "amount_k"]]


def sacs_spending() -> tuple[pd.DataFrame, pd.DataFrame]:
    """K-12 spending by object and function from CDE's SACS statewide totals ($ thousands).

    Drops pass-through, internal and fiduciary funds, transfers between agencies and funds, and any
    non-expenditure objects (see ca_taxes.school). Prints the result against Census' school spending as a
    cross-check: Census leaves out debt principal, SACS includes it, so the gap should be small after adding it back.
    """
    d = pd.read_csv(RAW / "cde" / "sacs_state_totals.csv", dtype={"fund": str, "function": str, "object": str})
    d = d[~d.fund.isin(EXCLUDED_FUNDS)]
    d["group"] = d.object.map(object_group)
    d = d.dropna(subset=["group"]).copy()
    d["category"] = d.object.map(object_category)
    d["function_group"] = d.function.map(function_group)
    d["amount_k"] = d.amount / 1e3
    spend = d.groupby(["fy", "group", "category"], as_index=False).amount_k.sum()
    func = d.groupby(["fy", "function_group", "group"], as_index=False).amount_k.sum()
    tot = d.groupby("fy").amount_k.sum()
    principal = d[d.object.isin(["7433", "7439"])].groupby("fy").amount_k.sum()
    cen = pd.read_csv(RAW / "census" / "schools" / "ca_school_districts.csv").groupby("fy")[["TOTALEXP", "Q11"]].sum()
    cen = cen.TOTALEXP - cen.Q11
    chk = pd.DataFrame({"sacs_b": tot / 1e6, "sacs_ex_principal_b": (tot - principal.reindex(tot.index).fillna(0)) / 1e6, "census_b": cen.reindex(tot.index) / 1e6})
    chk["ratio"] = chk.sacs_ex_principal_b / chk.census_b
    print("  SACS vs Census school spending ($B; ratio = SACS excl. principal / Census):")
    print("  " + chk.round(2).to_string().replace("\n", "\n  "))
    return spend, func


PARTIAL_SCHOOL_YEARS = {1994}  # Census' FY1994 file covers only 258 of ~1,080 California districts


def school_finance() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Statewide K-12 district totals from the Census school-finance survey.

    Revenue excludes D11 (transfers between school systems) and spending excludes Q11
    (payments to other school systems), as Census does in its published state tables;
    FY2022 then reproduces Census Table 1 (revenue $116.3B, expenditure $106.9B).
    """
    d = pd.read_csv(RAW / "census" / "schools" / "ca_school_districts.csv")
    d = d[~d.fy.isin(PARTIAL_SCHOOL_YEARS)]
    g = d.drop(columns=["IDCENSUS", "NAME", "CONUM"], errors="ignore").groupby("fy").sum(numeric_only=True)
    rev = pd.DataFrame({
        "Federal": g.TFEDREV,
        "State aid": g.TSTREV,
        "Local property tax": g.T06,
        "Other local taxes": g.T99,
        "Other local revenue": g.TLOCREV - g.D11 - g.T06 - g.T99,
    })
    spend = pd.DataFrame({
        "Instruction": g.TCURINST,
        "Support services": g.TCURSSVC,
        "Other current spending": g.TCUROTH + g.NONELSEC,
        "Capital outlay": g.TCAPOUT,
        "Interest and other": g.TOTALEXP - g.Q11 - g.TCURELSC - g.NONELSEC - g.TCAPOUT,
    })
    for name, t in (("revenue", rev), ("spending", spend)):
        neg = t[(t < 0).any(axis=1)]
        print(f"  school {name}: {len(neg)} years with a negative group", "" if neg.empty else neg.round(0).to_dict("index"))
    long = pd.concat([t.rename_axis("fy").reset_index().melt("fy", var_name="group", value_name="amount_k").assign(kind=k)
                      for k, t in (("revenue", rev), ("spending", spend))])
    enr = g.V33.rename("enrollment").rename_axis("fy").reset_index()
    return long[["kind", "fy", "group", "amount_k"]], enr


def higher_ed() -> dict[str, pd.DataFrame]:
    """UC, CSU and community college spending, revenue and enrollment from IPEDS (see fetch_ipeds.py), $ thousands.

    Community colleges in FY2004: only 77 of about 110 colleges filed the GASB form, so that system-year is dropped.
    """
    d = pd.read_csv(RAW / "ipeds" / "ca_public_higher_ed.csv")
    d = d[~((d.system == "Community colleges") & (d.fy == 2004))]
    d = d[d.F1C191 > 0]  # one filer reports zero/negative totals
    num = d.drop(columns=["institution"]).groupby(["fy", "system"]).sum(numeric_only=True)
    exp = []
    for col, label in FUNCTION_COLUMNS.items():
        sal = num[col[:-1] + "2"] if col[:-1] + "2" in num and col != "F1C081" else 0
        exp.append(pd.DataFrame({"function": label, "amount_k": num[col] / 1e3, "salaries_k": sal / 1e3 if col != "F1C081" else 0}))
    exp = pd.concat(exp).reset_index()
    resid = (num.F1C191 - num[list(FUNCTION_COLUMNS)].sum(axis=1)) / 1e3
    assert (resid > -1).all(), "functions add up to more than total expenses"
    exp = pd.concat([exp, resid.rename("amount_k").reset_index().assign(function=RESIDUAL, salaries_k=0.0)])
    exp = exp[exp.amount_k.abs() > 0.5]
    exp["salaries_k"] = exp.salaries_k.astype(float).fillna(0.0)
    nat = pd.concat([
        (num.F1C192 / 1e3).rename("amount_k").reset_index().assign(group="Salaries and wages"),
        (num.F1C193 / 1e3).rename("amount_k").reset_index().assign(group="Fringe benefits"),
        ((num.F1C191 - num.F1C192 - num.F1C193) / 1e3).rename("amount_k").reset_index().assign(group="Everything else"),
    ])
    rev = pd.concat([
        (num[cols].sum(axis=1) / 1e3).rename("amount_k").reset_index().assign(source=label) for label, cols in REVENUE_GROUPS.items()])
    tot = num[[c for cols in REVENUE_GROUPS.values() for c in cols]].sum(axis=1)
    assert ((tot - num.F1B25).abs() / num.F1B25 < 0.001).all(), "revenue groups do not add up to total revenues"
    fte = num.fte.rename("fte").reset_index().merge(d.groupby(["fy", "system"]).size().rename("institutions").reset_index())
    return {"highered_expenses": exp[["fy", "system", "function", "amount_k", "salaries_k"]], "highered_natural": nat[["fy", "system", "group", "amount_k"]],
            "highered_revenue": rev[["fy", "system", "source", "amount_k"]], "highered_fte": fte}


def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    sf, se = school_finance()
    sp, sfn = sacs_spending()
    state_exp = state_expenditures()
    state_exp.to_csv(PROCESSED / "state_expenditures.csv", index=False)  # federal_govt_receipts reads it
    boe = boe_tables()
    boe = {**boe, **higher_ed()}
    for name, df in [("sacs_spending", sp), ("sacs_function_group", sfn), *boe.items(), ("federal_collections", federal_collections()), ("federal_benefits", federal_benefits()),
                     ("federal_govt_receipts", federal_govt_receipts(sf)),
                     ("school_finance", sf), ("school_enrollment", se), ("macro", macro()), ("local_revenue", local_revenue()), ("local_taxes", local_taxes()),
                     ("local_spending", local_spending()), ("local_sd_activity", local_sd_activity()),
                     ("local_entities", local_entities()), ("state_revenue", repair_with_schedule3(state_revenue())), ("state_expenditures", state_expenditures())]:
        df.to_csv(PROCESSED / f"{name}.csv", index=False)
        print(name, df.shape)


if __name__ == "__main__":
    main()
