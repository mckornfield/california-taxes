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
| K-12 school districts: revenue by source and spending by function, FY1992-2024 (California rows kept) | Census Annual Survey of School System Finances, district-level files | `fetch_census_schools.py` |
| Inflation, CA population, California personal income (quarterly, BEA) | FRED CPIAUCSL, CAPOP, CAOTOT | `fetch_fred.py` |
| County FIPS codes and boundaries | Census reference file, plotly/datasets GeoJSON | `fetch_census_fips.py` |

Excel/PDF sources: `scripts/convert_to_csv.py` converts any workbook or PDF table to CSV, and
`ca_taxes.io` has the same helpers for use inside fetch scripts.

## Data-quality notes
- LAO's revenue file changes taxonomy at 2016-17 (charts mark the break).
- LAO's 2018-19 personal income and sales tax rows are misaligned; they are replaced from DOF Schedule 3. Every
  LAO-vs-Schedule-3 comparison and repair is logged in `data/processed/revenue_reconciliation.csv`.
- SCO changed its local reporting categories in FY2016-17 (charts mark it); SCO data excludes school districts and community colleges; K-12 districts come from Census instead (community colleges are not covered). The SCO's per-entity tables are aggregated by the fetch script (full tables are millions of rows); special districts are kept by county/type/activity rather than by district.
- SCO city populations are sometimes wrong: Mt. Shasta and Mountain View have each other's population in some years. `build_processed.py` flags any city larger than its county, swaps the pair back, and marks the rows `population_repaired`.
- Census school data: FY1994 is omitted (that year's file has only 258 of ~1,080 California districts); FY2019 is a break (over 900 charter schools with non-governmental charters were reclassified out of the surveyed systems); revenue excludes transfers between school systems and spending excludes payments to other school systems, which makes FY2022 match Census' published state table. School state aid is also counted in state spending, so do not add the two.
- Years after FY2025 are budget estimates (shaded). Real dollars use CPI-U (US) with the latest complete FY as base.

## Layout
`src/ca_taxes/` helpers (io, deflate, state crosswalk, plot style) | `scripts/` fetch, build, HTML | `notebooks/` numbered charts |
`data/raw` committed CSVs (original .xlsx/.pdf are gitignored, re-fetchable) | `data/processed` tidy tables
