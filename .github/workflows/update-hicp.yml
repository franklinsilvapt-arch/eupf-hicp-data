#!/usr/bin/env python3
"""Build the HICP dataset used by the eupersonalfinance.eu inflation calculator.

Two Eurostat datasets, two different jobs:

  prc_hicp_ainr  annual average rate of change, the definitive figure for each
                 closed year. This is the backbone of the calculator.
  prc_hicp_minr  monthly annual rate of change, used only to estimate the current
                 year, whose annual figure does not exist yet. The estimate is the
                 mean of the months published so far and is flagged as provisional.

Geographies: EA is the euro area with changing composition, the aggregate Eurostat
quotes in its own releases and the only one reaching back to 1997. NL is the
Netherlands, used by the Dutch locale of the calculator.

The monthly step is deliberately non-fatal: if it fails, the script still writes a
valid file with the annual series. A missing provisional year is a small loss; a
broken JSON would take the calculator down.
"""

import json
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
GEOS = {"EA": "Euro area", "NL": "Netherlands"}
START_YEAR = 1997
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "hicp-anual.json"
TIMEOUT = 60


def fetch(dataset: str, params: dict) -> dict:
    query = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            query.extend(f"{key}={item}" for item in value)
        else:
            query.append(f"{key}={value}")
    url = f"{BASE}/{dataset}?" + "&".join(query)
    req = urllib.request.Request(url, headers={"User-Agent": "eupf-hicp-data"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def decode(js: dict) -> dict:
    """Turn a JSON-stat response into {(dim value, ...): number}.

    Eurostat returns values in a flat dict keyed by a single integer offset. The
    offset is recovered from the dimension sizes, in the order given by id.
    """
    dim_ids = js["id"] if "id" in js else js["dimension"]["id"]
    sizes = js["size"] if "size" in js else js["dimension"]["size"]

    labels = []
    for dim in dim_ids:
        index = js["dimension"][dim]["category"]["index"]
        if isinstance(index, list):
            ordered = list(index)
        else:
            ordered = [None] * len(index)
            for code, pos in index.items():
                ordered[pos] = code
        labels.append(ordered)

    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    out = {}
    for flat, value in js.get("value", {}).items():
        if value is None:
            continue
        rest = int(flat)
        key = []
        for dim_pos in range(len(sizes)):
            idx, rest = divmod(rest, strides[dim_pos])
            key.append(labels[dim_pos][idx])
        out[tuple(key)] = float(value)
    return out


def position_of(js: dict, dim: str) -> int:
    dim_ids = js["id"] if "id" in js else js["dimension"]["id"]
    return dim_ids.index(dim)


def annual_series() -> dict:
    js = fetch(
        "prc_hicp_ainr",
        {
            "format": "JSON",
            "lang": "EN",
            "unit": "RCH_A_AVG",
            "coicop": "TOTAL",
            "geo": list(GEOS),
            "sinceTimePeriod": START_YEAR,
        },
    )
    values = decode(js)
    geo_pos = position_of(js, "geo")
    time_pos = position_of(js, "time")

    series = {geo: {} for geo in GEOS}
    for key, value in values.items():
        geo = key[geo_pos]
        year = key[time_pos]
        if geo in series:
            series[geo][year] = round(value, 1)

    for geo, data in series.items():
        if not data:
            raise RuntimeError(f"no annual data returned for {geo}")
    return series


def provisional(closed_years: dict) -> dict:
    """Mean of the monthly year on year rates already published for the open year."""
    year = datetime.now(timezone.utc).year
    js = fetch(
        "prc_hicp_minr",
        {
            "format": "JSON",
            "lang": "EN",
            "unit": "RCH_A",
            "coicop": "TOTAL",
            "geo": list(GEOS),
            "sinceTimePeriod": f"{year}-01",
        },
    )
    values = decode(js)
    geo_pos = position_of(js, "geo")
    time_pos = position_of(js, "time")

    months = {geo: [] for geo in GEOS}
    for key, value in values.items():
        geo = key[geo_pos]
        if geo in months and key[time_pos].startswith(str(year)):
            months[geo].append(value)

    out = {}
    for geo, vals in months.items():
        # Skip if the annual figure for this year is already final.
        if str(year) in closed_years.get(geo, {}):
            continue
        if vals:
            out[geo] = {str(year): round(sum(vals) / len(vals), 1), "months": len(vals)}
    return out


def main() -> int:
    try:
        series = annual_series()
    except (urllib.error.URLError, KeyError, ValueError, RuntimeError) as exc:
        print(f"annual fetch failed: {exc}", file=sys.stderr)
        return 1

    try:
        prov = provisional(series)
    except Exception as exc:  # never fatal: the annual series is what matters
        print(f"provisional estimate skipped: {exc}", file=sys.stderr)
        prov = {}

    payload = {
        "indicator": "HICP, annual average rate of change (%)",
        "source": "Eurostat, prc_hicp_ainr (annual) and prc_hicp_minr (provisional)",
        "note": "EA is the euro area with changing composition. Provisional values are the mean of the months published so far in the current year.",
        "geos": GEOS,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series": series,
        "provisional": prov,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for geo in GEOS:
        years = sorted(series[geo])
        print(f"{geo}: {len(years)} years, {years[0]} to {years[-1]}")
    print(f"provisional: {prov or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
