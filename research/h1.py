"""H1: inside the delivery month, known days + a forecast of the rest vs the futures price.

    python -m research.h1 calibrate   # pre-futures months: which rest-of-month model, error by days left
    python -m research.h1 futures     # futures months: model vs futures error, then the trading rule
"""

import json
import logging
import sys

import numpy as np
import pandas as pd

from . import backtest, data, forecast, metrics, settlement
from .config import CALIBRATION_END, CALIBRATION_START, RESULTS, Costs

log = logging.getLogger("h1")
BUCKETS = [0, 3, 7, 14, 21, 31]


def pseudo_expiry(month):
    """Business day before the month's last calendar day (weekends only; holidays ignored)."""
    d = pd.Period(month, "M").end_time.normalize() - pd.Timedelta(days=1)
    while d.dayofweek >= 5:
        d -= pd.Timedelta(days=1)
    return d


def estimates(iex, contract, expiry, decision_dates, models, ar_params=None):
    """Index estimates by each rest-of-month model, for each decision date."""
    rows = []
    for t in decision_dates:
        kp = settlement.known_part(iex, contract, expiry, t)
        if kp.n_rest == 0:
            continue
        hist = iex.loc[:kp.last_known] if kp.n_known else iex.loc[:t + pd.Timedelta(days=1)]
        first, last = settlement.settlement_window(contract, expiry)
        future = pd.date_range(max(first, hist.index[-1] + pd.Timedelta(days=1)), last)
        row = {"contract": contract, "date": t, "n_rest": kp.n_rest, "n_known": kp.n_known}
        for name in models:
            fn = forecast.REST_MODELS[name]
            rest = fn(hist, future, ar_params) if name == "R2_ar" else fn(hist, future)
            row[name] = kp.estimate(rest)
        rows.append(row)
    return pd.DataFrame(rows)


def bucket(n_rest):
    return pd.cut(n_rest, BUCKETS, labels=[f"{a + 1}-{b}" for a, b in zip(BUCKETS[:-1], BUCKETS[1:])])


def calibrate():
    iex = data.iex_daily()
    months = pd.period_range(CALIBRATION_START[:7], CALIBRATION_END[:7], freq="M")[1:]  # skip the cap-change month
    frames = []
    for m in months:
        c = str(m)
        expiry = pseudo_expiry(c)
        truth = settlement.index_proxy(iex, c, expiry)
        params = forecast.fit_ar(iex.loc[:m.start_time - pd.Timedelta(days=2)])   # refit monthly, past only
        dates = pd.date_range(m.start_time - pd.Timedelta(days=1), expiry - pd.Timedelta(days=1))
        e = estimates(iex, c, expiry, dates, forecast.REST_MODELS, params)
        e["truth"] = truth
        frames.append(e)
    e = pd.concat(frames)
    for name in forecast.REST_MODELS:
        e[name + "_err"] = (e[name] / e.truth - 1) * 100
    e["bucket"] = bucket(e.n_rest)
    tab = e.groupby("bucket", observed=True)[[n + "_err" for n in forecast.REST_MODELS]].agg(lambda x: x.abs().mean())
    sig = e.groupby("bucket", observed=True)[[n + "_err" for n in forecast.REST_MODELS]].std()
    overall = {n: e[n + "_err"].abs().mean() for n in forecast.REST_MODELS}
    best = min(overall, key=overall.get)
    print(f"pre-futures calibration: {len(months)} months {months[0]}..{months[-1]}, {len(e)} decision days")
    print("mean absolute error of the index estimate (%), by days remaining:")
    print(tab.round(2).to_string())
    print("overall:", {k: round(v, 2) for k, v in overall.items()}, "-> chosen:", best)
    sigma = {str(b): float(v) for b, v in sig[best + "_err"].items()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "h1_calibration.json").write_text(json.dumps({"model": best, "sigma_pct_by_bucket": sigma,
                                                             "mae_by_bucket": tab.round(3).to_dict()}, indent=1))
    print("sigma (sd of error, %) by bucket for the chosen model:", {k: round(v, 2) for k, v in sigma.items()})


