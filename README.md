# energy-derivatives

Daily prices of India's monthly electricity futures, on both exchanges, for research
against the IEX day-ahead market (IEX data lives in the sibling `power_market` repo).

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

## data/futures_daily.csv

One row per exchange, trade date and contract.

| column | meaning |
|---|---|
| exchange | MCX or NSE |
| trade_date | IST |
| contract | delivery month, YYYY-MM |
| expiry | last trading day |
| open, high, low, close | Rs/MWh |
| settle | daily settlement price (NSE only; MCX via Upstox has none) |
| prev_close | NSE only |
| lots, mwh | volume traded; mwh = lots x 50 |
| value_rs | traded value (NSE only) |
| open_interest_lots | open positions at the close |
| trades | number of trades (NSE only) |
| source | the raw file the row came from |

NSE lists a settlement price for every open contract each day, also on days it does
not trade; such a day has lots = 0 and a stale close. MCX volume from Upstox is taken
to be in lots; that is still to be confirmed against an MCX bhavcopy.
