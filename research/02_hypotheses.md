# Stage 2: strategy hypotheses

Written 31 Oct 2026, **before** any backtest in this repo, so the rules below are fixed in
advance. Any later change is logged in `RESEARCH_LOG.md` with its reason.

## Constraints that shape everything

- **14 settled NSE contracts** (Sep-25 to Oct-26) with real futures prices. Any test on the
  futures themselves has 14 independent outcomes at most. Daily observations within a
  contract are strongly dependent. All inference is clustered by contract.
- **4.5 years of IEX DAM** (Apr 2022 to Oct 2026). Spot-forecasting models can be developed and
  validated on spot history before any futures existed; the futures period is then a true
  out-of-sample test of whether the forecasts beat the market price.
- **Settlement proxy error ~0.7%** (Stage 1): edges below ~1% are not detectable.
- **No intraday quotes.** Trades are assumed done at the day's settlement price (the
  last-30-minute VWAP) plus costs, and only on days with 10+ trades (the settlement is then a
  market price). Days with fewer trades are not tradable in the backtest.
- **Capacity**: near month 1,000-3,000 lots a day; a strategy is assumed to trade at most 5%
  of the day's lots.

## Information timing (applies to every hypothesis)

A decision at the close of trading day T may use: NSE prices up to T; IEX DAM for delivery
days up to T+1 (published by 15:00 on T); anything else published by 23:30 IST on T. The trade
is done at T's settlement price.

## All hypotheses

Ranked by research priority (economic mechanism x data we have x tradability).

| # | Hypothesis | Category | Mechanism | Data | Priority |
|---|---|---|---|---|---|
| H1 | Inside the delivery month, futures misprice the known part plus a good forecast of the rest | spot-futures convergence, settlement forecasting | retail participants do not compute the index; known days are pure arithmetic | have | **1** |
| H2 | Before the delivery month, futures anchor to last month's level; a seasonal/recent-trend forecast of next month beats them | settlement forecasting, seasonality | anchoring; few participants model seasonality | have | **2** |
| H3 | Futures sit above the expected settlement (speculative long premium); shorting earns it | risk premium | retail long bias, no natural short hedgers (generators) active | have | **3** |
| H4 | Futures react to each day's DAM result with a lag, so yesterday's news predicts today's move | price discovery delay | thin market, many participants trade once a day | have | **4** |
| H5 | Weather forecasts (temperature anomalies at load centres) improve the next-month forecast beyond H2 | weather, demand surprise | cooling demand moves the DAM; forecasts lead | Open-Meteo, rate-limited | **5** |
| H6 | Near/next calendar spread reverts to the seasonal spread | calendar spread | next month thinly traded, quoted off the near month | have (next month liquid only ~5 weeks) | 6 |
| H7 | Big daily futures moves (limit hits, 6-9%) partly reverse next day | mean reversion | forced liquidation / margin calls in a thin market | have | 7 |
| H8 | Futures momentum over 3-10 days | momentum | slow diffusion of fundamentals | have | 8 |
| H9 | Spot volatility regime (realised vol of daily DAM) predicts futures premium | volatility regime | risk premium rises with uncertainty | have | 9 |
| H10 | Midday solar strength (cheapest-hours price) trend predicts the volume-weighted index | renewable forecasting | VW index weights the solar hours heavily | have (IEX blocks) | 10 |
| H11 | Event effects: price-cap changes, heatwave alerts, coal shortage notices | event-driven | slow incorporation of regulatory/weather news | news archive needed | 11 |
| H12 | Day-of-week / pre-weekend effect in futures returns | calendar | weekend DAM days published Fri-Sun, futures closed | have | 12 |
| H13 | NSE vs MCX: MCX index weights days by volume and uses UMCP simple-average blocks; their spread tracks the evening-cap share | cross-market | different indices, separate speculators | MCX history blocked | 13 |
| H14 | Gradient-boosted model of next-day futures return on all features | ML forecasting | none specific | have | 14 |
| H15 | Hybrid: H1/H2 fair value + H4 timing | hybrid | combines | have | 15 |
| H16 | Open-interest build-up with price (flow) predicts direction | futures structure | informed positioning | have | 16 |
| H17 | DAM bid-volume imbalance (purchase vs sell bids) predicts next-week prices | demand surprise | bids reveal demand before prices settle | have (IEX bids) | 17 |

H11, H13 lack data here. H14 is run only if a simpler model shows signal (with 14 contracts an
ML model on daily returns would mostly fit noise).

## Pre-registered specifications (H1-H5)

Common to all: trade only on days with 10+ trades; fill at that day's settlement price;
costs per side = half-spread Rs 5/MWh (market-maker obligation) + slippage Rs 5/MWh + fees
0.01% + CTT 0.01% (sell) + stamp 0.002% (buy) + Rs 20 brokerage per order; sensitivity at 2x
and 4x. Position marked daily at the settlement price, closed at the final settlement on
expiry. Margin assumed 20% of notional (above SEBI floors, as the contract is volatile).
Returns reported per contract, per lot and on margin. No annualised Sharpe from 14 contracts
is treated as meaningful; the main statistics are mean PnL per contract-trade, its t-stat
clustered by contract, hit rate, worst contract, and a sign test.

