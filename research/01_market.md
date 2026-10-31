# Stage 1: the market

Research notes, 31 Oct 2026. Sources are linked; "verified" means checked against our own
data in this repo, "reported" means taken from a document and not tested.

## 1. What is traded

| | NSE ELECMBL | MCX ELECDMBL |
|---|---|---|
| Launched | 14 Jul 2025 | 10 Jul 2025 |
| Unit | 50 MWh a lot, Rs/MWh, tick Re 1 | same |
| Months listed | about 3 ahead; a new month lists on the 1st business day (verified: 18 contracts, each first listed 3 months before delivery) | current + 2 or 3 (sources differ) |
| Last trading day | business day before the month's last calendar day (verified) | same; closes at 12:00 on expiry day |
| Hours | 09:00-23:30 IST (23:55 in US daylight-saving) | same |
| Settlement | cash only. Nothing is delivered | cash only |
| Final settlement (reported) | daily VWAP of DAM (conventional + green + high-price) across PXIL, IEX and HPX, then averaged over the month's days ([NSE Clearing circular 69054](https://www.archive.nseclearing.in/content/circulars/COM69054.pdf)) | volume-weighted average of IEX DAM UMCP ([MCX launch notes](https://fyers.in/notice-board/launch-of-monthly-electricity-futures-in-commodity-derivatives-segment-nse-mcx)) |
| Daily settlement (reported) | VWAP of last 30 min if 10+ trades; else VWAP of last 10 trades; with under 10 trades in the day, theoretical F = S e^(rt) | not checked |
| Margin | SPAN, 99% VaR, floor by volatility category; +1% ELM; spread benefit at most 75% | ~10% minimum, SPAN |
| Position limits | member 30 lakh MWh or 20% of market OI; client 3 lakh MWh or 5% (reported) | similar |
| Market makers | two paid MMs: 3+ lots each side, spread at most Rs 10/MWh, near and next month ([NSE circular 68807](https://nsearchives.nseindia.com/content/circulars/COM68807.pdf)); scheme for 6 months from Jul 2025, status after that unknown | not checked |
| Costs | exchange fee waived to 31 Dec 2025, current rate unconfirmed; CTT 0.01% on sell side; stamp duty on buy side; brokerage | similar |

### What we verified against data

1. **Final settlement formula.** Against 14 NSE finals (Sep-25 to Oct-26), the best IEX-only
   proxy is the plain mean of each day's IEX volume-weighted price over delivery days 1 to
   expiry + 1: mean absolute error 0.69%, bias +0.18%, sd 0.85%. Three alternatives are
   within 0.2% of it (volume-weighting the days, or using the whole month). The leftover
   ~0.7% is the part of the index we cannot see (PXIL, HPX and IEX's green and high-price
   segments). **Any edge under about 1% is below what this data can detect.**
2. **NSE-set daily prices.** On days with fewer than 10 trades the settlement equals the next
   delivery day's spot price (published that afternoon) times e^(rt): median gap 1.6% at
   r = 6.5%, against 8% on liquid days. So an illiquid contract is marked to tomorrow's spot,
   not to any forecast of its own month. Its mark-to-market noise is the spot's day-to-day
   noise (up to 66% in a day, per NSE).
3. **Volumes.** Our per-contract MWh match NSE's own FY26 review (Aug-25 6.30 million MWh,
   Sep-25 5.98).

### Market size and who trades ([NSE FY26 review](https://nsearchives.nseindia.com//web/mediaattachment/2026-06/Performance_review_for_FY_25-26_-_Electricity_20260630173256.pdf))

- FY26 turnover Rs 11,333 crore, 29.4 million MWh; average open interest ~756 lots (37,800 MWh).
- 907 clients, 133 members; 12.3% algorithmic; hedger participation "nil/negligible".
- NSE's own futures-spot correlation 0.71; hedge effectiveness 0.11 ("not good").
- Our data: a contract trades only from 3-7 weeks after listing; before that its price is set
  by NSE. Near-month volume is 1,000-3,000 lots a day; far months often zero.

Implication: this is a small speculative market. A strategy can realistically trade tens of
lots a day in the near month and a few in the next month, nothing in the third.

## 2. The underlying: Indian power exchanges

- **Day-ahead market (DAM)**, IEX, PXIL, HPX: double-sided closed auction for each of 96
  15-minute blocks of the next day; results out around 13:00-15:00 IST on D-1. Price cap
  Rs 10,000/MWh since Apr 2023 (Rs 20,000 before Apr 2022, Rs 12,000 in between). IEX holds
  most exchange volume (roughly 85-90%, from public reporting; not checked here).
- **Real-time market (RTM)**: 48 half-hour auctions through the day, gate closure about an
  hour before delivery. Not in the futures' settlement.
- **Physical vs financial**: DAM/RTM trades are physical power with scheduling. Futures are
  purely financial and settle on the DAM average. Exchange-traded spot is a small share of
  Indian generation (single-digit percent, from public reporting); most power moves under
  long-term PPAs.

### What drives the DAM price (public reporting; the seasonal pattern is tested in Stage 3)

- **Daily shape**: midday solar pushes prices to Rs 1,000-2,500; evening peaks hit the
  Rs 10,000 cap most days since 2023. The volume-weighted average is pulled toward the cheap
  midday hours, where most volume clears.
- **Seasons**: high in Apr-Jun (heat, pre-monsoon), lower in the monsoon (Jul-Sep: hydro,
  wind, cooler), a dip in Oct-Nov, rising in Dec-Jan (heating, low solar), then March-May up.
- **Fuel**: coal stocks at plants, imported coal and gas prices; outages.
- **Weather**: temperature drives cooling demand; rainfall drives hydro and agricultural load.
- **Policy**: the price cap, market coupling plans, Section 11 orders.

## 3. Where an edge could plausibly come from

1. **Settlement arithmetic.** Inside the delivery month part of the index is already published.
   A trader who computes the known part exactly, and forecasts the rest well, has a
   mechanical advantage over one who does not. The market is small and mostly retail.
2. **Level forecasting.** Before the month, the price looked like "last month plus a premium"
   (earlier analysis). If seasonal and weather information predicts the change, futures that
   anchor to last month can be beaten.
3. **Risk premium.** If speculative longs outnumber shorts, the futures may sit above the
   expected settlement on average.
4. **Microstructure.** NSE-set prices on illiquid days follow spot by formula, not by forecast;
   price limits (6%, then 9%) and margin calls can force moves that later reverse.

What would argue against an edge: 14 settled contracts is a very small sample; the market is
young and its behaviour changed during 2026 (the premium disappeared from June); costs and
the narrow capacity may eat any small edge.

## 4. Data available

| Data | Source | Status |
|---|---|---|
| NSE futures daily OHLC, settlement, volume, OI | NSE bhavcopy archive | **have**, 14 Jul 2025 to 30 Oct 2026 |
| MCX futures | MCX bhavcopy | blocked here; Upstox gives live contracts only (Oct-Dec 26 saved) |
| Intraday futures trades, bid/ask | NSE / data vendors | **not available**; spread proxied by MM obligation (Rs 10) and daily range |
| IEX DAM 15-minute prices, volumes, bids | IEX market snapshot | **have**, Apr 2022 to Oct 2026 |
| IEX RTM 15-minute | IEX | have to Sep 2026 (in power_market) |
| PXIL / HPX DAM | exchange sites | not fetched; small share of volume |
| Weather forecasts and actuals | Open-Meteo (ERA5 archive, historical forecast archive) | reachable but rate-limited here; to try |
| All-India demand, generation by source | Grid-India daily PSP reports | site not reachable from here |
| Coal stocks | CEA daily coal report (PDF) | reachable; not parsed |
| DAM bid volumes (demand/supply proxy) | inside the IEX pages we have | **have** |
