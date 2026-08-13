#!/usr/bin/env python3
"""Build the inflation dataset used by the eupersonalfinance.eu inflation calculator.

Two audiences, two indices, on purpose:

  EA  Euro area, Eurostat HICP (prc_hicp_ainr), annual average rate of change,
      from 1997. The harmonised index is the right one for a pan-European page
      because it is the only measure comparable across member states.

  NL  Netherlands, CBS national CPI (StatLine 70936ned), from 1963. This is the
      figure Dutch media and Dutch competitors quote. It differs from the HICP by
      more than rounding: 2022 reads 10.0% here and 11.6% in the HICP. On a page
      written for Dutch readers, matching what they remember beats cross-border
      comparability, and it buys 34 extra years of history.

The current year is estimated from the months already published and flagged as
provisional. That step is deliberately non-fatal: a missing provisional year is a
small loss, a broken JSON would take the calculator down.
"""

import gzip
import json
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

EA_START = 1997
NL_START = 1963
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "hicp-anual.json"
TIMEOUT = 180

GEOS = {"EA": "Euro area", "NL": "Netherlands"}

# Eurostat retired the old bulk download service (410 Gone) and the statistics/1.0
# query API with it. Everything now lives under SDMX 2.1. Forms are tried in order so
# a future move degrades to the next candidate instead of taking the pipeline down.
EUROSTAT_URLS = [
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}?format=TSV&compressed=true",
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}/?format=TSV&compressed=true",
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}?format=TSV",
    "https://ec.europa.eu/eurostat/api/dissemination/files/data/{ds}.tsv.gz",
]

# CBS OData v3. Periods look like 1963MM01 for months and 1963JJ00 for the year.
CBS_URL = (
    "https://opendata.cbs.nl/ODataApi/OData/70936ned/TypedDataSet"
    "?$select=Perioden,JaarmutatieCPI_1"
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "eupf-hicp-data"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


# ----------------------------------------------------------------- Eurostat (EA)

def download_tsv(dataset: str) -> str:
    errors = []
    for template in EUROSTAT_URLS:
        url = template.format(ds=dataset)
        try:
            raw = fetch(url)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            errors.append(f"{url} -> HTTP {exc.code} {body}")
            continue
        except Exception as exc:
            errors.append(f"{url} -> {exc}")
            continue

        try:
            text = gzip.decompress(raw).decode("utf-8")
        except OSError:
            text = raw.decode("utf-8", "replace")

        if "\t" not in text.split("\n", 1)[0]:
            errors.append(f"{url} -> response is not a TSV")
            continue
        print(f"fetched {dataset} from {url}")
        return text

    raise RuntimeError("all Eurostat endpoints failed:\n  " + "\n  ".join(errors))


def parse_tsv(text: str, key: str) -> dict:
    """Return {period: value} for the row whose dimension key matches exactly.

    Bulk files pack the dimensions into the first column and carry observation
    flags, so values look like '1.6 p' and ':' marks a missing observation.
    """
    lines = text.strip().split("\n")
    periods = [p.strip() for p in lines[0].split("\t")[1:]]
    out = {}
    for line in lines[1:]:
        if "\t" not in line:
            continue
        rowkey, _, rest = line.partition("\t")
        if rowkey.strip() != key:
            continue
        for period, cell in zip(periods, rest.split("\t")):
            cell = cell.strip()
            if not cell or cell.startswith(":"):
                continue
            try:
                out[period] = float(cell.split(" ")[0])
            except ValueError:
                continue
    return out


def euro_area() -> tuple:
    annual_raw = parse_tsv(download_tsv("prc_hicp_ainr"), "A,RCH_A_AVG,TOTAL,EA")
    annual = {
        y: round(v, 1)
        for y, v in annual_raw.items()
        if y.isdigit() and int(y) >= EA_START
    }
    if not annual:
        raise RuntimeError("no annual data found for EA")

    prov = {}
    try:
        year = str(datetime.now(timezone.utc).year)
        if year not in annual:
            monthly = parse_tsv(download_tsv("prc_hicp_minr"), "M,RCH_A,TOTAL,EA")
            months = [v for p, v in monthly.items() if p.startswith(year + "-")]
            if months:
                prov = {year: round(sum(months) / len(months), 1), "months": len(months)}
    except Exception as exc:
        print(f"EA provisional skipped: {exc}", file=sys.stderr)

    return annual, prov


# --------------------------------------------------------------------- CBS (NL)

def netherlands() -> tuple:
    raw = json.loads(fetch(CBS_URL).decode("utf-8"))
    rows = raw.get("value", [])
    if not rows:
        raise RuntimeError("CBS returned no rows")

    annual = {}
    monthly = {}
    for row in rows:
        period = (row.get("Perioden") or "").strip()
        value = row.get("JaarmutatieCPI_1")
        if value is None or len(period) < 6:
            continue
        year, kind = period[:4], period[4:6]
        if kind == "JJ":
            if year.isdigit() and int(year) >= NL_START:
                annual[year] = round(float(value), 1)
        elif kind == "MM":
            monthly.setdefault(year, []).append(float(value))

    if not annual:
        raise RuntimeError("no annual CBS data found")

    prov = {}
    year = str(datetime.now(timezone.utc).year)
    if year not in annual and monthly.get(year):
        vals = monthly[year]
        prov = {year: round(sum(vals) / len(vals), 1), "months": len(vals)}

    print(f"fetched NL from {CBS_URL}")
    return annual, prov


# ------------------------------------------------------------------------ main

def main() -> int:
    series, provisional = {}, {}

    try:
        series["EA"], prov = euro_area()
        if prov:
            provisional["EA"] = prov
    except Exception as exc:
        print(f"euro area fetch failed: {exc}", file=sys.stderr)
        return 1

    try:
        series["NL"], prov = netherlands()
        if prov:
            provisional["NL"] = prov
    except Exception as exc:
        print(f"netherlands fetch failed: {exc}", file=sys.stderr)
        return 1

    payload = {
        "indicator": "Annual average rate of change of consumer prices (%)",
        "sources": {
            "EA": "Eurostat, HICP, prc_hicp_ainr and prc_hicp_minr, from 1997",
            "NL": "CBS StatLine 70936ned, national CPI (jaarmutatie), from 1963",
        },
        "note": (
            "EA is the euro area with changing composition. NL uses the CBS national CPI "
            "rather than the HICP because that is the figure quoted in the Netherlands; "
            "the two differ materially (2022: 10.0 vs 11.6). Provisional values are the "
            "mean of the months published so far in the current year."
        ),
        "geos": GEOS,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series": series,
        "provisional": provisional,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for geo in GEOS:
        years = sorted(series[geo])
        print(f"{geo}: {len(years)} years, {years[0]} to {years[-1]}, latest {series[geo][years[-1]]}%")
    print(f"provisional: {provisional or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
