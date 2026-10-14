"""California school spending by object (salaries, pensions, supplies...) from the Dept. of Education's SACS data.

Every school district, county office of education and charter school that uses California's Standardized
Account Code Structure (SACS) files year-end unaudited actuals with the CDE. CDE publishes one download per
fiscal year, 2003-04 on, as a self-extracting archive of a Microsoft Access database:
  https://www3.cde.ca.gov/fiscal-downloads/sacs_data/<YYYY-YY>/sacs<YY><YY>.exe     (index page: https://www.cde.ca.gov/ds/fd/fd/)
The .exe is a plain zip with an .mdb inside (never executed here). The database already has statewide totals
in table UserGL_Totals (county code 99, district code 99999), by fund, resource, goal, function and object.

This script keeps, per year, the statewide totals summed to (fund, function, object), plus the code
descriptions and a count of LEAs and a rough K-12 average daily attendance (ADA). The ADA is NOT used anywhere: the LEAs table's scope changes
between years (2008-09 lists about twice as many rows), so it is not comparable over time. Per-pupil figures would need CDE's enrollment series. Fiscal year is the year the school year
ends (2023-24 -> 2024), like the rest of the repo.

Outputs (data/raw/cde/):  sacs_state_totals.csv  fy, fund, function, object, amount   ($ whole dollars)
                          sacs_object_codes.csv / sacs_function_codes.csv / sacs_fund_codes.csv  (latest year's titles)
                          sacs_leas.csv  fy, n_leas, k12_ada
Downloads are cached in data/raw/cde/_cache (gitignored, ~0.9 GB); each 350-480 MB .mdb is deleted after parsing.

Notes: reading the .mdb uses the pure-Python `access-parser` package, which is slow and memory hungry
(about 5 GB peak per year). It mis-splits this database's text columns, so the fixed-width fields are re-sliced
from the intact `Account` column (fund 2 + resource 4 + project year 1 + goal 4 + function 4 + object 4)
and from the concatenated Ccode text (county 2 + district 5 + fiscal year 4 + period 1).
Amounts are an Access Decimal in most years (decoded here) and a plain float in some older ones.
Charter schools that filed only the 'Alternative Form' are not in this table.
"""
import gc
import struct
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

from ca_taxes.io import RAW, USER_AGENT, record

BASE = "https://www3.cde.ca.gov/fiscal-downloads/sacs_data/{y0}-{y1:02d}/sacs{y0s}{y1:02d}.exe"
CACHE = RAW / "cde" / "_cache"
OUT = RAW / "cde"
FIRST, LAST = 2003, 2023  # school years starting in these calendar years (2003-04 ... 2023-24); bump LAST when CDE posts a new year


def decode(v) -> float:
    """Access Decimal(18,2) arrives as 17 raw bytes: sign byte (0x80 = negative) + four little-endian dwords, most significant first."""
    if isinstance(v, (bytes, bytearray)):
        sign = -1 if v[0] & 0x80 else 1
        w = struct.unpack("<4I", bytes(v[1:17]))
        return sign * ((w[0] << 96) | (w[1] << 64) | (w[2] << 32) | w[3]) / 100
    return float(v)


def download(start: int) -> Path:
    url = BASE.format(y0=start, y1=(start + 1) % 100, y0s=f"{start % 100:02d}")
    dest = CACHE / url.rsplit("/", 1)[1]
    if not dest.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=600)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"downloaded {url} ({len(r.content):,} bytes)", flush=True)
    return dest


def read_year(start: int, want_codes: bool):
    from access_parser import AccessParser

    exe = download(start)
    with zipfile.ZipFile(exe) as z:
        member = next(i.filename for i in z.infolist() if i.filename.lower().endswith(".mdb"))
        mdb = CACHE / f"sacs{start}.mdb"
        mdb.write_bytes(z.read(member))
    try:
        db = AccessParser(str(mdb))
        t = pd.DataFrame(db.parse_table("UserGL_Totals"))
        ccode = t["Ccode"].astype(str)  # concatenated text: county(2) district(5) fiscal year(4) period(1) ...
        state = t[(ccode.str[:2] == "99") & (ccode.str[2:7] == "99999")].copy()
        c = state["Ccode"].astype(str)
        assert c.str[11].eq("A").all(), "expected unaudited-actual rows only"
        fy_start = c.str[7:11].astype(int)
        assert (fy_start == start).all(), f"fiscal year mismatch in {mdb.name}: {sorted(set(fy_start))}"
        acct = state["Account"].astype(str)
        df = pd.DataFrame({"fund": acct.str[0:2], "function": acct.str[11:15], "object": acct.str[15:19],
                           "amount": state["Value"].map(decode)})
        df = df.groupby(["fund", "function", "object"], as_index=False).amount.sum()
        df = df[df.amount.round(2) != 0]
        df.insert(0, "fy", start + 1)
        leas = pd.DataFrame(db.parse_table("LEAs"))
        cols = {c.lower(): c for c in leas.columns}
        if "k12ada" in cols:  # 2003-04 and some other early years have RegularADA + SpecialEdADA (+ ROC/P and adult) instead
            ada = pd.to_numeric(leas[cols["k12ada"]], errors="coerce").sum()
        else:
            ada = sum(pd.to_numeric(leas[cols[k]], errors="coerce").sum() for k in ("regularada", "specialedada"))
        lea = dict(fy=start + 1, n_leas=len(leas), k12_ada=float(ada))
        codes = None
        if want_codes:
            codes = {}
            for name, width in (("Object", 4), ("Function", 4), ("Fund", 2)):
                d = pd.DataFrame(db.parse_table(name))
                # the Code column comes back as code + title run together; the Title column is intact
                codes[name] = pd.DataFrame({"code": d["Code"].astype(str).str[:width], "title": d["Title"].astype(str).str.strip()})
        return df, lea, codes
    finally:
        mdb.unlink(missing_ok=True)
        gc.collect()


def main():
    years = [int(a) for a in sys.argv[1:]] or list(range(FIRST, LAST + 1))
    frames, leas, codes = [], [], None
    for y in years:
        df, lea, c = read_year(y, want_codes=(y == max(years)))
        frames.append(df)
        leas.append(lea)
        codes = c or codes
        print(f"{y}-{(y + 1) % 100:02d}: {len(df):,} rows, ADA {lea['k12_ada']:,.0f}, LEAs {lea['n_leas']}, "
              f"expenditure objects 1000-7999 ${df[df.object.str[0].isin(list('1234567'))].amount.sum() / 1e9:,.1f}B", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat(frames).to_csv(OUT / "sacs_state_totals.csv", index=False)
    pd.DataFrame(leas).to_csv(OUT / "sacs_leas.csv", index=False)
    for name, d in (codes or {}).items():
        d.to_csv(OUT / f"sacs_{name.lower()}_codes.csv", index=False)
    for f in OUT.glob("*.csv"):
        record(f, BASE.format(y0="<YYYY>", y1=0, y0s="<YY>"), "CDE SACS unaudited actuals, California statewide totals (UserGL_Totals)")
    print("done")


if __name__ == "__main__":
    main()
