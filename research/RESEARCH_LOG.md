# Research log

Chronological. Each entry: what was done, what was found, what changed.

## 2026-10-31

- Data refreshed: NSE bhavcopy to 30 Oct 2026 (Oct-26 expired; 14 settled contracts),
  IEX DAM for all of Oct 2026, IEX daily history extended back to Apr 2022.
- Stage 1 (`01_market.md`): read NSE's launch circulars. Settlement is on daily VWAP across
  PXIL, IEX and HPX DAM (all segments), averaged over the month's days. Verified: best IEX-only
  proxy = mean of daily IEX VW over days 1..expiry+1, error 0.69% (n=14). Verified: on days with
  under 10 trades, NSE's settlement = next day's spot x e^(rt) (median gap 1.6%).
- Stage 2 (`02_hypotheses.md`): 17 hypotheses; H1-H5 pre-registered with fixed rules before
  any backtest (this commit).

## Next steps

1. Stage 3 pipeline: `research/` package (data, settlement, forecasts, backtest, metrics) with tests.
2. H1 and H2 forecast models on pre-futures spot data (2023-04..2025-06), then freeze.
3. Futures tests H1-H4; H5 if weather data can be fetched.
4. Stage 6-8 write-up: comparison, portfolio, paper-trading design.
