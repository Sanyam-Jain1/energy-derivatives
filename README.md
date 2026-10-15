# energy-derivatives

Daily prices of India's monthly electricity futures, for research against the IEX
day-ahead market (IEX data lives in the sibling `power_market` repo). Current focus:
**NSE, historical data only**. MCX is parked (expired MCX contracts are not reachable
from here); its code and the three contracts already saved stay in the repo unused.

| | MCX | NSE |
|---|---|---|
| Symbol | ELECDMBL | ELECMBL |
| Launched | 10 Jul 2025 | 14 Jul 2025 |
| Lot | 50 MWh | 50 MWh |
| Settles on | IEX DAM daily averages weighted by daily cleared volume | average across the power exchanges |

## Commands

    python futures.py nse [--from 2025-07-14] [--to 2026-10-14]   # NSE daily bhavcopy -> raw/nse/
    python futures.py mcx                                         # MCX contracts still trading, via Upstox
    python futures.py build                                       # raw/ -> data/futures_daily.csv
    python futures.py check                                       # sanity checks, prints findings
    python futures.py iex [--fetch]                               # IEX DAM daily -> data/iex_daily.csv
    python futures.py join                                        # NSE vs IEX known days -> data/nse_vs_iex.csv

Python 3 with pandas. Re-running `nse` fetches only missing days; `mcx` saves a new
snapshot each run.

## Sources

- **NSE:** the daily commodity bhavcopy,
  `nsearchives.nseindia.com/content/com/BhavCopy_NSE_CO_0_0_0_YYYYMMDD_F_0000.csv.zip`.
  Each trading day's ELECMBL rows are saved as published in `raw/nse/elecmbl_YYYYMMDD.csv`
  (the full zip, every commodity, is not kept). Complete from launch.
- **MCX:** MCX's own site refuses scripted requests, so prices come from Upstox's public
  API (`api.upstox.com/v2/historical-candle`), saved as published in `raw/mcx_upstox/`.
  It serves contracts still trading, back to their listing day. **Expired MCX contracts
  are missing**: Upstox serves those only with a logged-in token, and MCX's bhavcopy
  page has to be used in a browser.
- `raw/manifest.csv` logs every request: url, time, HTTP status, bytes, sha256.

## What is in the data (to 14 Oct 2026)

| | NSE | MCX |
|---|---|---|
| Trading days | 322, 14 Jul 2025 to 14 Oct 2026 (5 holidays with no file) | 67, 3 Jul to 14 Oct 2026 |
| Contracts | 18: Aug-25 to Jan-27, every one listed since launch | 3: Oct-26, Nov-26, Dec-26 (Jan-27 not yet traded) |
| Missing | Aug-25 final settlement (blank in NSE's own expiry-day file) | every contract that expired before Oct 2026 |

`data/contracts.csv` has one row per exchange and contract: first listed, first traded,
days traded, total lots, MWh and value, and the final settlement price.

### NSE settles on IEX's volume-weighted price

Every NSE final settlement price is within about 2% of the IEX DAM price weighted by each
15-minute block's cleared volume, in all 13 settled months (Sep-25 to Sep-26). It is not
the simple average: since April 2026 the simple average runs 22-33% higher, because little
volume clears in the evening blocks at the Rs 10,000 cap. So NSE's contract is a different
product from MCX's, not a mispriced copy. The small remaining gap fits NSE averaging
across exchanges rather than IEX alone.

| month | IEX block-VW | NSE final | gap | IEX simple |
|---|---:|---:|---:|---:|
| 2025-09 | 3,438 | 3,453 | +0.4% | 3,580 |
| 2025-10 | 2,859 | 2,800 | -2.1% | 2,669 |
| 2025-11 | 3,217 | 3,244 | +0.8% | 3,069 |
| 2025-12 | 3,825 | 3,859 | +0.9% | 3,920 |
| 2026-01 | 3,823 | 3,880 | +1.5% | 3,865 |
| 2026-02 | 3,559 | 3,545 | -0.4% | 3,582 |
| 2026-03 | 3,881 | 3,911 | +0.8% | 4,200 |
| 2026-04 | 3,850 | 3,899 | +1.3% | 5,257 |
| 2026-05 | 3,804 | 3,831 | +0.7% | 4,885 |
| 2026-06 | 3,901 | 3,899 | -0.1% | 5,168 |
| 2026-07 | 3,818 | 3,814 | -0.1% | 4,996 |
| 2026-08 | 3,622 | 3,674 | +1.4% | 4,881 |
| 2026-09 | 4,890 | 4,949 | +1.2% | 7,343 |

### Checks (`python futures.py check`)

- Every traded row has low <= open, close <= high, and NSE's value / MWh inside the day's range.
- 18 NSE rows trade more than 9% away from the previous day's settlement (list them with
  `check --show 20`). Most are on contracts that trade only now and then, where the
  previous settlement was a theoretical price, but not all (e.g. Feb-26 on 2 Feb 2026).
  Not yet explained; kept as published.

