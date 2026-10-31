"""Paper trading for the H15 signal (near contract, one-day hold). No real orders.

Each run processes one trading day, after NSE's bhavcopy and IEX's DAM for the next day are out:

    python futures.py nse && python futures.py iex --fetch && python futures.py build
    python -m research.paper run                      # latest trading day in the data
    python -m research.paper replay --from 2026-09-01 # replay past days into a separate ledger

What a run does, in order (all at the day's settlement price, costs from config.Costs):
1. closes positions opened on an earlier day (one-day hold; expiry pays the final settlement),
2. marks open positions to market,
3. refits the model on contracts already expired and computes today's signal,
4. checks risk limits, then opens a position if |predicted return| > THRESHOLD,
5. appends to the ledger: orders.csv, fills.csv, equity.csv in research/paper/<ledger>/.

A date already in equity.csv is never processed twice.
"""

import argparse
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import daily, data
from .config import LOT_MWH, MAX_SHARE_OF_DAY, MIN_TRADES_TO_TRADE, ROOT, Costs

log = logging.getLogger("paper")
FEATURES = ["news_now", "basis", "ret_now"]     # H15, no intercept (research/RESEARCH_LOG.md)


@dataclass(frozen=True)
class Rules:
    threshold: float = 0.006          # trade when |predicted next-day return| > 0.6%
    lots: int = 1
    max_open_lots: int = 3
    capital_rs: float = 1_000_000.0   # paper capital allocated
    max_drawdown: float = 0.15        # halt new trades after a 15% drawdown of capital
    min_days_to_expiry: int = 2
    min_train_contracts: int = 4


def fit(rows, asof):
    """Coefficients from contract-days of contracts that expired before `asof` (no look-ahead)."""
    train = rows[(rows.expiry < asof) & rows.liquid & rows.next_liquid & rows.prev_liquid]
    train = train.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES + ["ret_next"])
    if train.contract.nunique() < Rules.min_train_contracts:
        return None
    b, *_ = np.linalg.lstsq(train[FEATURES].values, train.ret_next.values, rcond=None)
    return b


class Ledger:
    def __init__(self, name):
        self.dir = ROOT / "research" / "paper" / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.orders, self.fills, self.equity = (self._load(n) for n in ("orders", "fills", "equity"))

    def _load(self, name):
        path = self.dir / f"{name}.csv"
        return pd.read_csv(path, parse_dates=["date"]) if path.exists() else pd.DataFrame()

    def save(self):
        for name in ("orders", "fills", "equity"):
            getattr(self, name).to_csv(self.dir / f"{name}.csv", index=False)

    def add(self, name, row):
        setattr(self, name, pd.concat([getattr(self, name), pd.DataFrame([row])], ignore_index=True))

    def open_positions(self):
        if self.fills.empty:
            return pd.DataFrame()
        f = self.fills
        opened = f[f.action == "open"].set_index("position_id")
        closed = set(f[f.action == "close"].position_id)
        return opened[~opened.index.isin(closed)]


