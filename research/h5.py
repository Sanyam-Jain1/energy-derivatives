"""H5 upper bound: does the delivery month's ACTUAL weather explain how far its index moves
away from the last 30 days' level? (Ex post diagnostic: if perfect weather knowledge explains
little, no weather forecast can help, and H5 is dropped.)

    python -m research.h5
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import data
from .config import DATA

CDD_BASE = 24.0


def weather_daily():
    w = pd.read_csv(DATA / "weather_daily.csv", parse_dates=["date"])
    w["tmean"] = (w.temperature_2m_max + w.temperature_2m_min) / 2
    w["cdd"] = (w.tmean - CDD_BASE).clip(lower=0)
    return w.groupby("date").agg(cdd=("cdd", "mean"), tmax=("temperature_2m_max", "mean"),
                                 rain=("precipitation_sum", "mean"))


def main():
    iex, w = data.iex_daily(), weather_daily()
    rows = []
    for m in pd.period_range("2022-06", "2026-09", freq="M"):
        start, end = m.start_time, m.end_time.normalize()
        ref = slice(start - pd.Timedelta(days=31), start - pd.Timedelta(days=2))   # last 30 days known at month start
        if end > w.index.max():
            continue
        rows.append({"month": str(m), "cal": m.month,
                     "y": np.log(iex.loc[start:end, "vw_avg"].mean() / iex.loc[ref, "vw_avg"].mean()),
                     "d_cdd": w.loc[start:end, "cdd"].mean() - w.loc[ref, "cdd"].mean(),
                     "d_tmax": w.loc[start:end, "tmax"].mean() - w.loc[ref, "tmax"].mean(),
                     "d_rain": w.loc[start:end, "rain"].mean() - w.loc[ref, "rain"].mean()})
    d = pd.DataFrame(rows)
    print(f"{len(d)} months {d.month.iloc[0]}..{d.month.iloc[-1]}; y = log(month index / last 30 days)")
    print(f"sd of y = {d.y.std():.3f} (that is the persistence error H5 tries to reduce)")
    for xs in (["d_cdd"], ["d_tmax"], ["d_rain"], ["d_cdd", "d_rain"]):
        f = sm.OLS(d.y, sm.add_constant(d[xs])).fit(cov_type="HC1")
        print(f"\n  y ~ {' + '.join(xs)}: R2 {f.rsquared:.3f}, adj {f.rsquared_adj:.3f}")
        print("   " + "  ".join(f"{k} {v:+.4f} (t {t:+.2f})" for k, v, t in zip(f.params.index, f.params, f.tvalues)))
    # leave-one-out error reduction vs persistence (y_hat = 0)
    X = sm.add_constant(d[["d_cdd", "d_rain"]]).values
    loo = []
    for i in range(len(d)):
        mask = np.arange(len(d)) != i
        b, *_ = np.linalg.lstsq(X[mask], d.y.values[mask], rcond=None)
        loo.append(d.y.values[i] - X[i] @ b)
    print(f"\nleave-one-out mean abs error: persistence {d.y.abs().mean():.3f}, with perfect weather {np.mean(np.abs(loo)):.3f} "
          f"({(1 - np.mean(np.abs(loo)) / d.y.abs().mean()) * 100:.0f}% lower)")


if __name__ == "__main__":
    main()
