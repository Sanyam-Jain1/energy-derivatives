"""Does the same calendar month in earlier years improve the within-month estimate?

    python analysis/analog_years.py

Two checks, on complete months after the Rs 10 cap (May 2023 on):
1. Second half vs the week before: index of days 16-end over index of days 9-15,
   by calendar month. Shows which months tend to fall or rise late.
2. Analog estimate vs persistence. Persistence (futures.split_month) assumes the
   unknown days look like the last 7 known days. The analog estimate scales that
   by the mean of the same ratio (rest of month / last 7 days, at the same day of
   the month) in earlier years of the same calendar month.

Result (2026-10-14): analog is worse overall (mean abs error 19.1% vs 15.7% before
the month, 11.3% vs 9.2% at 15 days known). October is the one month where
persistence overshot at mid-month in every year (2023-2025).
"""

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import futures as F

KNOWN_SHOWN = [0, 5, 10, 15, 20, 25]


def main():
    df = F.load_daily()
    months = sorted(m for m, g in df.groupby("month") if len(g) == len(F.month_days(m)))
    tested = [m for m in months if F.month_days(m)[0] > F.CAP_START]

    halves = []
    for m in tested:
        g = df[df.month == m]
        dom = g.delivery_date.dt.day
        halves.append({"month": m, "cal": m[5:],
                       "change": F.settlement_index(g[dom > 15]) / F.settlement_index(g[dom.between(9, 15)]) - 1})
    h = pd.DataFrame(halves)
    print("1. Index of days 16-end vs days 9-15, by calendar month (%)")
    print((h.groupby("cal").change.agg(["mean", "min", "max"]) * 100).round(1)
          .join(h.groupby("cal").size().rename("years")).to_string())

    def ratio(m, k):
        """Index of the days after day k over the index of the 7 days up to day k."""
        cut = pd.Timestamp(F.month_days(m)[0] + timedelta(days=k - 1))
        rest = df[(df.month == m) & (df.delivery_date > cut)]
        recent = df[df.delivery_date <= cut].tail(F.RECENT_DAYS)
        if recent.empty:  # the first month in the data has no week before it
            return None
        return F.settlement_index(rest) / F.settlement_index(recent)

    rows = []
    for m in tested:
        days = F.month_days(m)
        final = F.settlement_index(df[df.month == m])
        priors = [p for p in months if p[5:] == m[5:] and p < m]
        for k in range(len(days)):
            r = [x for p in priors if k < len(F.month_days(p)) and (x := ratio(p, k)) is not None]
            if not r:
                continue
            s = F.split_month(df, m, days[0] - timedelta(days=2 - k))
            known = s["known_index"] * s["known_vol"] if s["known_days"] else 0
            analog = (known + s["rest_price"] * np.mean(r) * s["rest_vol"]) / (s["known_vol"] + s["rest_vol"])
            rows.append({"month": m, "known": k, "persistence": s["fair"] / final - 1,
                         "analog": analog / final - 1})
    e = pd.DataFrame(rows)
    shown = e[e.known.isin(KNOWN_SHOWN)]
    print(f"\n2. Mean absolute error vs final index (%), {e.month.nunique()} months")
    print((shown.groupby("known")[["persistence", "analog"]].agg(lambda x: x.abs().mean()) * 100).round(1).to_string())
    octs = shown[shown.month.str.endswith("-10")].copy()
    octs[["persistence", "analog"]] = (octs[["persistence", "analog"]] * 100).round(1)
    print("\n   Octobers (signed error %; positive = estimate above final)")
    print(octs.to_string(index=False))


if __name__ == "__main__":
    main()
