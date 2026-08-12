# eupf-hicp-data

Inflation data for the inflation calculator on
[eupersonalfinance.eu](https://www.eupersonalfinance.eu/inflation-calculator),
including its Dutch locale at `/nl`.

## What is here

`data/hicp-anual.json` is the only file the website reads. Everything else builds it.

```json
{
  "series":      { "EA": { "1997": 1.6, ... }, "NL": { "1997": 1.9, ... } },
  "provisional": { "EA": { "2026": 2.5, "months": 7 }, ... }
}
```

## Source

Eurostat, Harmonised Index of Consumer Prices:

- `prc_hicp_ainr`, annual average rate of change, for every closed year.
- `prc_hicp_minr`, monthly annual rate of change, only to estimate the year still
  running. That estimate is the mean of the months published so far and is marked
  provisional so the calculator can label it.

`EA` is the euro area with **changing composition**. It is the aggregate Eurostat
uses in its releases and the only one that goes back to 1997.

## Why the series starts in 1997

The HICP was created to assess the Maastricht price convergence criterion. The first
harmonised indices are from 1996, and an annual rate needs the previous year to
exist, so 1997 is the earliest rate that can be computed. National consumer price
indices reach further back but use different baskets and methods, and cannot be
compared across countries or aggregated into a euro area series.

## Schedule

GitHub Actions runs the pipeline on the 5th and the 20th of each month, and it can
be triggered by hand from the Actions tab. A commit is only created when a number
actually changes.

The figure that matters is the January one, when Eurostat closes the previous year
and the provisional value becomes final.

## Failure behaviour

If Eurostat is unreachable or changes format, the workflow fails loudly and the
previous JSON stays in place. The calculator also carries the current figures
hardcoded as a fallback, so a broken fetch degrades to slightly stale numbers
rather than to a broken page.
