# energy-derivatives

Research on India's monthly electricity futures (MCX, NSE): what they settle on, how
their price relates to the IEX day-ahead market, and whether there is a tradable edge.
This is separate from the battery backtester in the sibling `power_market` repo, but
reuses its raw IEX data and parser.

Background on the contracts, prices so far and the ideas being tested:
[docs/contract_notes.md](docs/contract_notes.md).

## Setup

Clone `power_market` next to this repo (or set `POWER_MARKET_DIR`). Python 3 with pandas.

    ../power_market/raw/dam/dam_YYYY-MM.html   complete months of IEX DAM (from bess.py fetch)
    raw/dam/dam_YYYY-MM_to_DD.html             partial current month (from futures.py fetch)

## Commands

    python futures.py daily                  # raw IEX pages -> data/iex_dam_daily.csv
    python futures.py index                  # monthly settlement index vs MCX/NSE finals
    python futures.py fairvalue --month 2026-10 [--as-of 2026-10-08] [--rest 7000]
    python futures.py convergence            # how fast a month's index becomes known
    python futures.py fetch --month 2026-10  # current month to date from IEX

`fairvalue` treats a close on trading day T as knowing DAM delivery days up to T+1
(DAM results are out by 15:00, MCX trades until 23:30). For each close it prints
the estimate (known days, plus the rest at the last-7-day level or `--rest`) and the
average the unknown days would need for that close to equal the final index.

## Data

| file | what | how made |
|---|---|---|
| `data/iex_dam_daily.csv` | one row per delivery day: simple and volume-weighted price, min, max, cleared and scheduled MWh | `daily` |
| `data/iex_dam_monthly.csv` | MCX index, simple average, block volume-weighted average, exchange finals | `index` |
| `data/convergence_errors.csv` | estimate error vs final, every month and number of known days | `convergence` |
| `data/mcx_settlements.csv` | MCX final settlement prices | by hand from notes |
| `data/nse_settlements.csv` | NSE final settlement prices | by hand from notes |
| `data/mcx_daily.csv` | MCX daily closes | by hand from notes; replace with bhavcopy |

The Oct-26 closes in `mcx_daily.csv` came as a list of 18 values for 14 Sep to 8 Oct.
Dates were assigned assuming 2 Oct (Gandhi Jayanti) was a holiday, and are marked
`date_inferred = 1` until checked against the bhavcopy. Nov-26 and Dec-26 are the
approximate forward-curve levels from 8–9 Oct.

## Findings so far

1. **MCX settlement formula reproduced exactly.** The final price is the month's daily
   IEX DAM averages weighted by each day's cleared volume. That matches all five known
   MCX finals within Rs 0.5/MWh. It is neither the simple average (off by up to Rs 109)
   nor the block-level volume-weighted price (off by up to Rs 2,344).
   See [docs/settlement_index.md](docs/settlement_index.md).
2. **The NSE gap is probably volume weighting, not a different market.** IEX's
   block-level volume-weighted price for Sep-26 is 4,890, within 1.2% of NSE's 4,949.
   Since April 2026 little volume clears in the capped evening blocks, so a
   volume-weighted price sits 25–33% below the time average. This is one data point,
   and NSE monthly finals are needed to confirm it.
3. **Most of a month's price stays unknown until late in the month.** Take the known
   days plus "the rest looks like the last 7 days". Before the month starts, that
   estimate misses the final index by 15.7% on average (90th percentile 31%). With 14
   days known it misses by 9.3%, with 21 days by 4.5%, and with 25 days by 2.3%
   (41 months, May 2023 to Sep 2026). This is the benchmark the futures price has to
   beat, and the within-month edge only gets sharp in the last 10 days or so.

## Next steps

- [ ] Fetch October 2026 to date (`fetch --month 2026-10`, then `daily`). The IEX,
      MCX and NSE sites are blocked from the cloud environment this was built in,
      so run it locally.
- [ ] Get MCX bhavcopy for every contract since Jul 2025 to replace the hand-entered
      closes and check the inferred dates.
- [ ] Get NSE monthly finals to test the volume-weighting explanation (finding 2).
- [ ] With real daily closes, compare each close with the estimate and with what
      the close implies for the remaining days. Test whether the futures move
      after the DAM results are published (a lag) or before them.
- [ ] Paper-trade the within-month rule before risking money.
