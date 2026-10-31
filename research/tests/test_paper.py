import numpy as np
import pandas as pd
import pytest

from research import paper
from research.config import LOT_MWH, Costs


def test_paper_open_then_close_accounting(tmp_path, monkeypatch):
    monkeypatch.setattr(paper, "ROOT", tmp_path)
    days = pd.to_datetime(["2026-03-02", "2026-03-03"])
    fut = pd.DataFrame({"contract": ["2026-03", "2026-03"], "trade_date": days, "expiry": pd.Timestamp("2026-03-30"),
                        "settle": [4000.0, 4100.0], "lots": [500, 500], "trades": [50, 50]})
    # training rows: 4 expired contracts where ret_next = 1.0 x news_now exactly
    rng = np.random.default_rng(1)
    train = []
    for i, c in enumerate(["2025-10", "2025-11", "2025-12", "2026-01"]):
        x = rng.normal(0, 0.02, 20)
        train.append(pd.DataFrame({"contract": c, "expiry": pd.Timestamp(c + "-28"), "trade_date": pd.Timestamp(c + "-01"),
                                   "liquid": True, "next_liquid": True, "prev_liquid": True, "rank": 0,
                                   "news_now": x, "basis": 0.0, "ret_now": 0.0, "ret_next": x, "settle": 4000.0, "lots": 500}))
    today = pd.DataFrame({"contract": ["2026-03"], "expiry": [pd.Timestamp("2026-03-30")], "trade_date": [days[0]],
                          "liquid": [True], "next_liquid": [True], "prev_liquid": [True], "rank": [0], "news_now": [0.02],
                          "basis": [0.0], "ret_now": [0.0], "ret_next": [np.nan], "settle": [4000.0], "lots": [500]})
    rows = pd.concat(train + [today], ignore_index=True)
    ledger = paper.Ledger("t")
    paper.run_day(days[0], rows, fut, {}, ledger)
    assert (ledger.fills.action == "open").sum() == 1 and ledger.fills.side.iloc[0] == 1
    paper.run_day(days[1], rows, fut, {}, ledger)
    c = Costs()
    expected = ((4100 - 4000) - c.per_mwh(4000, 1) - c.per_mwh(4100, -1)) * LOT_MWH
    assert ledger.fills.pnl_rs.sum() == pytest.approx(expected)
    assert ledger.equity.equity_rs.iloc[-1] == pytest.approx(paper.Rules().capital_rs + expected)
    paper.run_day(days[1], rows, fut, {}, ledger)   # same day again: ignored
    assert len(ledger.equity) == 2
