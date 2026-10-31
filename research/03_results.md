# Stages 3-8: pipeline, tests, results

31 Oct 2026. Every number here comes from code in `research/` run on the repo's data; outputs
are saved in `research/results/`. Hypotheses and rules were fixed in `02_hypotheses.md`
before the tests; anything exploratory is labelled so.

## Bottom line

**No strategy is statistically established.** After costs, with 14 settled contracts:

- The market prices the published part of the month correctly and is about as accurate as
  our best models both inside the delivery month (H1) and before it (H2).
- The one consistent bias (futures above the final a month ahead, +5.5% on average) faded in
  2026 and does not survive as a trade (H3).
- Weather explains almost none of the month-to-month moves even with perfect hindsight (H5).
- The one real signal is **under-reaction to each day's DAM result** (H4/H15): it is there
  before costs (+1.1% per trade, t 2.4, out of sample), but after realistic costs it is
  +0.2% to +0.6% per trade depending on implementation details, t 0.3-1.3. It is the only
  candidate worth paper trading, and it most likely needs intraday execution right after the
  DAM result (13:00-15:00 IST) to be worth anything.

## Stage 3-4: pipeline and code

| Module | What it does |
|---|---|
| `futures.py` | data: NSE bhavcopy (daily, all contracts), IEX DAM pages, joins; `python futures.py -h` |
| `research/config.py` | fixed settings: costs, lot, margin, calibration period |
| `research/data.py` | loaders; each row carries the date it became public |
| `research/settlement.py` | settlement window, index proxy, known part at a decision date |
| `research/forecast.py` | rest-of-month models R0-R2, next-month models M0-M3; all take only past rows |
| `research/backtest.py` | event-driven: entry at a liquid day's settlement, daily MTM, exit at a later settlement or the final; costs per side |
| `research/metrics.py` | statistics by contract (the independent unit), sign test, drawdown |
| `research/h1.py`, `h2.py`, `daily.py`, `h5.py`, `h15.py` | the tests below |
| `research/weather.py` | ERA5 daily weather for 9 load centres (Open-Meteo) |
| `research/paper.py` | paper trading (Stage 8) |
| `research/tests/` | 10 tests: settlement arithmetic, no look-ahead in every model, backtest and paper accounting, proxy vs NSE finals |

Information timing used everywhere: a decision at the close of day T sees NSE prices to T and
DAM delivery days to T+1. Trades only on days with 10+ trades (otherwise NSE sets the
settlement by formula and nobody could have dealt there). Costs per side: half-spread Rs 5
(NSE market-maker obligation), slippage Rs 5, fees 0.01%, CTT/stamp, brokerage; about 0.56%
per round trip at Rs 4,000.

## Stage 5: results

| # | Hypothesis | Test | Result | Verdict |
|---|---|---|---|---|
| H1 | Delivery month: known days + forecast beats futures | 14 contracts, 286 liquid days; model chosen on 26 pre-futures months (AR(1)+weekday) | MAE model 4.93% vs futures 5.22%; better in 6/14; Wilcoxon p 0.71. Rule +3.4%/contract, t 1.19 (from Mar-Apr 26) | **rejected** |
| H2 | Pre-month: seasonal/recent forecast beats futures | persistence beat all seasonal models on pre-futures data (15.2% vs 19.8-22.9%) so M0 was used | M0 11.3% vs futures 13.7%; better in 6/14; p 0.34. Rule: 4 trades, all +, +14.5% (p 0.03; 0.15 after Bonferroni) | **not established** |
| H3 | Short premium | short a month before delivery, 14 contracts | +3.4%/contract, t 0.71; +7.9% first half, -1.0% second | **rejected** |
| H4 | Lag to DAM news | 317 near-month day pairs | lag coef 0.17 (t 2.47), 29% of same-day; rule +0.40% gross, **-0.17% net** | **fails after costs** |
| H5 | Weather | perfect-hindsight upper bound, 52 months | R2 3-7%; leave-one-out worse than persistence | **rejected** |
| H6 | Calendar spread | 13 near/next pairs | spread predicts the change in finals worse than "no change" (corr 0.15) | **rejected** |
| H7 | Reversal after 6%+ moves | 14 near-month cases | no reversal (next day -0.7% after both up and down moves) | **rejected** |
| H8 | Momentum | 1-day and 5-day | 1-day t 2.27 (part of H4's under-reaction); 5-day t 1.58 | folded into H15 |
| H9 | Volatility regime | not run: 14 contracts cannot separate regimes | n/a | **not testable yet** |
| H10 | Solar strength | not run: only matters through H1/H2, which already match the market | n/a | deferred |
| H11 | Event-driven | no event archive | n/a | **no data** |
| H12 | Weekday | Monday dummy | t -1.14 near, 0.40 next | **rejected** |
| H13 | NSE vs MCX | expired MCX contracts not reachable | n/a | **no data** |
| H14 | ML on daily returns | not run: the linear model already has t ~2 before costs on 225 OOS days; a flexible model would fit noise | n/a | not justified |
| H15 | Hybrid news + basis + momentum, walk-forward | 11 OOS contracts | gross +1.13%/trade (t 2.37, 10/11); net **+0.57% to +0.64%** (t 1.2-1.3, 7/11); paper replay with daily refits **+0.18%** | **best candidate, unproven** |
| H16 | Open-interest change | near/next | near t 1.30; next t 2.94 with a tiny coefficient | **rejected** |
| H17 | DAM bid imbalance | not run (same reason as H10) | n/a | deferred |

Multiple testing: 5 pre-registered hypotheses, ~12 more checks. Nothing passes p < 0.01;
H15's best net t of 1.3 is far from any corrected threshold.

### What the data says about this market (useful even without a strategy)

1. **Settlement**: NSE's final = mean over days of the daily volume-weighted DAM price, across
   exchanges and DAM segments, for days 1..expiry+1. IEX-only proxy error 0.7%.
2. **Daily marks** on days with under 10 trades are tomorrow's spot x e^(rt), not a forecast.
3. **Before delivery** the futures priced "last month + a premium" (+5.5% average a month
   out). The premium was large until May 2026 and gone from June.
4. **Month-to-month moves of the index are ~15% (sd) and mostly unpredictable** from price
   history, seasonality (only Dec and Jan rose in every year) or national weather.
5. **Within the month** the futures track known days + persistence closely; there is no
   arithmetic edge left for a daily-close trader.
6. **The futures under-react to each day's DAM result by about 20-30%** at the close. Too
   small to pay the 0.56% round trip on most days.

## Stage 6: comparison

| Strategy | OOS evidence | Net per trade | Cost sensitivity | Capacity | Complexity |
|---|---|---|---|---|---|
| H15 (news + basis + momentum, 1-day) | 11 contracts walk-forward; 236-day paper replay | +0.18% to +0.64% | breakeven at ~2x assumed costs | 1-3 lots a day near month | low |
| H2 rule (rare large deviations) | 4 trades | +14.5% | negligible | 1 lot | low |
| H1 rule | 11 trades | +3.4% (two trades carry it) | low | 1-3 lots | low |
| H3 short premium | 14 trades | +3.4%, unstable | low | 1-5 lots | trivial |
| H4 rule | 245 trades | -0.17% | fatal | | low |

None is ranked as "works". If one had to be watched, it is H15 (most trades, consistent
gross signal, theory), then H2's rule (economically sensible: trade only when the market is
far from persistence; but four trades prove nothing).

