#!/usr/bin/env python3
"""Build the HICP dataset used by the eupersonalfinance.eu inflation calculator.

Reads Eurostat's SDMX 2.1 bulk endpoint. The older statistics/1.0 query API answers
400 and the previous bulk download service answers 410 Gone, so both were dropped.
The TSV format is the one verified by hand against the series this calculator ships
with, which is why it is preferred over JSON-stat here.

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

import gzip
import json
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

GEOS = {"EA": "Euro area", "NL": "Netherlands"}
START_YEAR = 1997
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "hicp-anual.json"
TIMEOUT = 180

# Eurostat retired the old bulk download service (it answers 410 Gone) and the
# statistics/1.0 query API with it. Everything now lives under SDMX 2.1. The forms
# below are tried in order so a future move degrades to the next candidate instead
# of taking the pipeline down.
BULK_URLS = [
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}?format=TSV&compressed=true",
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}/?format=TSV&compressed=true",
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}?format=TSV",
    "https://ec.europa.eu/eurostat/api/dissemination/files/data/{ds}.tsv.gz",
]


def download_tsv(dataset: str) -> str:
    """Fetch and unzip a bulk dataset, trying each known endpoint in turn."""
    errors = []
    for template in BULK_URLS:
        url = template.format(ds=dataset)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eupf-hicp-data"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:300]
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

        # A stray HTML error page would decompress to nothing useful, so sanity check.
        if "\t" not in text.split("\n", 1)[0]:
            errors.append(f"{url} -> response is not a TSV")
            continue
        print(f"fetched {dataset} from {url}")
        return text

    raise RuntimeError("all bulk endpoints failed:\n  " + "\n  ".join(errors))


def parse_tsv(text: str, freq: str, unit: str, coicop: str) -> dict:
    """Return {geo: {period: value}} for the rows matching the given key.

    Bulk files look like this, with the dimension key packed into the first column:

        freq,unit,coicop,geo\\TIME_PERIOD	1996	1997	...
        A,RCH_A_AVG,TOTAL,EA	:	1.6 	1.1 	...

    Values carry observation flags such as a trailing 'p' for provisional, and ':'
    marks a missing observation.
    """
    lines = text.strip().split("\n")
    periods = [p.strip() for p in lines[0].split("\t")[1:]]

    wanted = {geo: f"{freq},{unit},{coicop},{geo}" for geo in GEOS}
    out = {geo: {} for geo in GEOS}

    for line in lines[1:]:
        if "\t" not in line:
            continue
        key, _, rest = line.partition("\t")
        key = key.strip()
        geo = next((g for g, k in wanted.items() if key == k), None)
        if geo is None:
            continue
        for period, cell in zip(periods, rest.split("\t")):
            cell = cell.strip()
            if not cell or cell.startswith(":"):
                continue
            try:
                out[geo][period] = float(cell.split(" ")[0])
            except ValueError:
                continue
    return out


def annual_series() -> dict:
    raw = parse_tsv(download_tsv("prc_hicp_ainr"), "A", "RCH_A_AVG", "TOTAL")
    series = {}
    for geo, values in raw.items():
        series[geo] = {
            year: round(value, 1)
            for year, value in values.items()
            if year.isdigit() and int(year) >= START_YEAR
        }
        if not series[geo]:
            raise RuntimeError(f"no annual data found for {geo}")
    return series


def provisional(closed_years: dict) -> dict:
    """Mean of the monthly year on year rates already published for the open year."""
    year = str(datetime.now(timezone.utc).year)
    raw = parse_tsv(download_tsv("prc_hicp_minr"), "M", "RCH_A", "TOTAL")

    out = {}
    for geo, values in raw.items():
        # Skip if the annual figure for this year is already final.
        if year in closed_years.get(geo, {}):
            continue
        months = [v for period, v in values.items() if period.startswith(year + "-")]
        if months:
            out[geo] = {year: round(sum(months) / len(months), 1), "months": len(months)}
    return out


def main() -> int:
    try:
        series = annual_series()
    except Exception as exc:
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
        print(f"{geo}: {len(years)} years, {years[0]} to {years[-1]}, latest {series[geo][years[-1]]}%")
    print(f"provisional: {prov or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
