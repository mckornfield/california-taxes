# California Taxes

Historical California tax revenue and spending, state and local (cities, counties, special districts), as interactive Plotly charts
published to GitHub Pages from `index.html`. Same pipeline as `california-prop13` and `homelessness-stats`.

## Reproduce everything
```bash
uv venv && uv pip install -e .
# 1. fetch raw data (each script documents its URL; hashes go in data/raw/MANIFEST.csv)
#    fetch_census_schools.py downloads ~250 MB into a gitignored cache (data/raw/census/schools/_cache)
for s in scripts/fetch_*.py; do .venv/bin/python $s; done
# 2. build tidy tables in data/processed/ (also writes revenue_reconciliation.csv)
.venv/bin/python scripts/build_processed.py
# 3. execute notebooks in place, then build the page
for nb in notebooks/*.ipynb; do .venv/bin/python -m papermill $nb $nb -k python3 --cwd notebooks; done
.venv/bin/python scripts/generate_html.py
```
Output must be written back into the notebook (same path in and out) because `generate_html.py` reads the Plotly JSON from the executed notebooks.

## Data sources
| Data | Source | Script |
|---|---|---|
| State revenue by source, 1950-51 on | LAO Historical Revenues (+ Archive) | `fetch_lao_state.py` |
| State spending by department, 1984-85 on | LAO Historical Expenditures | `fetch_lao_state.py` |
| Tax yield by type, 1970-71 on (cross-check and repair) | DOF Schedule 3 (PDF, parsed) | `fetch_dof_schedule3.py` |
| Cities, counties, special districts: revenue and spending, FY2002-03 on (aggregated server-side) | State Controller's Office, bythenumbers.sco.ca.gov (Socrata API) | `fetch_sco_local.py` |
| K-12 spending by object (salaries, pensions, benefits, supplies) and function, school years 2003-04 on | California Department of Education, SACS unaudited actuals (statewide totals from the published Access databases) | `fetch_cde_sacs.py` |
| K-12 school districts: revenue by source and spending by function, FY1992-2024 (California rows kept) | Census Annual Survey of School System Finances, district-level files | `fetch_census_schools.py` |
| Property assessed values, levies, tax rates by county (Jan 1 rolls from 2000), allocations (2012 on) | Board of Equalization open-data OData API | `fetch_boe.py` |
| Federal tax collections in California by type, FY1998-2025 | IRS Data Book Table 5 (one workbook per year) | `fetch_irs_collections.py` |
| Government benefits to Californians and federal pay, calendar years | BEA state personal income (SAINC35, SAINC6), bulk download | `fetch_bea.py` |
| Inflation, CA population, California personal income (quarterly, BEA), California house price index (FHFA) | FRED CPIAUCSL, CAPOP, CAOTOT, CASTHPI | `fetch_fred.py` |
| County FIPS codes and boundaries | Census reference file, plotly/datasets GeoJSON | `fetch_census_fips.py` |

Excel/PDF sources: `scripts/convert_to_csv.py` converts any workbook or PDF table to CSV, and
`ca_taxes.io` has the same helpers for use inside fetch scripts.

## Data-quality notes
- LAO's revenue file changes taxonomy at 2016-17 (charts mark the break).
- LAO's 2018-19 personal income and sales tax rows are misaligned; they are replaced from DOF Schedule 3. Every
  LAO-vs-Schedule-3 comparison and repair is logged in `data/processed/revenue_reconciliation.csv`.
- SCO changed its local reporting categories in FY2016-17 (charts mark it); SCO data excludes school districts and community colleges; K-12 districts come from Census instead (community colleges are not covered). The SCO's per-entity tables are aggregated by the fetch script (full tables are millions of rows); special districts are kept by county/type/activity rather than by district.
- SCO city populations are sometimes wrong: Mt. Shasta and Mountain View have each other's population in some years. `build_processed.py` flags any city larger than its county, swaps the pair back, and marks the rows `population_repaired`.
- BOE Table 5 includes a statewide 'Total'/'Totals' row in the 2000-2018 rolls; `build_processed.py` drops it and asserts the county sum matches BOE's statewide summary. BOE publishes only about 25 years of county data online (2000 roll on), 2009 on for statewide levies. BOE's school levies are about 1.7x the K-12 property tax revenue in the Census school data; not reconciled.
- IRS state collections follow where taxes are filed or deposited, not who bears them; FY2023 and FY2024 are distorted by postponed California filing deadlines. The federal 'back in' measures (BEA benefits and pay, federal funds received by governments) omit contracts, most grants and interest, and federal funds received by governments overlap with Medicaid and each other (state federal funds include pass-through to counties and schools), so they are not additive.
- sco.ca.gov's data host (bythenumbers) intermittently serves a wrong TLS certificate; `ca_taxes.io.get_with_retry` retries.
- SACS (K-12 spending detail): CDE publishes Access databases; the fetch script reads them with the pure-Python `access-parser` (slow, about 5 GB RAM per year) and hand-decodes Decimal amounts. Statewide totals include pass-through, internal-service and fiduciary funds and interfund transfers, which `ca_taxes.school` removes (otherwise totals are about 40% too high). Unaudited actuals; charter schools that file only the alternative form are excluded; community colleges are not covered; attendance and enrollment are not used because the LEA tables' scope changes between years.
- Census school data: FY1994 is omitted (that year's file has only 258 of ~1,080 California districts); FY2019 is a break (over 900 charter schools with non-governmental charters were reclassified out of the surveyed systems); revenue excludes transfers between school systems and spending excludes payments to other school systems, which makes FY2022 match Census' published state table. School state aid is also counted in state spending, so do not add the two.
- Years after FY2025 are budget estimates (shaded). Real dollars use CPI-U (US) with the latest complete FY as base.

## Layout
`src/ca_taxes/` helpers (io, deflate, state crosswalk, plot style) | `scripts/` fetch, build, HTML | `notebooks/` numbered charts |
`data/raw` committed CSVs (original .xlsx/.pdf are gitignored, re-fetchable) | `data/processed` tidy tables