### H1: delivery-month convergence

- **Predicts**: the final settlement S of the near contract, during its delivery month.
- **Model**: S_hat(T) = (sum of known daily VW prices + n_rest x R_hat) / N, with N the
  settlement days (1 to expiry+1) and R_hat a forecast of the mean daily VW price of the
  unknown days. R_hat candidates, all fit only on data before T:
  - R0: mean of the last 7 known days (persistence)
  - R1: exponentially weighted mean, half-life 3 days
  - R2: AR(1) on log daily VW deviations from a 28-day mean, fitted on 2022-04..T, with
    day-of-week effects. Selected by forecast error on 2023-04..2025-06 (pre-futures) only.
- **Signal**: edge = (S_hat - F_T) / F_T, F_T the settlement price at T.
- **Entry**: |edge| > k x sigma_T, sigma_T = historical sd of the S_hat error at the same number
  of remaining days (from 2023-04..2025-06 spot data), k = 1. Direction = sign(edge).
- **Exit**: hold to expiry (main), or close when |edge| < 0.25 sigma_T (variant).
- **Sizing**: 1 lot per unit of |edge|/sigma, max 3 lots; capped at 5% of day's lots.
- **Risk**: no stop-loss in the main test (the payoff converges to a known index); daily
  MTM tracked for drawdown and margin.
- **Holding**: 1-25 days. **Contracts**: near month, in its delivery month.
- **Fails if**: forecast error of S_hat is no smaller than the futures' error at the same day;
  or mean PnL per contract <= 0 after costs; or the sign test is not better than 50%.
- **Falsification**: if S_hat does not beat F_T on mean absolute error over the 14 contracts
  (paired, by remaining-days bucket), H1 is rejected regardless of PnL.

### H2: pre-month level forecast

- **Predicts**: the final settlement of the next contract, from 25 to 5 trading days before
  its delivery month.
- **Models** (monthly index = mean of daily VW over the month, from IEX, 2022-04 on):
  - M0: last 30 days' mean daily VW (persistence: what the market seemed to use)
  - M1: M0 x median ratio (month m / previous 30 days) over earlier years for the same
    calendar month (seasonal ratio)
  - M2: same month last year x (last 90 days / same 90 days last year) (year-on-year scaling)
  - M3: average of M1 and M2
  Each is evaluated first on pseudo-decisions 2023-04..2025-06 (no futures), then frozen.
- **Signal**: edge = (M_hat - F_T)/F_T with the model chosen on the pre-futures period.
- **Entry**: on the first day in the window with 10+ trades and |edge| > k x sigma_M (sigma_M
  from the pre-futures error of that model at that horizon), k = 1.
- **Exit**: hold to expiry. **Sizing**: 1 lot. **Holding**: 25-45 days.
- **Fails if**: the chosen model's error on the 14 futures months is not smaller than the
  futures' own error from the same dates; or PnL <= 0 after costs.

### H3: risk premium

- **Predicts**: E[F_T - S] > 0.
- **Rule**: short the next contract at the settlement of the first day it has 10+ trades in
  the month before delivery; hold to expiry. One trade per contract.
- **Fails if**: mean (F_T - S)/S over the 14 contracts has a one-sided p > 0.10, or the sign
  is unstable between the first and second half of the sample.

### H4: price-discovery lag

- **Predicts**: r_{T+1} = (F_{T+1} - F_T)/F_T for the near contract.
- **Signal**: news_T = change in S_hat (H1 model R0) from T-1 to T, from the new DAM day.
- **Test**: regression of r_{T+1} on news_T and on news_{T+1} (contemporaneous) on
  consecutive liquid days; clustered by contract.
- **Rule** (only if the lag coefficient is > 0 with t > 2): long if news_T > 0.5% else
  short if < -0.5%, hold one day.
- **Fails if**: lag coefficient t < 2, or the contemporaneous coefficient already captures
  most of the move (ratio lag/contemporaneous < 0.2).

### H5: weather-augmented H2

- **Predicts**: next-month index, adding forecast temperature anomalies at 8 load centres.
- **Data**: Open-Meteo historical forecast archive (forecast vintages, no look-ahead) and
  ERA5 actuals for climatology. Only forecasts issued before T are used.
- **Fails if**: adding weather does not reduce the pre-futures pseudo-out-of-sample error of
  the H2 model by at least 10%; then it is not tested on futures.

## Multiple testing

Five pre-registered hypotheses, a few variants each. A result is called promising only if
it passes its own falsification test **and** its p-value survives a Bonferroni factor of 5.
Everything tested is reported, including failures.
