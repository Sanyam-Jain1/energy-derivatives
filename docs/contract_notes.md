# Electricity futures in India: notes

Notes as of 9 Oct 2026. Points marked **[checked]** were tested against IEX data in
this repo. Everything else is as reported and not yet verified.

## What they are

- Monthly electricity futures launched July 2025 on MCX (10 Jul) and NSE (14 Jul)
  after SEBI approval. Settled in cash; no power is delivered.
- One contract = 50 MWh, quoted in Rs/MWh, tick Re 1 (Rs 50 per lot).
- Pays on the average day-ahead price for one calendar month, all 24 hours
  (baseload). No peak, weekly or options contracts yet.
- Four contracts open at a time: the current month plus the next three. Each lists
  about 3 months before its month and can be bought or sold on any trading day until expiry.
- Last trading day: business day before month-end; trading stops at noon.
- Daily price limit 6%, widening to 9%. Margin about 10%.
- Hours: 9:00–23:30, Mon–Fri. A daily settlement price each evening is used for
  mark-to-market and margin calls.

## Settlement index

- **MCX [checked]:** the month's daily IEX DAM averages (simple mean of 96 blocks),
  weighted by each day's cleared volume. Reproduces all five known finals within
  Rs 0.5. See [settlement_index.md](settlement_index.md). The earlier "within about
  1% of IEX monthly averages" was a comparison with the simple average.
- **NSE:** averages across all three power exchanges, including green and high-price
  segments. It matched IEX until March 2026, then ran 25–32% below from June 2026
  (Sep-26: NSE 4,949 vs MCX 7,234). **Likely cause [partly checked]:** block-level
  volume weighting. IEX's block-VW price for Sep-26 is 4,890 (+1.2% vs NSE). Treat
  NSE as a different product until this is confirmed.

## Prices so far (Rs/MWh)

MCX finals: Oct-25 2,687; Dec-25 3,932; Jun-26 5,168; Jul-26 4,963; Sep-26 7,234.

IEX DAM monthly, from `data/iex_dam_monthly.csv`:

| month | simple | block VW | MCX index |
|---|---:|---:|---:|
| Aug-25 | 4,001 | 3,990 | 4,058 |
| Sep-25 | 3,580 | 3,438 | 3,604 |
| Oct-25 | 2,669 | 2,859 | 2,687 |
| Nov-25 | 3,069 | 3,217 | 3,089 |
| Dec-25 | 3,920 | 3,825 | 3,932 |
| Jan-26 | 3,864 | 3,823 | 3,833 |
| Feb-26 | 3,582 | 3,559 | 3,595 |
| Mar-26 | 4,200 | 3,881 | 4,134 |
| Apr-26 | 5,257 | 3,850 | 4,920 |
| May-26 | 4,885 | 3,804 | 4,829 |
| Jun-26 | 5,168 | 3,901 | 5,168 |
| Jul-26 | 4,996 | 3,818 | 4,963 |
| Aug-26 | 4,881 | 3,622 | 4,903 |
| Sep-26 | 7,343 | 4,890 | 7,234 |

The reported IEX averages (Jun-26 ~5,200, Jul ~4,990, Aug ~4,880, Sep ~7,300) are
the simple column.

- September 2026 jumped because midday prices rose (cheapest 2 hours ~1,290 in Aug,
  ~2,040 in Sep). Evenings were already at the Rs 10,000 cap. This lifts the monthly
  average but narrows a battery's spread.
- MCX forward curve (8–9 Oct 2026): Oct-26 ~7,200; Nov-26 ~6,270; Dec-26 ~5,870.
  That is 1.5–2.7x the same months last year (backwardation).
- Oct-26 daily closes, 14 Sep–8 Oct 2026: 6812, 7385, 7165, 6525, 6379, 6274, 6334,
  6307, 5740 (limit down), 5710, 6222, 6384, 6356, 6484, 7067, 7049, 7166, 7185.
  Range 5,710–7,385 (29% swing); average daily move ~3.8%; 6 of 18 days moved 8–9%.
  If 2 Oct was a holiday, the limit-down close is 24 Sep. That is the day the DAM
  result for 25 Sep came out at 5,682, after 7,435 the day before; 26–27 Sep then
  fell to 4,299 and 2,756.
- IEX DAM daily average on 8 Oct 2026: 8,032 (futures closed 7,185).
- At launch (Jul 2025) the first contract traded ~4,370–4,430. The Aug-25 MCX index
  came to 4,058, so launch prices were about 8% high (month unconfirmed).

## Market activity

- NSE FY26: ~Rs 11,300 cr turnover, 29.4 million MWh, tiny open interest, 907
  clients. Hedger participation nil or negligible (mostly speculation). NSE's own
  hedge-effectiveness score was poor; futures-spot correlation 0.71.
- MCX record day 4 Sep 2026: Rs 245 cr, 4.2 lakh MWh. MCX is gaining share.

## Key ideas

- Before the month, the futures price is the market's estimate of the index. During
  the month it becomes partly known: estimate = (known volume x index so far +
  remaining volume x expected price) / total volume. At expiry it equals the index.
  This is weighted by volume, because the index is.
- If my forecast is below the futures price, the trade is to sell. It profits only
  if the index ends lower, and margin calls can hit before then.
- My battery backtest (~96% capture) measures timing within a day (the daily shape),
  not the monthly price level. Forecasting the level weeks ahead is much harder
  (weather, hydro and monsoon, coal, new solar, policy such as the Rs 10 cap).
- Realistic edge: within the current month, where the data computes the known part
  exactly. Weak edge 2–3 months ahead. **[checked]** A last-7-days estimate misses by
  15.7% on average before the month, 9.3% at mid-month, and 2.3% with 25 days known.
- Futures are a poor hedge for batteries. They pay on the 24-hour average, while a
  battery earns evening minus midday. That would need an evening-peak or spread
  contract, and none exists.