def run_day(day, rows, fut, finals, ledger, rules=Rules(), costs=Costs()):
    day = pd.Timestamp(day)
    if not ledger.equity.empty and (ledger.equity.date == day).any():
        log.info("%s already processed", day.date())
        return
    today = fut[fut.trade_date == day].set_index("contract")
    realised = 0.0
    # 1. close positions opened earlier (one-day hold)
    for pid, pos in ledger.open_positions().iterrows():
        c = pos.contract
        expired = day >= pd.Timestamp(pos.expiry)
        if expired:
            px, at_exp = finals.get(c), True
        elif c in today.index and today.loc[c].trades >= MIN_TRADES_TO_TRADE:
            px, at_exp = today.loc[c].settle, False
        else:
            continue  # not liquid today: keep holding, close on the next liquid day
        if px is None or pd.isna(px):
            continue
        cost = costs.per_mwh(px, -pos.side, pos.lots, at_expiry=at_exp)
        pnl = (pos.side * (px - pos.price) - cost) * pos.lots * LOT_MWH
        realised += pnl
        ledger.add("fills", {"date": day, "position_id": pid, "action": "close", "contract": c, "side": -pos.side,
                             "lots": pos.lots, "price": px, "cost_rs": cost * pos.lots * LOT_MWH, "pnl_rs": pnl,
                             "expiry": pos.expiry})
    # 2. mark open positions
    unrealised = 0.0
    for _, pos in ledger.open_positions().iterrows():
        if pos.contract in today.index:
            unrealised += pos.side * (today.loc[pos.contract].settle - pos.price) * pos.lots * LOT_MWH
    prev_eq = ledger.equity.equity_rs.iloc[-1] if not ledger.equity.empty else rules.capital_rs
    prev_unr = ledger.equity.unrealised_rs.iloc[-1] if not ledger.equity.empty else 0.0
    equity = prev_eq - prev_unr + realised + unrealised
    peak = max(ledger.equity.equity_rs.max() if not ledger.equity.empty else rules.capital_rs, equity)
    halted = (peak - equity) / rules.capital_rs > rules.max_drawdown
    # 3. signal for today's near contract
    b = fit(rows, day)
    near = rows[(rows.trade_date == day) & (rows["rank"] == 0)]
    decision, pred, contract = "no signal", np.nan, None
    if b is None:
        decision = "not enough expired contracts to fit"
    elif near.empty:
        decision = "no near contract row"
    else:
        r = near.iloc[0]
        contract = r.contract
        x = r[FEATURES].astype(float).values
        if not np.all(np.isfinite(x)):
            decision = "features missing"
        else:
            pred = float(x @ b)
            # 4. risk checks
            open_lots = ledger.open_positions().lots.sum() if not ledger.open_positions().empty else 0
            if abs(pred) <= rules.threshold:
                decision = "below threshold"
            elif not r.liquid:
                decision = "contract not liquid today (<10 trades)"
            elif not r.prev_liquid:
                decision = "previous day not liquid (return is from an NSE-set price)"
            elif (pd.Timestamp(r.expiry) - day).days < rules.min_days_to_expiry:
                decision = "too close to expiry"
            elif halted:
                decision = "halted: drawdown limit"
            elif open_lots + rules.lots > rules.max_open_lots:
                decision = "position limit"
            else:
                lots = int(min(rules.lots, max(1, np.floor(r.lots * MAX_SHARE_OF_DAY))))
                side = int(np.sign(pred))
                px = float(r.settle)
                cost = costs.per_mwh(px, side, lots)
                pid = f"{day:%Y%m%d}-{contract}"
                ledger.add("fills", {"date": day, "position_id": pid, "action": "open", "contract": contract,
                                     "side": side, "lots": lots, "price": px, "cost_rs": cost * lots * LOT_MWH,
                                     "pnl_rs": -cost * lots * LOT_MWH, "expiry": r.expiry})
                equity -= cost * lots * LOT_MWH
                decision = f"opened {'long' if side > 0 else 'short'} {lots} lot"
    ledger.add("orders", {"date": day, "contract": contract, "predicted_return": pred, "decision": decision})
    ledger.add("equity", {"date": day, "equity_rs": equity, "realised_rs": realised, "unrealised_rs": unrealised,
                          "drawdown_pct": (peak - equity) / rules.capital_rs * 100})
    log.info("%s %s pred=%s -> %s; equity %.0f", day.date(), contract, f"{pred:+.4f}" if np.isfinite(pred) else "-",
             decision, equity)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="process the latest trading day into the live ledger")
    rp = sub.add_parser("replay", help="process past days into the replay ledger")
    rp.add_argument("--from", dest="start", required=True)
    rp.add_argument("--to", dest="end")
    args = ap.parse_args()
    fut = data.futures()
    finals = data.contracts().final_settle.dropna().to_dict()
    rows = daily.features()
    if args.cmd == "run":
        ledger, days = Ledger("live"), [fut.trade_date.max()]
    else:
        ledger = Ledger("replay")
        days = sorted(d for d in fut.trade_date.unique() if d >= pd.Timestamp(args.start)
                      and (args.end is None or d <= pd.Timestamp(args.end)))
    for d in days:
        run_day(d, rows, fut, finals, ledger)
    ledger.save()
    eq = ledger.equity
    print(f"{ledger.dir.relative_to(ROOT)}: {len(eq)} days, equity Rs {eq.equity_rs.iloc[-1]:,.0f}, "
          f"max drawdown {eq.drawdown_pct.max():.2f}% of capital, trades {int((ledger.fills.action == 'open').sum()) if not ledger.fills.empty else 0}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
