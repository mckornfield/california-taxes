"""California public higher education finances (UC, CSU, community colleges) from IPEDS.

The Dept. of Education's Integrated Postsecondary Education Data System collects a finance survey from every
public college and university that follows GASB accounting (form F1A): revenues by source, expenses by function
(instruction, research, public service, ...) and, for all years, expenses split into salaries, fringe benefits
and everything else. Enrollment-based FTE (full-time-equivalent students) comes from the 12-month instructional
activity survey (EFIA). Both are bulk CSV downloads, no key needed:
  https://nces.ed.gov/ipeds/datacenter/data/F<YY><YY+1>_F1A.zip   finance, fiscal year ending in 20<YY+1>
  https://nces.ed.gov/ipeds/datacenter/data/EFIA<YYYY>.zip         12-month FTE, academic year ending in <YYYY>
  https://nces.ed.gov/ipeds/datacenter/data/HD<YYYY>.zip           institution directory (name, state, control)
Fiscal year = year the fiscal year ends (2022-23 -> 2023), like the rest of the repo. FY2004 on: variable names
are stable from then on (earlier files use a different layout and are not used).

Kept: California public institutions with 2-year or 4-year programs. Groups (by name, see classify()):
UC (10 campuses + UC College of the Law, SF), CSU (23 campuses), California Community Colleges (the rest; the
survey is filed by college or district, and the rows are not double counted). Left out: Naval Postgraduate School
(federal), adult schools and regional occupational programs (sector 'less than 2-year'; they are part of K-12 spending),
and non-system units such as Teachers College of San Joaquin.

Output: data/raw/ipeds/ca_public_higher_ed.csv  one row per institution-year, $ whole dollars (as filed),
        columns: fy, unitid, institution, system, fte, then the F1B*/F1C* variables listed in KEEP.
Downloads are cached in data/raw/ipeds/_cache (gitignored, ~30 MB).
"""
import io
import re
import sys
import zipfile

import pandas as pd

from ca_taxes.io import RAW, get_with_retry, record

BASE = "https://nces.ed.gov/ipeds/datacenter/data"
CACHE = RAW / "ipeds" / "_cache"
OUT = RAW / "ipeds" / "ca_public_higher_ed.csv"
FIRST, LAST = 2004, 2023  # bump LAST when NCES posts a newer finance file

# F1B revenue lines and F1C expense lines (current year total, salaries and wages); stable FY2004-on
REVENUE = ["F1B01", "F1B02", "F1B03", "F1B04", "F1B05", "F1B06", "F1B07", "F1B08", "F1B09", "F1B10", "F1B11", "F1B12", "F1B13",
           "F1B14", "F1B15", "F1B16", "F1B17", "F1B18", "F1B19", "F1B20", "F1B21", "F1B22", "F1B23", "F1B24", "F1B25"]
FUNCTIONS = ["F1C011", "F1C021", "F1C031", "F1C051", "F1C061", "F1C071", "F1C101", "F1C111", "F1C121", "F1C131", "F1C141"]  # totals
FUNCTION_SALARIES = [c[:-1] + "2" for c in FUNCTIONS if c != "F1C101"]  # salaries and wages; scholarships have none after 2008
TOTALS = ["F1C191", "F1C192", "F1C193"]  # total expenses, salaries and wages, fringe benefits
OPTIONAL = ["F1B26",  # sales and services of educational activities (clinical practice fees etc.), FY2008 on
            "F1C081"]  # operation and maintenance of plant as its own function, FY2004-2015 only (afterwards allocated to functions)
KEEP = REVENUE + FUNCTIONS + FUNCTION_SALARIES + TOTALS


def get_zip(name: str) -> zipfile.ZipFile:
    dest = CACHE / f"{name}.zip"
    if not dest.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = get_with_retry(f"{BASE}/{name}.zip", timeout=300)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"downloaded {name}.zip ({len(r.content):,} bytes)", flush=True)
    return zipfile.ZipFile(dest)


def read_csv(name: str) -> pd.DataFrame:
    """The zip holds <name>.csv and sometimes a revised <name>_rv.csv, which supersedes it."""
    z = get_zip(name)
    members = {m.lower(): m for m in z.namelist() if m.lower().endswith(".csv")}
    pick = next((m for k, m in members.items() if k.endswith("_rv.csv")), None) or next(iter(members.values()))
    df = pd.read_csv(io.BytesIO(z.read(pick)), encoding="latin-1", low_memory=False)
    df.columns = [re.sub(r"[^A-Z0-9]", "", c.upper().replace("ï»¿", "")) for c in df.columns]
    return df


def classify(name: str) -> str | None:
    """'UC', 'CSU', 'Community colleges', or None for units that are not part of the three systems and not counted."""
    if re.search(r"naval postgraduate|massachusetts|teachers college", name, re.I):
        return None
    if re.match(r"University of California", name, re.I):
        return "UC"
    if re.search(r"California State|California Polytechnic|California Maritime|Cal Poly|Humboldt State|"
                 r"(San Diego|San Francisco|San Jose|Sonoma) State", name, re.I):
        return "CSU"
    return "Community colleges"


def read_year(fy: int) -> pd.DataFrame:
    a, b = (fy - 1) % 100, fy % 100
    fin = read_csv(f"F{a:02d}{b:02d}_F1A")
    hd = read_csv(f"HD{fy}")
    hd = hd[(hd.STABBR == "CA") & (hd.CONTROL == 1) & hd.SECTOR.isin([1, 4])][["UNITID", "INSTNM"]]
    df = fin.merge(hd, on="UNITID").copy()
    df = df.assign(system=df.INSTNM.map(classify))
    df = df[df.system.notna()].copy()
    efia = read_csv(f"EFIA{fy}")
    fte_cols = [c for c in ("FTEUG", "FTEGD") if c in efia.columns]
    efia["fte"] = efia[fte_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    df = df.merge(efia[["UNITID", "fte"]], on="UNITID", how="left")
    missing = [c for c in KEEP if c not in df.columns]
    assert not missing, f"FY{fy}: finance variables missing {missing}"
    for c in KEEP + OPTIONAL:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df.columns else float("nan")
    out = df[["UNITID", "INSTNM", "system", "fte"] + KEEP + OPTIONAL].rename(columns={"UNITID": "unitid", "INSTNM": "institution"})
    out.insert(0, "fy", fy)
    return out


def main():
    years = [int(a) for a in sys.argv[1:]] or list(range(FIRST, LAST + 1))
    frames = []
    for fy in years:
        d = read_year(fy)
        frames.append(d)
        s = d.groupby("system").F1C191.sum() / 1e9
        print(f"FY{fy}: {len(d)} institutions; expenses $B " + ", ".join(f"{k} {v:.1f}" for k, v in s.items()), flush=True)
    out = pd.concat(frames, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    record(OUT, f"{BASE}/F<YY><YY+1>_F1A.zip, EFIA<YYYY>.zip, HD<YYYY>.zip", "IPEDS finance (GASB), 12-month FTE and directory, California public higher education")
    print(f"wrote {OUT.relative_to(RAW.parent.parent)} ({len(out):,} rows)")


if __name__ == "__main__":
    main()
