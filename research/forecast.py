"""Spot forecasts. Every function takes `hist`, the daily IEX series up to the last delivery day
known at the decision (no later rows), so look-ahead is impossible by construction."""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- remaining days of a month (H1)


def r0_last7(hist, future_dates):
    """Persistence: every unknown day at the mean of the last 7 known days."""
    return float(hist.vw_avg.iloc[-7:].mean())


def r1_ewm(hist, future_dates, halflife=3.0):
    return float(hist.vw_avg.ewm(halflife=halflife).mean().iloc[-1])


def fit_ar(hist, window=28):
    """AR(1) on log daily VW price minus its trailing 28-day mean, with day-of-week effects.
    Returns (phi, dow) where dow[k] is the mean residual on weekday k."""
    x = np.log(hist.vw_avg.clip(lower=1.0))
    m = x.rolling(window).mean().shift(1)
    y = (x - m).dropna()
    y_lag = y.shift(1).dropna()
    y_now = y.loc[y_lag.index]
    dow = pd.get_dummies(y_now.index.dayofweek).astype(float).values
    X = np.column_stack([y_lag.values, dow])
    coef, *_ = np.linalg.lstsq(X, y_now.values, rcond=None)
    return float(coef[0]), coef[1:]


def r2_ar(hist, future_dates, params=None, window=28):
    """Mean of AR(1)+weekday forecasts of each unknown day, back on the price scale."""
    phi, dow = params if params is not None else fit_ar(hist, window)
    x = np.log(hist.vw_avg.clip(lower=1.0))
    m = x.iloc[-window:].mean()
    y_last = x.iloc[-1] - m
    last = hist.index[-1]
    out = []
    for d in future_dates:
        h = (d - last).days
        out.append(np.exp(m + (phi ** h) * y_last + dow[d.dayofweek] * (1 - phi ** h)))
    return float(np.mean(out)) if out else float("nan")


REST_MODELS = {"R0_last7": r0_last7, "R1_ewm3": r1_ewm, "R2_ar": r2_ar}

# ---------------------------------------------------------------- next month's level (H2)


def monthly_index(hist):
    """Mean daily VW price per calendar month (complete months only)."""
    g = hist.vw_avg.groupby(hist.index.to_period("M"))
    full = g.size() == [p.days_in_month for p in g.size().index]
    return g.mean()[full]


def m0_last30(hist, month):
    return float(hist.vw_avg.iloc[-30:].mean())


def m1_seasonal_ratio(hist, month):
    """Last 30 days x median ratio, in earlier years, of the same month's index to the 30 days
    that ended the same number of days before that month started."""
    month = pd.Period(month, "M")
    gap = (month.start_time - hist.index[-1]).days
    idx = monthly_index(hist)
    ratios = []
    for back in range(1, 6):
        past = month - 12 * back
        if past not in idx.index:
            continue
        end = past.start_time - pd.Timedelta(days=gap)
        ref = hist.vw_avg.loc[end - pd.Timedelta(days=29):end]
        if len(ref) >= 25:
            ratios.append(idx[past] / ref.mean())
    base = m0_last30(hist, month)
    return float(base * np.median(ratios)) if ratios else base


def m2_yoy(hist, month):
    """Same month last year x (last 90 days / the same 90 days a year earlier)."""
    month = pd.Period(month, "M")
    idx = monthly_index(hist)
    last_year = month - 12
    end = hist.index[-1]
    prev = hist.vw_avg.loc[end - pd.Timedelta(days=365 + 89):end - pd.Timedelta(days=365)]
    if last_year not in idx.index or len(prev) < 80:
        return m0_last30(hist, month)
    return float(idx[last_year] * hist.vw_avg.iloc[-90:].mean() / prev.mean())


def m3_blend(hist, month):
    return 0.5 * (m1_seasonal_ratio(hist, month) + m2_yoy(hist, month))


MONTH_MODELS = {"M0_last30": m0_last30, "M1_seasonal": m1_seasonal_ratio, "M2_yoy": m2_yoy, "M3_blend": m3_blend}
