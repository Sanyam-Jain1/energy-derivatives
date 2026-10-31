"""H2: next month's settlement forecast before the month starts, vs the futures price.
H3: the risk premium (short the next contract a month before delivery).

    python -m research.h2 calibrate   # pre-futures months: choose among M0-M3
    python -m research.h2 futures     # futures months: model vs futures; H2 and H3 trading rules
"""

import json
import logging
import sys

import numpy as np
import pandas as pd
from scipy import stats

from . import backtest, data, forecast, metrics, settlement
from .config import CALIBRATION_END, CALIBRATION_START, RESULTS, Costs
from .h1 import pseudo_expiry

log = logging.getLogger("h2")
HORIZONS = [35, 25, 15, 7]          # calendar days before the delivery month starts (pre-futures)


def hbucket(days_before):
    return pd.cut(days_before, [0, 10, 20, 30, 60], labels=["1-10", "11-20", "21-30", "31-60"]).astype(str)


def predict_all(iex, month, decision_date):
    hist = iex.loc[:pd.Timestamp(decision_date) + pd.Timedelta(days=1)]   # DAM up to D+1
    return {name: fn(hist, month) for name, fn in forecast.MONTH_MODELS.items()}


def calibrate():
    iex = data.iex_daily()
    months = pd.period_range(CALIBRATION_START[:7], CALIBRATION_END[:7], freq="M")[1:]
    rows = []
    for m in months:
        c = str(m)
        truth = settlement.index_proxy(iex, c, pseudo_expiry(c))
        for h in HORIZONS:
            t = m.start_time - pd.Timedelta(days=h)
            p = predict_all(iex, m, t)
            rows.append({"contract": c, "days_before": h, "truth": truth,
                         **{k: (v / truth - 1) * 100 for k, v in p.items()}})
    e = pd.DataFrame(rows)
    names = list(forecast.MONTH_MODELS)
    tab = e.groupby("days_before")[names].agg(lambda x: x.abs().mean())
    overall = e[names].abs().mean()
    best = overall.idxmin()
    print(f"pre-futures: {len(months)} months {months[0]}..{months[-1]}; mean absolute error (%) by days before month start")
    print(tab.round(2).to_string())
    print("overall:", overall.round(2).to_dict(), "-> chosen:", best)
    print("bias (mean error %):", e[names].mean().round(2).to_dict())
    sigma = {b: float(e[hbucket(e.days_before) == b][best].std()) for b in ["1-10", "11-20", "21-30", "31-60"]}
    (RESULTS / "h2_calibration.json").write_text(json.dumps({"model": best, "sigma_pct_by_bucket": sigma}, indent=1))
    print("sigma by bucket:", {k: round(v, 2) for k, v in sigma.items()})


def futures_test():
    cal = json.loads((RESULTS / "h2_calibration.json").read_text())
    model, sigma = cal["model"], cal["sigma_pct_by_bucket"]
    iex, fut, con = data.iex_daily(), data.futures(), data.contracts()
    settled = con[con.final_settle.notna()]
    book = backtest.Book(fut, settled.final_settle.to_dict())
    rows = []
    for c, k in settled.iterrows():
        m = pd.Period(c, "M")
        g = fut[(fut.contract == c) & (fut.trade_date < m.start_time) & (fut.trades >= 10)]
        for r in g.itertuples():
            p = predict_all(iex, m, r.trade_date)
            rows.append({"contract": c, "date": r.trade_date, "settle": r.settle, "final": k.final_settle,
                         "days_before": (m.start_time - r.trade_date).days, **p})
    e = pd.DataFrame(rows)
    names = list(forecast.MONTH_MODELS)
    for n in names + ["settle"]:
        e[n + "_err"] = (e[n] / e.final - 1) * 100
    e["bucket"] = hbucket(e.days_before)
    tab = e.groupby("bucket").agg(days=("final", "size"), contracts=("contract", "nunique"),
                                  **{n: (n + "_err", lambda x: x.abs().mean()) for n in names + ["settle"]})
    print(f"H2 futures period: {e.contract.nunique()} contracts, {len(e)} liquid days before delivery")
    print("mean absolute error vs final (%), 'settle' = the futures price:")
    print(tab.round(2).to_string())
    print("bias (mean error %):", {n: round(e[n + "_err"].mean(), 2) for n in names + ["settle"]})
    pc = e.groupby("contract").agg(m=(model + "_err", lambda x: x.abs().mean()), f=("settle_err", lambda x: x.abs().mean()))
    w = stats.wilcoxon(pc.m, pc.f, alternative="less")
    print(f"per contract: {model} {pc.m.mean():.2f}% vs futures {pc.f.mean():.2f}%; model better in "
          f"{(pc.m < pc.f).sum()}/{len(pc)}; Wilcoxon one-sided p = {w.pvalue:.3f}")
    e.to_csv(RESULTS / "h2_futures_days.csv", index=False)

    # H2 rule (pre-registered): window 25..5 trading days before delivery; first day |z| > 1; 1 lot; hold
    e = e.sort_values("date")
    e["tdays_before"] = e.groupby("contract").cumcount(ascending=False) + 1
    e["z"] = (e[model] / e.settle - 1) * 100 / e.bucket.map(sigma)
    trades = []
    for c, g in e[(e.tdays_before <= 25) & (e.tdays_before >= 5)].groupby("contract"):
        hit = g[g.z.abs() > 1]
        if len(hit):
            r = hit.iloc[0]
            trades.append(backtest.Trade(c, r.date, int(np.sign(r.z)), 1, tag="H2"))
    report("H2 rule (first |z|>1, hold to expiry)", trades, book)

    # H3 (pre-registered): short at the first liquid day of the month before delivery; hold
    trades = []
    for c, g in e.groupby("contract"):
        m = pd.Period(c, "M")
        g = g[g.date >= (m - 1).start_time]
        if len(g):
            trades.append(backtest.Trade(c, g.date.iloc[0], -1, 1, tag="H3"))
    res = report("H3 short a month before delivery", trades, book)
    if len(res):
        half = len(res) // 2
        print(f"  H3 halves: first {res.net_pct.iloc[:half].mean():.2f}% , second {res.net_pct.iloc[half:].mean():.2f}%")


def report(label, trades, book):
    out = None
    for k_cost in (1, 2, 4):
        res, pnl = backtest.run(trades, book, Costs().scaled(k_cost))
        print(f"\n{label}, costs x{k_cost}:")
        print(metrics.fmt(metrics.summarize(res, pnl)))
        if k_cost == 1:
            out = res
            if len(res):
                print(res[["contract", "entry_date", "direction", "entry_px", "exit_px", "net_pct"]]
                      .round({"entry_px": 0, "exit_px": 0, "net_pct": 2}).to_string(index=False))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    {"calibrate": calibrate, "futures": futures_test}[sys.argv[1]]()
