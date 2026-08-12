# eupf-hicp-data

Inflation data for the inflation calculator on
[eupersonalfinance.eu](https://www.eupersonalfinance.eu/inflation-calculator),
including its Dutch locale at `/nl`.

## What is here

`data/hicp-anual.json` is the only file the website reads. Everything else builds it.

```json
{
  "updated":     "2026-08-12T21:48:19Z",
  "series":      { "EA": { "1997": 1.6, ... }, "NL": { "1997": 1.9, ... } },
  "provisional": { "EA": { "2026": 2.6, "months": 7 }, ... }
}
```

The calculator fetches this file in the visitor's browser, so **the website does not
need republishing when the data changes**. New numbers are live as soon as this file
is committed.

## Source

Eurostat, Harmonised Index of Consumer Prices:

- `prc_hicp_ainr`, annual average rate of change, for every closed year.
- `prc_hicp_minr`, monthly annual rate of change, only to estimate the year still
  running. That estimate is the mean of the months published so far and is marked
  provisional so the calculator can label it.

`EA` is the euro area with **changing composition**. It is the aggregate Eurostat
uses in its releases and the only one that goes back to 1997.

Read through the SDMX 2.1 bulk endpoint. The older `statistics/1.0` query API answers
400 and the previous bulk download service answers **410 Gone**, so neither is worth
returning to. Several endpoint forms are tried in order, so a future move should
degrade to the next candidate rather than take the pipeline down.

## Why the series starts in 1997

The HICP was created to assess the Maastricht price convergence criterion. The first
harmonised indices are from 1996, and an annual rate needs the previous year to
exist, so 1997 is the earliest rate that can be computed. National consumer price
indices reach further back but use different baskets and methods, and cannot be
compared across countries or aggregated into a euro area series.

This is also why the Dutch series uses the HICP and not the CBS national CPI. The two
disagree by more than a rounding error: for 2022 the HICP reads 11.6% while the
national index reads about 10.0%, and 11.6% is the figure Dutch readers saw in the
news.

## Schedule

GitHub Actions runs the pipeline on the 5th and the 20th of each month, and it can be
triggered by hand from the Actions tab.

**Why every run commits, even when no rate changed.** The `updated` timestamp changes
on every execution, so the file always differs and a commit is always created. This is
deliberate and should not be "cleaned up": GitHub disables scheduled workflows in
repositories with no activity for 60 days, and these commits are what keep the
schedule alive. The commit message says the data was updated even when only the
timestamp moved, which is the small price of that guarantee.

The run that matters is the January one, when Eurostat closes the previous year and
the provisional value becomes final. Nothing needs doing by hand: the year simply
leaves the `provisional` block, and the calculator stops marking it with an asterisk.

## Failure behaviour

If Eurostat is unreachable or changes format, the workflow fails and GitHub emails the
repository owner. The previous JSON stays in place, and the calculator additionally
carries a copy of the current figures in its own script, so a broken fetch degrades to
slightly stale numbers rather than to a broken page.

The consequence worth knowing: **a failure here is silent on the website**. Nothing
looks wrong to a visitor, so the failure email is the only signal that the data has
stopped moving.
