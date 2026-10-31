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

- Stage 3: `research/` package (config, data, settlement, forecast, backtest, metrics), 9 tests
  (settlement arithmetic, no look-ahead in every forecast model, backtest accounting, proxy vs
  NSE finals) all passing.
- H1 (delivery-month convergence): calibration on 26 pre-futures months chose R2 (AR(1) with
  weekday effects). On futures: model MAE 4.93% vs futures 5.22%, model better in 6/14
  contracts, Wilcoxon p = 0.71. **Rejected** by its pre-registered test. The trading rule made
  +3.4% per contract (t = 1.19, p = 0.13), carried by Mar-Apr 2026; not counted.
- H2 (pre-month level): seasonal models did worse than persistence on pre-futures data
  (MAE 20.6-22.9% vs 15.2%), so the pre-registered choice is M0 (last 30 days). On futures:
  M0 11.3% vs futures 13.7% MAE, better in 6/14, p = 0.34: **not established**. The rule traded
  4 times, all winners (+14.5%, p = 0.029 one-sided, 0.15 after Bonferroni x5): too few trades.
  Futures bias before delivery +5.5% vs M0 -1.5%.
- H3 (short premium): +3.4% per contract, p = 0.24; +7.9% in the first 7 contracts, -1.0% in
  the last 7. **Rejected** (insignificant and unstable).

## Next steps

1. H4 (price-discovery lag) and the daily-return hypotheses (H7 reversal, H8 momentum, H12
   weekday, H16 open interest) on near-month returns.
2. H5 weather if Open-Meteo stops rate-limiting.
4. Stage 6-8 write-up: comparison, portfolio, paper-trading design.
