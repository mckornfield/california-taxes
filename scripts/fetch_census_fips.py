"""County FIPS codes (California only) from the Census 2020 reference file, plus California's county
boundaries (plotly/datasets GeoJSON, filtered to FIPS 06xxx), for choropleth joins."""
import io
import json

import pandas as pd
import requests

from ca_taxes.io import RAW, USER_AGENT, record

GEO_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
URL = "https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt"


def main():
    r = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep="|", dtype=str)
    ca = df[df.STATEFP == "06"].copy()
    ca["fips"] = ca.STATEFP + ca.COUNTYFP
    ca["county"] = ca.COUNTYNAME.str.replace(" County", "", regex=False)
    dest = RAW / "census" / "ca_county_fips.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    ca[["fips", "county"]].to_csv(dest, index=False)
    record(dest, URL, "California rows of national_county2020.txt")
    print(f"wrote {dest} ({len(ca)} counties)")

    g = requests.get(GEO_URL, headers={"User-Agent": USER_AGENT}, timeout=120)
    g.raise_for_status()
    geo = g.json()
    geo["features"] = [f for f in geo["features"] if f["id"].startswith("06")]
    assert len(geo["features"]) == 58
    gdest = RAW / "census" / "ca_counties.geojson"
    gdest.write_text(json.dumps(geo, separators=(",", ":")))
    record(gdest, GEO_URL, "California features only")
    print(f"wrote {gdest}")


if __name__ == "__main__":
    main()
