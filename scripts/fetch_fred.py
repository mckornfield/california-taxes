"""Deflator and population series from FRED (no key needed for fredgraph.csv).

CPIAUCSL - CPI-U, US city average, monthly, SA (1947+)
CAPOP    - Resident population of California, annual, thousands (1900+)
CAOTOT   - Total personal income in California (BEA), quarterly, $ millions at seasonally adjusted annual rates (1948+)
"""
from ca_taxes.io import RAW, download

SERIES = ["CPIAUCSL", "CAPOP", "CAOTOT"]


def main():
    for s in SERIES:
        download("https://fred.stlouisfed.org/graph/fredgraph.csv", RAW / "fred" / f"{s}.csv",
                 params={"id": s}, note=f"FRED series {s}")


if __name__ == "__main__":
    main()