## Stage 7: portfolio

With one weak candidate there is nothing to diversify; combining H15 with H3 would mostly add
the (fading) premium. If H15 is ever deployed: 1 lot per signal; at most 3 lots open; no
trade on days with under 10 trades or within 2 days of expiry; size so that a 9% adverse
day (the price band, Rs 18,000 on a Rs 2 lakh lot at Rs 4,000/MWh) costs under 1% of capital,
i.e. about Rs 18 lakh of capital per lot (the paper ledger uses Rs 10 lakh, so a 9% day is 1.8%
of it); stop new trades after a 15% drawdown (all coded in `paper.py`). Volatility
targeting is not meaningful at one lot.

## Stage 8: paper trading

`research/paper.py` (tested): each day after NSE's bhavcopy is out it closes yesterday's
position at today's settlement, marks open positions, refits H15 on contracts already
expired, checks risk limits and records any new order and fill, appending to
`research/paper/<ledger>/{orders,fills,equity}.csv`. A day is never processed twice.

    python futures.py nse && python futures.py iex --fetch && python futures.py build
    python -m research.paper run

Replay 1 Dec 2025 - 30 Oct 2026: 55 trades, +Rs 20,268 on Rs 10 lakh after Rs 60,782 of
costs (+0.18% per trade), max drawdown 4.1% of capital.

What paper trading needs to settle: (1) fills at or near the settlement price (needs real
quotes; the last-30-minute VWAP may not be achievable); (2) the actual cost (exchange fee
after the waiver, real spread); (3) at least 6 more contracts of live signals before any
real money, given t ~1 now.

## Answers to the ten edge questions (H15)

1. **Predicting**: the near contract's next-day settlement change.
2. **Why**: thin, mostly retail market; most participants trade once a day; DAM results come
   out at 13:00-15:00 and the price only partly adjusts by the close.
3. **Already priced?** About 70-80% of it is, the same day.
4. **Information advantage**: none beyond speed and doing the arithmetic; every input is public.
5. **When available**: DAM results ~13:00-15:00 IST; the futures trade until 23:30.
6. **How fast incorporated**: mostly the same day; the leftover is gone in about a day.
7. **Big enough for costs?** Barely: gross ~1.1% vs ~0.56% cost, net not significant.
8. **Volume**: 1-3 lots a day in the near month without moving the price.
9. **What would stop it**: more market makers or algos (12% algo share already), tighter
   reaction to DAM publication, cost increases.
10. **Abandon if**: after 6 more live contracts the paper ledger's net per trade is <= 0, or
    the gross correlation of prediction and next-day return drops below 0.05.

## What would change the conclusions (data to get)

1. **Intraday futures trades/quotes** (NSE tick data, paid): to test trading right after the
   DAM result instead of at the close. This is the most promising direction.
2. **PXIL and HPX DAM prices, IEX green/high-price segments**: to compute NSE's settlement
   exactly (removes the 0.7% proxy error).
3. **MCX bhavcopy history**: MCX settles on a different index (daily average weighted by
   volume, IEX only); the NSE-MCX spread is a clean, testable relationship.
4. **Grid-India demand, renewable generation, CEA coal stocks**: for better spot forecasts;
   but H5's result suggests demand-side weather alone will not be enough.
5. **Time**: every new contract adds one independent observation. At ~12 a year, the
   sample needed to confirm a 0.5% edge with t > 2 is several years.