## IEX side

`data/iex_daily.csv`: one row per DAM delivery day from Jun 2025, with the simple and the
volume-weighted (VW) average price, cheapest and dearest block, and cleared MWh. Complete
months are read from `../power_market/raw/dam` with its own parser (set `POWER_MARKET_DIR`
if it lives elsewhere); the current month to date is fetched into `raw/iex/` by
`iex --fetch`.

`data/nse_vs_iex.csv`: one row per NSE contract and trade date. A close on trade date T
knows DAM delivery days up to T+1 (DAM is out by 15:00, NSE trades until 23:30).

| column | meaning |
|---|---|
| days_known, known_mwh, vw_so_far | the delivery month's days known at that close, their MWh and VW price |
| last_7d_vw | VW price of the last 7 known days |
| implied_rest | VW price the unknown days need for the settlement to be right (their volume set to the last 7 days' mean) |
| final_vw | IEX VW over the whole month (complete months) |
| nse_final | NSE's final settlement |

### First look: settlement price vs the final (13 contracts, Sep-25 to Sep-26)

Mean absolute error of NSE's daily settlement price against the contract's final
settlement, next to a naive estimate (known days, rest at the last 7 days' VW price):

| when | rows | rows traded | NSE | naive | NSE bias |
|---|---:|---:|---:|---:|---:|
| 3 months before the month | 256 | 6 | 18.2% | 15.9% | +3.5% |
| 2 months before | 266 | 66 | 18.3% | 15.6% | +4.7% |
| 1 month before | 264 | 250 | 15.1% | 13.9% | +6.6% |
| 1-10 days known | 90 | 90 | 8.1% | 8.7% | +4.0% |
| 11-20 days known | 94 | 94 | 6.1% | 7.3% | +2.4% |
| 21-30 days known | 89 | 89 | 1.6% | 2.1% | +0.4% |

Before the month NSE's price was further off than the naive estimate and sat above the
final on average; inside the month it was slightly closer. Thirteen contracts, with
neighbouring days heavily overlapping, so this is a lead, not a result. Far-month
settlement prices are mostly theoretical (few trades).

## data/futures_daily.csv

One row per exchange, trade date and contract.

| column | meaning |
|---|---|
| exchange | MCX or NSE |
| trade_date | IST |
| contract | delivery month, YYYY-MM |
| expiry | last trading day |
| open, high, low, close | Rs/MWh |
| settle | daily settlement price (NSE only; MCX via Upstox has none). On expiry day it is the final settlement |
| prev_close | NSE only |
| lots, mwh | volume traded; mwh = lots x 50 |
| value_rs | traded value (NSE only) |
| open_interest_lots | open positions at the close |
| trades | number of trades (NSE only) |
| source | the raw file the row came from |

NSE lists a settlement price for every open contract each day, also on days it does
not trade; such a day has lots = 0 and a stale close. MCX volume from Upstox is taken
to be in lots; that is still to be confirmed against an MCX bhavcopy.
