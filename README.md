# California Taxes

Historical California tax revenue and spending (state now, local next), as interactive Plotly charts
published to GitHub Pages from `index.html`. Same pipeline as `california-prop13` and `homelessness-stats`.

## Reproduce everything
```bash
uv venv && uv pip install -e .
# 1. fetch raw data (each script documents its URL; hashes go in data/raw/MANIFEST.csv)
for s in scripts/fetch_*.py; do .venv/bin/python $s; done
# 2. build tidy tables in data/processed/ (also writes revenue_reconciliation.csv)
.venv/bin/python scripts/build_processed.py
# 3. execute notebooks in place, then build the page
for nb in notebooks/0*.ipynb; do .venv/bin/python -m papermill $nb $nb -k python3 --cwd notebooks; done
.venv/bin/python scripts/generate_html.py
```
Output must be written back into the notebook (same path in and out) because `generate_html.py` reads the Plotly JSON from the executed notebooks.

## Data sources
| Data | Source | Script |
|---|---|---|
| State revenue by source, 1950-51 on | LAO Historical Revenues (+ Archive) | `fetch_lao_state.py` |
| State spending by department, 1984-85 on | LAO Historical Expenditures | `fetch_lao_state.py` |
| Tax yield by type, 1970-71 on (cross-check and repair) | DOF Schedule 3 (PDF, parsed) | `fetch_dof_schedule3.py` |
| Inflation, CA population | FRED CPIAUCSL, CAPOP | `fetch_fred.py` |

Excel/PDF sources: `scripts/convert_to_csv.py` converts any workbook or PDF table to CSV, and
`ca_taxes.io` has the same helpers for use inside fetch scripts.

## Data-quality notes
- LAO's revenue file changes taxonomy at 2016-17 (charts mark the break).
- LAO's 2018-19 personal income and sales tax rows are misaligned; they are replaced from DOF Schedule 3. Every
  LAO-vs-Schedule-3 comparison and repair is logged in `data/processed/revenue_reconciliation.csv`.
- Years after FY2025 are budget estimates (shaded). Real dollars use CPI-U (US) with the latest complete FY as base.

## Layout
`src/ca_taxes/` helpers (io, deflate, state crosswalk, plot style) | `scripts/` fetch, build, HTML | `notebooks/` numbered charts |
`data/raw` committed CSVs (original .xlsx/.pdf are gitignored, re-fetchable) | `data/processed` tidy tables
