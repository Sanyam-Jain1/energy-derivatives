"""Day-to-day returns of the near and next contracts against information known at the prior close.

H4 (price-discovery lag), H7 (reversal after big moves), H8 (momentum), H12 (weekday),
H16 (open interest), H1-style basis mean reversion. Standard errors clustered by contract.

    python -m research.daily
"""

import logging

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import data, forecast, settlement
from .config import RESULTS

log = logging.getLogger("daily")


def fair_value(iex, contract, expiry, t, ar_params):
    """Estimate of the contract's settlement at the close of t: known days + AR forecast of the
    rest inside the delivery month; last 30 days' mean before it (the frozen H1/H2 models)."""
    m = pd.Period(contract, "M")
    kp = settlement.known_part(iex, contract, expiry, t)
    hist = iex.loc[:pd.Timestamp(t) + pd.Timedelta(days=1)]
    if kp.n_known == 0:
        return forecast.m0_last30(hist, m)
    first, last = settlement.settlement_window(contract, expiry)
    future = pd.date_range(hist.index[-1] + pd.Timedelta(days=1), last)
    return kp.estimate(forecast.r2_ar(hist, future, ar_params)) if kp.n_rest else kp.known_sum / kp.n_days


def panel():
    """Research panel: rows where today, yesterday and tomorrow are all liquid."""
    p = features()
    ok = p.liquid & p.next_liquid & p.prev_liquid & p.ret_next.notna() & p.ret_now.notna()
    return p[ok].copy()


def features(contracts=None):
    """Every near/next contract-day with the features known at its close (no filtering)."""
    iex, fut = data.iex_daily(), data.futures()
    fut = fut[fut.trade_date < fut.expiry]
    # rank contracts by expiry each day: 0 = near, 1 = next
    fut["rank"] = fut.groupby("trade_date").expiry.rank(method="dense").astype(int) - 1
    fut = fut[fut["rank"] <= 1].copy()
    params = {}
    rows = []
    for c, g in fut.groupby("contract"):
        if contracts is not None and c not in contracts:
            continue
        g = g.sort_values("trade_date")
        m = pd.Period(c, "M")
        if c not in params:
            params[c] = forecast.fit_ar(iex.loc[:m.start_time - pd.Timedelta(days=60)])
        g["fair"] = [fair_value(iex, c, g.expiry.iloc[0], t, params[c]) for t in g.trade_date]
        g["liquid"] = g.trades >= 10
        g["ret_next"] = g.settle.shift(-1) / g.settle - 1
        g["next_liquid"] = g.liquid.shift(-1, fill_value=False)
        g["ret_now"] = g.settle / g.settle.shift(1) - 1
        g["prev_liquid"] = g.liquid.shift(1, fill_value=False)
        g["ret_5d"] = g.settle / g.settle.shift(5) - 1
        g["news_now"] = g.fair / g.fair.shift(1) - 1          # fair-value change from DAM published on t
        g["news_next"] = g.news_now.shift(-1)                  # contemporaneous with ret_next
        g["basis"] = g.fair / g.settle - 1
        g["oi_chg"] = g.open_interest_lots / g.open_interest_lots.shift(1) - 1
        g["next_weekday"] = g.trade_date.shift(-1).dt.dayofweek
        rows.append(g)
    return pd.concat(rows)


def reg(p, y, xs, label):
    d = p[[y, *xs, "contract"]].replace([np.inf, -np.inf], np.nan).dropna()
    X = sm.add_constant(d[xs].astype(float))
    fit = sm.OLS(d[y], X).fit(cov_type="cluster", cov_kwds={"groups": d.contract.astype("category").cat.codes})
    print(f"\n{label}: n={len(d)} days, {d.contract.nunique()} contracts, R2={fit.rsquared:.3f}")
    print(pd.DataFrame({"coef": fit.params, "t": fit.tvalues, "p": fit.pvalues}).round(4).to_string())
    return fit


def main():
    p = panel()
    p.to_csv(RESULTS / "daily_panel.csv", index=False)
    for rank, name in [(0, "NEAR"), (1, "NEXT")]:
        q = p[p["rank"] == rank]
        print(f"\n=================== {name} contract ===================")
        reg(q, "ret_next", ["news_now", "news_next"], "H4 lag: next-day return on today's vs tomorrow's fair-value news")
        reg(q, "ret_next", ["basis"], "Basis: next-day return on (fair - price)/price")
        reg(q, "ret_next", ["ret_now"], "H7/H8: next-day return on today's return")
        big = q.ret_now.abs() > 0.06
        print(f"\nH7 after |move| > 6%: n={big.sum()}, mean next-day return when today up {q[big & (q.ret_now>0)].ret_next.mean():.4f} "
              f"(n={(big & (q.ret_now>0)).sum()}), when down {q[big & (q.ret_now<0)].ret_next.mean():.4f} (n={(big & (q.ret_now<0)).sum()})")
        reg(q, "ret_next", ["ret_5d"], "H8 momentum: next-day return on last 5 days' return")
        reg(q, "ret_next", ["oi_chg"], "H16: next-day return on today's open-interest change")
        q = q.assign(mon=(q.next_weekday == 0).astype(float))
        reg(q, "ret_next", ["mon"], "H12: next trading day is a Monday")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()


def h4_rule(threshold=0.005):
    """Pre-registered: near contract; long if today's fair-value news > +0.5%, short if < -0.5%;
    hold one day (exit at the next liquid day's settlement)."""
    from . import backtest, metrics
    from .config import Costs
    p = pd.read_csv(RESULTS / "daily_panel.csv", parse_dates=["trade_date", "expiry"], dtype={"contract": str})
    fut, con = data.futures(), data.contracts()
    book = backtest.Book(fut, con.final_settle.dropna().to_dict())
    q = p[(p["rank"] == 0) & (p.news_now.abs() > threshold)].sort_values("trade_date")
    nxt = fut.set_index(["contract", "trade_date"]).sort_index()
    trades = []
    for r in q.itertuples():
        later = nxt.loc[r.contract]
        later = later[later.index > r.trade_date]
        if len(later):
            trades.append(backtest.Trade(r.contract, r.trade_date, int(np.sign(r.news_now)), 1, later.index[0], tag="H4"))
    for k in (0, 1, 2):
        costs = Costs().scaled(k) if k else Costs(0, 0, 0, 0, 0, 0)
        res, pnl = backtest.run(trades, book, costs)
        s = metrics.summarize(res, pnl)
        print(f"\nH4 rule |news| > {threshold:.1%}, costs x{k}: {len(res)} trades")
        print(metrics.fmt(s))
        print(f"  mean per trade {res.net_pct.mean():.3f}%, per-trade t {res.net_pct.mean() / res.net_pct.std() * np.sqrt(len(res)):.2f}")
        if k == 1:
            res = res.sort_values("entry_date")
            h = len(res) // 2
            print(f"  halves (per-trade mean): {res.net_pct.iloc[:h].mean():.3f}% / {res.net_pct.iloc[h:].mean():.3f}%")
            res.to_csv(RESULTS / "h4_trades.csv", index=False)
