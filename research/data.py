"""Loaders for the repo's tables. Every frame carries the date it became known (IST)."""

import pandas as pd

from .config import DATA


def futures(exchange="NSE"):
    """Daily futures rows. `known_on` = trade_date: the settlement is published that evening."""
    f = pd.read_csv(DATA / "futures_daily.csv", dtype={"contract": str}, parse_dates=["trade_date", "expiry"])
    f = f[f.exchange == exchange].copy()
    f["known_on"] = f.trade_date
    return f.sort_values(["trade_date", "contract"]).reset_index(drop=True)


def contracts(exchange="NSE"):
    c = pd.read_csv(DATA / "contracts.csv", dtype={"contract": str}, parse_dates=["expiry"])
    return c[c.exchange == exchange].set_index("contract")


def iex_daily():
    """One row per DAM delivery day. DAM for day D is published by 15:00 IST on D-1, so
    `known_on` = delivery_date - 1 day."""
    d = pd.read_csv(DATA / "iex_daily.csv", parse_dates=["delivery_date"])
    d["known_on"] = d.delivery_date - pd.Timedelta(days=1)
    return d.sort_values("delivery_date").set_index("delivery_date")
