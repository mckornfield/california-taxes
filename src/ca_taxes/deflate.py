"""Real-dollar and per-capita adjustment using data/processed/macro.csv."""
import pandas as pd

from .io import PROCESSED

# LAO's state files run through the 2025-26 Budget Act and 2026-27 proposals.
# Years after this are estimates/proposals, not closed books.
LAST_ACTUAL_FY = 2025


def macro() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "macro.csv").set_index("fy")


def base_fy() -> int:
    return int(macro().base_fy.iloc[0])


def add_views(df: pd.DataFrame, value: str = "amount_k") -> pd.DataFrame:
    """Add nominal_b, real_b ($ billions, base-FY dollars) and real_pc ($ per resident)."""
    m = macro()
    out = df.copy()
    out["nominal_b"] = out[value] / 1e6
    factor = out["fy"].map(m.cpi_factor)
    pop = out["fy"].map(m.population_k)
    out["real_b"] = out["nominal_b"] * factor
    out["real_pc"] = out[value] * factor / pop  # $K / thousand people = $ per person
    return out.dropna(subset=["real_b", "real_pc"])
