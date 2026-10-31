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

- H4 (price-discovery lag), near contract, 317 liquid day-pairs: today's fair-value news
  predicts tomorrow's return (coef 0.17, t 2.47; same-day 0.57), passes its gate before
  Bonferroni (0.068 after). Pre-registered rule (|news| > 0.5%, hold 1 day): +0.40% per trade
  gross (t 2.26) but **-0.17% after costs** (0.57% round trip). Fails. Exploratory: bigger
  thresholds help gross, net t < 1. The reaction mostly happens on the publication day itself
  (DAM out 13-15h, futures trade to 23:30): intraday data would be needed to test that.
- Other daily tests (near): today's return predicts tomorrow (t 2.27); basis predicts (t 2.76);
  5-day momentum, weekday, OI change, reversal after 6% moves: nothing (|t| < 1.6). Next
  contract: only same-day news and OI (t 2.9, tiny coefficient).
- H5 weather: 9 load centres, ERA5 daily (Open-Meteo). Upper bound with PERFECT knowledge of
  the delivery month's weather explains 3-7% of month-over-month index moves; leave-one-out
  error worse than persistence. **Rejected.** Daily: same-day weather adds R2 0.013 over AR.
- H15 hybrid (walk-forward by contract, 11 OOS contracts): predicted next-day return from
  news, basis and today's return. Gross +1.13% per trade (t 2.37, 10/11 contracts) at
  |pred| > 0.6%; **net +0.57% (t 1.20, 7/11)**; breakeven cost ~Rs 47/MWh round trip (2x
  assumed); halves 0.59%/0.56%. Mostly shorts (41/57, +0.77%) in Mar-May 2026, which overlaps
  the fading premium. Best candidate; not statistically established; paper-trade.

- H15 without intercept (to separate signal from the premium drift): net +0.64%/trade (t 1.31),
  so the signal is not just the drift. H6 calendar spread: no information (worse than "no
  change"). Seasonality from data: only Dec and Jan rose in all years.
- Stage 8: `paper.py` (tested). Replay Dec-25..Oct-26 with daily refits: 55 trades, +0.18% per
  trade net, max DD 4.1% of Rs 10 lakh. Lower than the per-contract walk-forward (+0.64%):
  the edge is sensitive to how often the model is refitted, i.e. not robust.
- Write-up: `03_results.md`. Conclusion: no strategy statistically established; H15 is the
  only candidate for paper trading; intraday data after the DAM result is the best next lead.

- Mispricing regressions (brief: does model mispricing predict later returns?): pre-month
  ln(M0/F) predicts ln(final/F), slope 0.82 (t 3.2 clustered, wild bootstrap p 0.003), but
  slope ~0 in the first 7 contracts and ~1 in the last 7. Same pattern early in the delivery
  month. Pre-registered as H18 for forward testing only (Nov-26 onward); first signal Nov-26 long.

## Next steps

1. Paper-trade H15 daily (`python -m research.paper run`) and record H18 (`python -m research.forward_h18`)
   for at least 6-8 more contracts.
2. Get intraday NSE electricity futures data to test entry right after the DAM result.
3. Get PXIL/HPX DAM and IEX green/high-price data to compute the settlement exactly.
4. Get MCX bhavcopy history (manual download) for the NSE-MCX index spread (H13).