def futures_test():
    cal = json.loads((RESULTS / "h1_calibration.json").read_text())
    model, sigma = cal["model"], cal["sigma_pct_by_bucket"]
    iex, fut, con = data.iex_daily(), data.futures(), data.contracts()
    settled = con[con.final_settle.notna()]
    book = backtest.Book(fut, settled.final_settle.to_dict())
    rows = []
    for c, k in settled.iterrows():
        m = pd.Period(c, "M")
        params = forecast.fit_ar(iex.loc[:m.start_time - pd.Timedelta(days=2)])
        days = fut[(fut.contract == c) & (fut.trade_date >= m.start_time - pd.Timedelta(days=1))
                   & (fut.trade_date < k.expiry) & (fut.trades >= 10)]
        e = estimates(iex, c, k.expiry, list(days.trade_date), [model], params)
        e = e.merge(days[["trade_date", "settle", "lots"]], left_on="date", right_on="trade_date")
        e["final"] = k.final_settle
        rows.append(e)
    e = pd.concat(rows)
    e["model_err"] = (e[model] / e.final - 1) * 100
    e["fut_err"] = (e.settle / e.final - 1) * 100
    e["bucket"] = bucket(e.n_rest).astype(str)
    e["sigma"] = e.bucket.map(sigma)
    e["edge_pct"] = (e[model] / e.settle - 1) * 100
    e["z"] = e.edge_pct / e.sigma
    tab = e.groupby("bucket").agg(days=("final", "size"), contracts=("contract", "nunique"),
                                  model_mae=("model_err", lambda x: x.abs().mean()),
                                  futures_mae=("fut_err", lambda x: x.abs().mean()),
                                  model_closer=("model_err", lambda x: np.nan))
    tab["model_closer"] = e.assign(w=e.model_err.abs() < e.fut_err.abs()).groupby("bucket").w.mean()
    print(f"H1 futures period: {e.contract.nunique()} contracts, {len(e)} liquid delivery-month days, model {model}")
    print(tab.reindex(["1-3", "4-7", "8-14", "15-21", "22-31"]).round(2).to_string())
    # falsification: paired, per contract (mean over its days), model vs futures absolute error
    pc = e.groupby("contract").agg(m=("model_err", lambda x: x.abs().mean()), f=("fut_err", lambda x: x.abs().mean()))
    from scipy import stats
    w = stats.wilcoxon(pc.m, pc.f, alternative="less")
    print(f"per-contract MAE: model {pc.m.mean():.2f}% vs futures {pc.f.mean():.2f}%; model better in "
          f"{(pc.m < pc.f).sum()}/{len(pc)} contracts; Wilcoxon one-sided p = {w.pvalue:.3f}")
    e.to_csv(RESULTS / "h1_futures_days.csv", index=False)

    # trading rule (pre-registered): first day |z| > 1, size min(3, floor|z|), hold to expiry
    for label, exit_rule in [("hold to expiry", False), ("exit when |z| < 0.25", True)]:
        trades = []
        for c, g in e.sort_values("date").groupby("contract"):
            pos = None
            for r in g.itertuples():
                if pos is None and abs(r.z) > 1:
                    pos = backtest.Trade(c, r.date, int(np.sign(r.z)), int(min(3, np.floor(abs(r.z)))), tag="H1")
                    if not exit_rule:
                        break
                elif pos is not None and exit_rule and abs(r.z) < 0.25:
                    pos.exit_date = r.date
                    trades.append(pos)
                    pos = None
            if pos is not None:
                trades.append(pos)
        for k_cost in (1, 2, 4):
            res, pnl = backtest.run(trades, book, Costs().scaled(k_cost))
            s = metrics.summarize(res, pnl)
            print(f"\nH1 rule, {label}, costs x{k_cost}:")
            print(metrics.fmt(s))
            if k_cost == 1:
                res.to_csv(RESULTS / f"h1_trades_{'exit' if exit_rule else 'hold'}.csv", index=False)
                print(res[["contract", "entry_date", "direction", "lots", "entry_px", "exit_px", "net_pct"]].round({"entry_px": 0, "exit_px": 0, "net_pct": 2}).to_string(index=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    {"calibrate": calibrate, "futures": futures_test}[sys.argv[1]]()
