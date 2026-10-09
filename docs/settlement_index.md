# What the futures settle on

Checked 2026-10-09 with `python futures.py index` against IEX DAM data in
`power_market/raw/dam` (blocks parsed by `bess.parse_snapshot`).

## MCX

Three candidate monthly averages of the IEX DAM clearing price (MCP):

- **simple**: mean of every 15-minute block price in the month (IEX's published monthly "Avg").
- **block VW**: sum(MCP x MCV) / sum(MCV) over every block.
- **index**: each day's simple average, weighted by that day's total cleared volume:
  `sum(day_avg x day_MCV) / sum(day_MCV)`.

| month | MCX final | index | err | simple | err | block VW | err |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-10 | 2,687 | 2,687.5 | -0.5 | 2,669.0 | +18 | 2,859.0 | -172 |
| 2025-12 | 3,932 | 3,932.4 | -0.4 | 3,919.6 | +12 | 3,825.2 | +107 |
| 2026-06 | 5,168 | 5,168.3 | -0.3 | 5,168.2 | -0 | 3,901.4 | +1,267 |
| 2026-07 | 4,963 | 4,963.1 | -0.1 | 4,995.8 | -33 | 3,818.4 | +1,145 |
| 2026-09 | 7,234 | 7,233.7 | +0.3 | 7,342.7 | -109 | 4,889.8 | +2,344 |

Rs/MWh; err = MCX final - candidate. The index is within rounding (Rs 0.5) every
month. Weighting by final scheduled volume instead gives the same within Rs 1
(Jul-26: 4,962.2), so cleared volume fits slightly better.

What this means:

- High-volume days count more. In Sep-26 the cheap, high-volume days at month end
  (26–28 Sep) pulled the index to 7,234, below the simple average of 7,343. So a
  forecast of the settlement needs daily volumes as well as daily prices.
- The earlier note that MCX "matches IEX monthly averages within about 1%" was
  comparing against the simple average. The gap is up to 1.5% and has a known cause.
- Before the month starts, a buyer or seller is exposed to this exact index, so it is
  what `fairvalue` and `convergence` compute.

## NSE

NSE averages across all three power exchanges, including green and high-price
segments. Its Sep-26 final was 4,949, and IEX's block-VW price for Sep-26 is 4,890
(+1.2%). The MCX-style index is 7,234 (-31.6%).

Working explanation: NSE weights by volume at block level (across exchanges). Since
April 2026 little volume clears in the evening blocks priced at the Rs 10,000 cap, so
block-weighted prices sit far below time averages:

| month | simple | block VW | VW below simple |
|---|---:|---:|---:|
| 2026-03 | 4,200 | 3,881 | 7.6% |
| 2026-04 | 5,257 | 3,850 | 26.8% |
| 2026-06 | 5,168 | 3,901 | 24.5% |
| 2026-07 | 4,996 | 3,818 | 23.6% |
| 2026-09 | 7,343 | 4,890 | 33.4% |

That fits the reported "matched IEX until March 2026, then 25–32% below from June".
It is still a hypothesis: one exact NSE final and a reported range. Monthly NSE
finals are needed to confirm it. If it holds, NSE is a different product: a contract
on the volume-weighted price, which moves with midday solar prices far more than MCX does.
