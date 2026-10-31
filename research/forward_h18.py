"""H18 forward test (pre-registered in 02_hypotheses.md): no backtest, only contracts that
settle after 31 Oct 2026. Run daily after the data update; it records at most one signal per
contract and settles it at expiry.

    python -m research.forward_h18
"""

import numpy as np
import pandas as pd

from . import data, forecast
from .config import ROOT, Costs, LOT_MWH, MIN_TRADES_TO_TRADE

LEDGER = ROOT / "research" / "paper" / "h18" / "signals.csv"
FIRST_CONTRACT = "2026-11"
THRESHOLD = 0.05
DAYS_BEFORE = 15


def main():
    fut, iex, con = data.futures(), data.iex_daily(), data.contracts()
    led = pd.read_csv(LEDGER, dtype={"contract": str}) if LEDGER.exists() else pd.DataFrame(
        columns=["contract", "signal_date", "x", "side", "entry_px", "final", "net_pct"])
    days = sorted(fut.trade_date.unique())
    for c in sorted(fut.contract.unique()):
        if c < FIRST_CONTRACT or c in set(led.contract):
            continue
        start = pd.Period(c, "M").start_time
        before = [d for d in days if d < start]
        if len(before) < DAYS_BEFORE:
            continue
        g = fut[(fut.contract == c) & (fut.trade_date >= before[-DAYS_BEFORE]) & (fut.trade_date < start)
                & (fut.trades >= MIN_TRADES_TO_TRADE)].sort_values("trade_date")
        if g.empty:
            continue
        r = g.iloc[0]
        hist = iex.loc[:r.trade_date + pd.Timedelta(days=1)]
        x = float(np.log(forecast.m0_last30(hist, c) / r.settle))
        side = int(np.sign(x)) if abs(x) > THRESHOLD else 0
        led.loc[len(led)] = [c, r.trade_date.date(), round(x, 4), side, r.settle, np.nan, np.nan]
        print(f"{c}: signal on {r.trade_date.date()} x={x:+.3f} -> {['short', 'no trade', 'long'][side + 1]}")
    # settle what has expired
    for i, r in led.iterrows():
        if pd.isna(r.final) and r.contract in con.index and pd.notna(con.loc[r.contract, "final_settle"]):
            final = con.loc[r.contract, "final_settle"]
            led.loc[i, "final"] = final
            if r.side:
                cost = Costs().per_mwh(r.entry_px, r.side) + Costs().per_mwh(final, -r.side, at_expiry=True)
                led.loc[i, "net_pct"] = (r.side * (final - r.entry_px) - cost) / r.entry_px * 100
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    led.to_csv(LEDGER, index=False)
    print(f"{LEDGER.relative_to(ROOT)}: {len(led)} contracts recorded, {led.net_pct.notna().sum()} settled")


if __name__ == "__main__":
    main()
