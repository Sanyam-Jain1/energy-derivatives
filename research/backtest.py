"""Event-driven backtest on daily settlement prices.

A trade is entered at the settlement price of a day with 10+ trades (a market price), marked
to market daily at NSE's settlement price, and closed either at a later liquid day's
settlement or at the final settlement on expiry. Costs per side from `config.Costs`.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import LOT_MWH, MARGIN_RATE, MAX_SHARE_OF_DAY, MIN_TRADES_TO_TRADE, Costs

log = logging.getLogger(__name__)


@dataclass
class Trade:
    contract: str
    entry_date: pd.Timestamp
    direction: int          # +1 long, -1 short
    lots: int = 1
    exit_date: pd.Timestamp = None   # None: hold to expiry
    tag: str = ""


class Book:
    """Futures prices by (contract, date) and final settlements by contract."""

    def __init__(self, fut, finals):
        self.fut = fut.set_index(["contract", "trade_date"]).sort_index()
        self.finals = finals

    def row(self, contract, date):
        try:
            return self.fut.loc[(contract, pd.Timestamp(date))]
        except KeyError:
            return None

    def tradable(self, contract, date):
        r = self.row(contract, date)
        return r is not None and r.trades >= MIN_TRADES_TO_TRADE and r.settle > 0

    def path(self, contract, start, end):
        g = self.fut.loc[contract]
        return g.loc[(g.index >= start) & (g.index <= end), "settle"]


def run(trades, book, costs=Costs()):
    """Returns one row per trade with PnL in Rs/MWh, Rs and % of entry price, plus a daily
    portfolio PnL series (Rs) for drawdowns."""
    rows, daily = [], {}
    for t in trades:
        entry = book.row(t.contract, t.entry_date)
        if entry is None or not book.tradable(t.contract, t.entry_date):
            log.warning("skip %s %s: not tradable", t.contract, t.entry_date.date())
            continue
        lots = int(min(t.lots, max(1, np.floor(entry.lots * MAX_SHARE_OF_DAY))))
        expiry = pd.Timestamp(entry.expiry)
        if t.exit_date is not None and pd.Timestamp(t.exit_date) < expiry:
            ex = book.row(t.contract, t.exit_date)
            if ex is None or not book.tradable(t.contract, t.exit_date):
                log.warning("exit %s %s not tradable; holding to expiry", t.contract, t.exit_date)
                exit_date, exit_px, at_expiry = expiry, book.finals.get(t.contract), True
            else:
                exit_date, exit_px, at_expiry = pd.Timestamp(t.exit_date), ex.settle, False
        else:
            exit_date, exit_px, at_expiry = expiry, book.finals.get(t.contract), True
        if exit_px is None or pd.isna(exit_px):
            log.warning("skip %s: no exit price", t.contract)
            continue
        px = entry.settle
        cost = costs.per_mwh(px, t.direction, lots) + costs.per_mwh(exit_px, -t.direction, lots, at_expiry)
        gross = t.direction * (exit_px - px)
        net = gross - cost
        mwh = lots * LOT_MWH
        # daily mark-to-market path (Rs), last day at the exit price
        marks = book.path(t.contract, t.entry_date, exit_date).copy()
        marks.iloc[-1] = exit_px
        steps = marks.diff().fillna(marks.iloc[0] - px) * t.direction * mwh
        steps.iloc[0] -= costs.per_mwh(px, t.direction, lots) * mwh
        steps.iloc[-1] -= costs.per_mwh(exit_px, -t.direction, lots, at_expiry) * mwh
        for d, v in steps.items():
            daily[d] = daily.get(d, 0.0) + v
        worst = (t.direction * (marks - px)).min()
        rows.append({"contract": t.contract, "tag": t.tag, "entry_date": t.entry_date, "exit_date": exit_date,
                     "direction": t.direction, "lots": lots, "entry_px": px, "exit_px": exit_px,
                     "at_expiry": at_expiry, "days_held": int((exit_date - t.entry_date).days),
                     "gross_rs_mwh": gross, "cost_rs_mwh": cost, "net_rs_mwh": net,
                     "net_pct": net / px * 100, "net_rs": net * mwh,
                     "return_on_margin_pct": net / (px * MARGIN_RATE) * 100,
                     "worst_mtm_pct": worst / px * 100})
    res = pd.DataFrame(rows)
    pnl = pd.Series(daily).sort_index() if daily else pd.Series(dtype=float)
    return res, pnl
