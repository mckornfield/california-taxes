# California Taxes

## Overview
Interactive Plotly charts of California taxes: where state and local revenue comes from, what it is spent on, and how both have changed over time (nominal, inflation-adjusted, per person, share of total). Notebooks are executed with papermill and `scripts/generate_html.py` bundles them into one static `index.html` served by GitHub Pages.

## Architecture
- `src/ca_taxes/`: shared helpers.
  - `io.py`: `RAW`/`PROCESSED` paths, `download`, `record` (writes `data/raw/MANIFEST.csv`), `excel_sheet_to_csv`, `pdf_tables_to_csv`
  - `deflate.py`: `add_views` adds `nominal_b`, `real_b`, `real_pc`; `LAST_ACTUAL_FY`
  - `style.py`: palette, base layout, `stacked_area_toggle`
  - `state.py`, `local.py`: taxonomy crosswalks (LAO and SCO categories to stable groups)
- `scripts/fetch_*.py`: one per source, each writes `data/raw/<source>/*.csv` and logs to the manifest.
- `scripts/convert_to_csv.py`: generic xlsx/pdf to CSV tool.
- `scripts/build_processed.py`: raw to tidy `data/processed/*.csv`, including the DOF Schedule 3 repair of LAO revenue (logged in `revenue_reconciliation.csv`).
- `scripts/generate_html.py`: notebooks to `index.html`.
- Fiscal years are the END year (2015-16 is 2016). Money is $ thousands nominal in processed CSVs.

## Notebook Pipeline
Run in order; each reads `data/processed/`.
1. `01_state_data_overview`, `02_state_revenue`, `03_state_spending`, `04_state_revenue_vs_spending`
2. `05_local_revenue`, `06_local_taxes`, `07_local_spending`, `08_school_districts`, `09_county_maps`
3. `10_tax_burden` (state + city + county + school-district taxes, real per person and as a share of personal income)
4. `11_city_county_explorer` (dropdown per city/county, top/bottom lists)

## Data Sources
| Source | Script | Output |
|---|---|---|
| LAO historical revenues/expenditures (xlsx) | `fetch_lao_state.py` | `data/raw/lao/` |
| DOF Budget Summary Schedule 3 (PDF) | `fetch_dof_schedule3.py` (bump the budget year in the URL when a newer one exists) | `data/raw/dof/` |
| FRED CPIAUCSL, CAPOP, CAOTOT (CA personal income) | `fetch_fred.py` | `data/raw/fred/` |
| State Controller (SCO) cities/counties/special districts, Socrata API | `fetch_sco_local.py` (aggregates server-side) | `data/raw/sco/` |
| Census county FIPS + CA county GeoJSON | `fetch_census_fips.py` | `data/raw/census/` |
| Census school-district finances FY1992-2024 | `fetch_census_schools.py` (~250 MB gitignored cache; keeps CA rows only) | `data/raw/census/schools/` |

Known data issues (also in README):
- LAO revenue taxonomy changes at FY2016-17; LAO 2018-19 rows are misaligned and are repaired from DOF Schedule 3.
- SCO reporting format changes at FY2016-17 (series break drawn on charts).
- SCO excludes K-12 districts and community colleges. K-12 comes from Census (FY1994 omitted, FY2019 charter-school break); community colleges are not covered anywhere. County revenue includes state aid, so do not add state and local revenue totals.
- SCO city populations can be swapped between cities (Mt. Shasta / Mountain View); `repair_city_population` in `build_processed.py` fixes and flags them.
- `.xlsx`/`.xls`/`.pdf` raw files are gitignored; the converted CSVs are committed.

## Running Notebooks
```bash
uv venv && uv pip install -e .
for nb in notebooks/*.ipynb; do
  .venv/bin/python -m papermill $nb $nb -k python3 --cwd notebooks --no-progress-bar
done
```
Plotly renderer is `plotly_mimetype`; the `+notebook` variant bloats the page to ~15 MB.

## Generating the HTML Report
```bash
.venv/bin/python scripts/generate_html.py   # writes ./index.html
python3 -m http.server 8765                  # view locally (browsers block file: URLs for some checks)
```
Sections and notebook order live in `SECTIONS` in `generate_html.py`. Pushing to `main` deploys via `.github/workflows/static.yml` (Pages source: GitHub Actions).

## Environment
- Python >= 3.11, managed with uv (`uv.lock` committed).
- Network is only needed for the `fetch_*` scripts; notebooks and HTML generation work offline from committed CSVs.
- Executing notebooks needs local port binding for the Jupyter kernel (relevant in sandboxes).
