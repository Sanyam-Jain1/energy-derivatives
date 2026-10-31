"""Summary statistics. With ~14 contracts, inference is by contract (one value per contract),
never by day, and no annualised figure is reported as evidence."""

import numpy as np
import pandas as pd
from scipy import stats


def summarize(res, daily_pnl=None):
    if res.empty:
        return {"trades": 0}
    per_contract = res.groupby("contract").net_pct.sum()   # contract = independent unit
    n = len(per_contract)
    mean = per_contract.mean()
    sd = per_contract.std(ddof=1) if n > 1 else np.nan
    t = mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else np.nan
    wins = (per_contract > 0).sum()
    gains, losses = res.net_rs[res.net_rs > 0].sum(), -res.net_rs[res.net_rs < 0].sum()
    out = {
        "trades": len(res), "contracts": n,
        "mean_net_pct_per_contract": mean, "t_stat": t,
        "p_one_sided": float(stats.t.sf(t, n - 1)) if n > 1 and not np.isnan(t) else np.nan,
        "hit_rate_contracts": wins / n,
        "sign_test_p": float(stats.binomtest(int(wins), n, 0.5, alternative="greater").pvalue),
        "worst_contract_pct": per_contract.min(), "best_contract_pct": per_contract.max(),
        "profit_factor": gains / losses if losses > 0 else np.inf,
        "total_net_rs": res.net_rs.sum(), "mean_days_held": res.days_held.mean(),
        "mean_cost_pct": (res.cost_rs_mwh / res.entry_px).mean() * 100,
        "worst_intratrade_mtm_pct": res.worst_mtm_pct.min(),
    }
    if daily_pnl is not None and len(daily_pnl):
        eq = daily_pnl.cumsum()
        out["max_drawdown_rs"] = float((eq - eq.cummax()).min())
    return out


def fmt(summary):
    keys = ["trades", "contracts", "mean_net_pct_per_contract", "t_stat", "p_one_sided", "hit_rate_contracts",
            "sign_test_p", "worst_contract_pct", "best_contract_pct", "profit_factor", "total_net_rs",
            "max_drawdown_rs", "mean_days_held", "mean_cost_pct", "worst_intratrade_mtm_pct"]
    return "\n".join(f"  {k:28} {summary[k]:.3f}" if isinstance(summary.get(k), float) else f"  {k:28} {summary.get(k)}"
                     for k in keys if k in summary)
