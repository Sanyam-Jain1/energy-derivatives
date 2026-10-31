import numpy as np
import pandas as pd
import pytest

from research import backtest, data, forecast, settlement
from research.config import Costs


def synthetic_iex(start="2025-01-01", days=200, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame({"vw_avg": 4000 + rng.normal(0, 300, days)}, index=idx)


def test_index_proxy_is_mean_over_window():
    iex = synthetic_iex()
    # Feb 2025: expiry 27 Feb -> window 1..28 Feb (expiry+1 = 28 Feb = month end)
    assert settlement.index_proxy(iex, "2025-02", "2025-02-27") == pytest.approx(iex.loc["2025-02-01":"2025-02-28", "vw_avg"].mean())
    # expiry 2 days before month end -> window stops at expiry + 1
    assert settlement.settlement_window("2025-05", "2025-05-29")[1] == pd.Timestamp("2025-05-30")


def test_known_part_uses_only_published_days():
    iex = synthetic_iex()
    kp = settlement.known_part(iex, "2025-03", "2025-03-28", "2025-03-10")
    assert kp.n_known == 11            # 1..11 March: DAM for D+1 is out on D
    assert kp.n_days == 29             # 1..29 March
    assert kp.known_sum == pytest.approx(iex.loc["2025-03-01":"2025-03-11", "vw_avg"].sum())
    before = settlement.known_part(iex, "2025-03", "2025-03-28", "2025-02-20")
    assert before.n_known == 0


def test_estimate_and_implied_rest_are_inverse():
    kp = settlement.KnownPart(30, 12, 12 * 4000.0, pd.Timestamp("2025-03-12"))
    assert kp.implied_rest(kp.estimate(5000.0)) == pytest.approx(5000.0)


@pytest.mark.parametrize("name", list(forecast.REST_MODELS))
def test_rest_models_ignore_future_rows(name):
    iex = synthetic_iex()
    cut = pd.Timestamp("2025-05-10")
    hist = iex.loc[:cut]
    fut_days = pd.date_range(cut + pd.Timedelta(days=1), periods=10)
    a = forecast.REST_MODELS[name](hist, fut_days)
    tampered = iex.copy()
    tampered.loc[cut + pd.Timedelta(days=1):, "vw_avg"] = 1e6
    b = forecast.REST_MODELS[name](tampered.loc[:cut], fut_days)
    assert np.isfinite(a) and a == pytest.approx(b)


def test_backtest_long_to_expiry_pnl_and_costs():
    fut = pd.DataFrame({"contract": ["2025-03"] * 3,
                        "trade_date": pd.to_datetime(["2025-03-25", "2025-03-26", "2025-03-27"]),
                        "expiry": pd.to_datetime(["2025-03-27"] * 3),
                        "settle": [4000.0, 4100.0, 4200.0], "lots": [500, 500, 500], "trades": [50, 50, 50]})
    book = backtest.Book(fut, {"2025-03": 4300.0})
    res, pnl = backtest.run([backtest.Trade("2025-03", pd.Timestamp("2025-03-25"), +1)], book, Costs())
    r = res.iloc[0]
    assert r.gross_rs_mwh == pytest.approx(300.0)
    expected_cost = Costs().per_mwh(4000.0, +1) + Costs().per_mwh(4300.0, -1, at_expiry=True)
    assert r.cost_rs_mwh == pytest.approx(expected_cost)
    assert pnl.sum() == pytest.approx(r.net_rs)


def test_backtest_skips_untradable_entry():
    fut = pd.DataFrame({"contract": ["2025-03"], "trade_date": pd.to_datetime(["2025-03-25"]),
                        "expiry": pd.to_datetime(["2025-03-27"]), "settle": [4000.0], "lots": [3], "trades": [2]})
    res, _ = backtest.run([backtest.Trade("2025-03", pd.Timestamp("2025-03-25"), +1)], backtest.Book(fut, {"2025-03": 4300.0}))
    assert res.empty


def test_proxy_matches_nse_finals_on_real_data():
    iex, con = data.iex_daily(), data.contracts()
    settled = con[con.final_settle.notna()]
    errs = [abs(settlement.index_proxy(iex, c, r.expiry) / r.final_settle - 1) for c, r in settled.iterrows()]
    assert len(errs) >= 14 and np.mean(errs) < 0.01
