"""The settlement index and what is known of it at a decision date.

Proxy (Stage 1): the final settlement ~ mean of each day's IEX volume-weighted DAM price over
delivery days 1 .. min(expiry + 1, month end). Error against 14 NSE finals: MAE 0.69%.
"""

from dataclasses import dataclass

import pandas as pd


def settlement_window(contract, expiry):
    first = pd.Timestamp(contract + "-01")
    last = min(pd.Timestamp(expiry) + pd.Timedelta(days=1), first + pd.offsets.MonthEnd(0))
    return first, last


def index_proxy(iex, contract, expiry):
    """Settlement index proxy from IEX, or None if not all days are published."""
    first, last = settlement_window(contract, expiry)
    days = iex.loc[first:last, "vw_avg"]
    return days.mean() if len(days) == (last - first).days + 1 else None


@dataclass
class KnownPart:
    n_days: int          # settlement days in total
    n_known: int         # published by the decision date
    known_sum: float     # sum of their daily VW prices
    last_known: pd.Timestamp

    @property
    def n_rest(self):
        return self.n_days - self.n_known

    def estimate(self, rest_mean):
        """Index estimate given a forecast of the mean daily price of the unknown days."""
        return (self.known_sum + self.n_rest * rest_mean) / self.n_days

    def implied_rest(self, price):
        """Mean daily price the unknown days need for the index to equal `price`."""
        return (price * self.n_days - self.known_sum) / self.n_rest if self.n_rest else None


def known_part(iex, contract, expiry, decision_date):
    """What of the settlement index is public at the close of `decision_date` (DAM up to D+1)."""
    first, last = settlement_window(contract, expiry)
    cutoff = min(pd.Timestamp(decision_date) + pd.Timedelta(days=1), last)
    known = iex.loc[first:cutoff, "vw_avg"] if cutoff >= first else iex.iloc[0:0]["vw_avg"]
    return KnownPart((last - first).days + 1, len(known), float(known.sum()),
                     known.index.max() if len(known) else first - pd.Timedelta(days=1))
