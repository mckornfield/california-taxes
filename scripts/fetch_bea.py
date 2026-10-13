"""California personal income detail from the BEA regional bulk download (no key needed).

Source: https://apps.bea.gov/regional/zip/SAINC.zip  (State Annual Income and Employment tables, ~17 MB)
Kept (California only, calendar years, $ thousands):
  SAINC35  personal current transfer receipts by program, 1929-2025
           (Social Security, Medicare, Medicaid, SNAP, veterans, ... from governments of all levels)
  SAINC6S / SAINC6N  compensation of employees by industry, 1958-2001 (SIC) and 1998-2025 (NAICS):
           'Federal civilian' and 'Military' lines used for federal pay
Output: data/raw/bea/*.csv. The zip itself is not kept.
"""
import io
import zipfile

import requests

from ca_taxes.io import RAW, USER_AGENT, record

URL = "https://apps.bea.gov/regional/zip/SAINC.zip"
KEEP = ["SAINC35_CA_1929_2025.csv", "SAINC6S_CA_1958_2001.csv", "SAINC6N_CA_1998_2025.csv"]


def main():
    r = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300)
    r.raise_for_status()
    dest = RAW / "bea"
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = {n.split("/")[-1]: n for n in z.namelist()}
        for k in KEEP:
            # file names carry the data's year span, which changes each release; match on table + state
            stem = "_".join(k.split("_")[:2]) + "_"
            match = next((n for b, n in names.items() if b.startswith(stem)), None)
            if match is None:
                raise SystemExit(f"{stem}* not found in {URL}; BEA may have renamed tables")
            out = dest / names_to_out(match)
            out.write_bytes(z.read(match))
            record(out, URL, f"BEA {stem.rstrip('_')} from SAINC.zip")
            print(f"wrote {out.relative_to(RAW.parent.parent)}")


def names_to_out(zip_member: str) -> str:
    base = zip_member.split("/")[-1]
    return "_".join(base.split("_")[:2]) + ".csv"  # e.g. SAINC35_CA.csv, independent of the year span


if __name__ == "__main__":
    main()
