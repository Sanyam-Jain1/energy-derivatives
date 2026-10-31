"""H15 (hybrid, walk-forward): predict the near contract's next-day return from today's
fair-value news, the fair-value basis and today's return, with coefficients fitted only on
contracts that expired before the one being traded. Trade only when |prediction| exceeds the
round-trip cost.

    python -m research.h15
"""

import logging

import numpy as np
import pandas as pd

from . import backtest, data, metrics
from .config import Costs, RESULTS

FEATURES = ["news_now", "basis", "ret_now"]
MIN_TRAIN_CONTRACTS = 4


def main():
    p = pd.read_csv(RESULTS / "daily_panel.csv", parse_dates=["trade_date", "expiry"], dtype={"contract": str})
    p = p[p["rank"] == 0].replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES + ["ret_next"])
    fut, con = data.futures(), data.contracts()
    book = backtest.Book(fut, con.final_settle.dropna().to_dict())
    nxt = fut.set_index(["contract", "trade_date"]).sort_index()
    order = p.groupby("contract").expiry.first().sort_values()
    preds = []
    for i, c in enumerate(order.index):
        train = p[p.expiry < order[c]]          # only contracts already expired when c trades
        train = train[train.trade_date < p[p.contract == c].trade_date.min()]
        if train.contract.nunique() < MIN_TRAIN_CONTRACTS:
            continue
        X = np.column_stack([np.ones(len(train)), train[FEATURES].values])
        b, *_ = np.linalg.lstsq(X, train.ret_next.values, rcond=None)
        test = p[p.contract == c].copy()
        test["pred"] = np.column_stack([np.ones(len(test)), test[FEATURES].values]) @ b
        test["train_contracts"] = train.contract.nunique()
        preds.append(test)
    q = pd.concat(preds)
    ic = q[["pred", "ret_next"]].corr().iloc[0, 1]
    print(f"walk-forward: {q.contract.nunique()} test contracts ({q.contract.min()}..{q.contract.max()}), {len(q)} days; "
          f"correlation(pred, next-day return) = {ic:.3f}")
    for thr in (0.003, 0.006, 0.01):
        trades = []
        for r in q[q.pred.abs() > thr].itertuples():
            later = nxt.loc[r.contract]
            later = later[later.index > r.trade_date]
            if len(later):
                trades.append(backtest.Trade(r.contract, r.trade_date, int(np.sign(r.pred)), 1, later.index[0], tag="H15"))
        for k in (0, 1):
            res, pnl = backtest.run(trades, book, Costs().scaled(k) if k else Costs(0, 0, 0, 0, 0, 0))
            if res.empty:
                continue
            t = res.net_pct.mean() / res.net_pct.std() * np.sqrt(len(res))
            pc = res.groupby("contract").net_pct.sum()
            print(f"  |pred| > {thr:.1%}, costs x{k}: {len(res)} trades, {res.net_pct.mean():+.3f}% per trade (t {t:+.2f}), "
                  f"{(pc > 0).sum()}/{len(pc)} contracts positive, total Rs {res.net_rs.sum():,.0f}, "
                  f"max DD Rs {metrics.summarize(res, pnl).get('max_drawdown_rs', 0):,.0f}")
    q.to_csv(RESULTS / "h15_walkforward.csv", index=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    main()
