"""Electricity futures research: MCX monthly baseload futures vs the IEX day-ahead market.

One file, standard library plus pandas. Run from the terminal:

    python futures.py daily                  # IEX DAM raw pages -> data/iex_dam_daily.csv
    python futures.py index                  # monthly settlement index vs MCX/NSE finals
    python futures.py fairvalue --month 2026-10 [--as-of 2026-10-08] [--rest 7000]
    python futures.py convergence            # how fast the month's index becomes known
    python futures.py export                 # CSVs for the dashboard -> data/dashboard/
    python futures.py fetch --month 2026-10  # current month to date from IEX (slow, polite)
    python futures.py nse-bhavcopy           # NSE electricity futures, every trading day
    python futures.py mcx-upstox             # MCX near contract, last ~20 days, from Upstox

IEX data. Complete months come from the sibling power_market repo
(../power_market/raw/dam, or $POWER_MARKET_DIR), parsed with its own
bess.parse_snapshot so there is one parser. Partial months fetched here go to
raw/dam/dam_YYYY-MM_to_DD.html; for any delivery day, a complete-month file
wins over a partial one, and a later partial file over an earlier one.

Settlement index (checked in `index`, see docs/settlement_index.md). MCX's final
settlement price equals the month's daily IEX DAM averages (simple mean of the
96 block prices) weighted by each day's cleared volume:

    index = sum(day_avg_d * mcv_d) / sum(mcv_d)

This reproduces all five known MCX finals within Rs 0.5/MWh. It is neither the
simple mean of all blocks nor the block-level volume-weighted price.

Information timing. DAM prices for delivery day D are public by 15:00 on D-1
(power_market's rule), and MCX trades until 23:30. So a close on trading day T
can know delivery days up to and including T+1.

All dates are Indian Standard Time.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time as clock
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = ROOT / "raw" / "dam"
MANIFEST = ROOT / "raw" / "manifest.csv"
POWER_MARKET_DIR = Path(os.environ.get("POWER_MARKET_DIR", ROOT.parent / "power_market")).resolve()

DAILY_CSV = DATA_DIR / "iex_dam_daily.csv"
MONTHLY_CSV = DATA_DIR / "iex_dam_monthly.csv"
MCX_SETTLEMENTS = DATA_DIR / "mcx_settlements.csv"
NSE_SETTLEMENTS = DATA_DIR / "nse_settlements.csv"
MCX_DAILY = DATA_DIR / "mcx_daily.csv"

CAP_START = date(2023, 4, 4)       # Rs 10/kWh cap; months before it are a different market
RECENT_DAYS = 7                    # window for the "rest of month looks like last week" estimate
FETCH_DELAY_SECONDS = 10
USER_AGENT = "futures-research/0.1 (research; one request per 10 s)"
IST = timezone(timedelta(hours=5, minutes=30))  # India has no daylight saving
PARTIAL_RE = re.compile(r"^dam_(\d{4}-\d\d)(?:_to_(\d\d))?\.html$")


def load_bess():
    """power_market's bess module, for its snapshot parser and fetch helpers."""
    if not (POWER_MARKET_DIR / "bess.py").exists():
        sys.exit(f"bess.py not found in {POWER_MARKET_DIR}; set POWER_MARKET_DIR")
    sys.path.insert(0, str(POWER_MARKET_DIR))
    import bess
    return bess


def month_days(month):
    first = date.fromisoformat(month + "-01")
    nxt = date(first.year + first.month // 12, first.month % 12 + 1, 1)
    return [first + timedelta(days=i) for i in range((nxt - first).days)]


# ---------------------------------------------------------------- daily IEX averages

def raw_files():
    """Every DAM page, in priority order: complete months first, then partials, latest first."""
    complete = sorted((POWER_MARKET_DIR / "raw" / "dam").glob("dam_*.html"))
    partial = []
    for p in sorted(RAW_DIR.glob("dam_*.html")):
        m = PARTIAL_RE.match(p.name)
        if m and m.group(2) is None:
            complete.append(p)
        elif m:
            partial.append((m.group(1), m.group(2), p))
    return complete + [p for *_, p in sorted(partial, reverse=True)]


def load_blocks():
    """Traded DAM blocks, one version per delivery day (see raw_files for which file wins)."""
    bess = load_bess()
    seen, parts = set(), []
    for path in raw_files():
        blocks = pd.DataFrame(bess.parse_snapshot("DAM", path.read_text()))
        blocks = blocks[~blocks.delivery_date.isin(seen)]
        seen.update(blocks.delivery_date)
        blocks["source"] = f"{path.parents[2].name}/{path.relative_to(path.parents[2]).as_posix()}"
        parts.append(blocks)
    blocks = pd.concat(parts)
    return blocks[~((blocks.mcv_mw == 0) & (blocks.mcp_rs_mwh == 0))]  # no-trade blocks are not Rs 0 prices


def cmd_daily(args):
    """One row per delivery day. Volumes in MWh (sum of 15-min MW / 4)."""
    rows = []
    for d, b in load_blocks().groupby("delivery_date"):
        rows.append({
            "delivery_date": d,
            "blocks": len(b),
            "avg_mcp": round(b.mcp_rs_mwh.mean(), 2),
            "vw_mcp": round((b.mcp_rs_mwh * b.mcv_mw).sum() / b.mcv_mw.sum(), 2),
            "min_mcp": b.mcp_rs_mwh.min(),
            "max_mcp": b.mcp_rs_mwh.max(),
            "mcv_mwh": round(b.mcv_mw.sum() / 4, 2),
            "fsv_mwh": round(b.final_scheduled_volume_mw.sum() / 4, 2),
            "source": b.source.iloc[0],
        })
    df = pd.DataFrame(rows)
    short = df[df.blocks != 96]
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DAILY_CSV, index=False)
    print(f"wrote {DAILY_CSV.relative_to(ROOT)}  {len(df)} days, {df.delivery_date.min()} to {df.delivery_date.max()}")
    if len(short):
        print(f"  {len(short)} days with fewer than 96 traded blocks: {', '.join(short.delivery_date)}")


def load_daily():
    if not DAILY_CSV.exists():
        sys.exit(f"{DAILY_CSV.relative_to(ROOT)} missing; run `python futures.py daily` first")
    df = pd.read_csv(DAILY_CSV, parse_dates=["delivery_date"])
    df["month"] = df.delivery_date.dt.strftime("%Y-%m")
    return df


def settlement_index(days):
    """MCX's final settlement formula: daily averages weighted by daily cleared volume."""
    return (days.avg_mcp * days.mcv_mwh).sum() / days.mcv_mwh.sum()


# ---------------------------------------------------------------- monthly index vs exchange finals

def monthly_table(df):
    """Per month: MCX index, simple and block volume-weighted averages, exchange finals."""
    df = df.assign(pv=df.vw_mcp * df.mcv_mwh)
    g = df.groupby("month")
    m = pd.DataFrame({
        "days": g.size(),
        "mcx_index": g.apply(settlement_index, include_groups=False),
        "simple_avg": g.apply(lambda x: (x.avg_mcp * x.blocks).sum() / x.blocks.sum(), include_groups=False),
        "block_vw_avg": g.pv.sum() / g.mcv_mwh.sum(),
    })
    m["complete"] = [m.loc[k, "days"] == len(month_days(k)) for k in m.index]
    for name, path in (("mcx_final", MCX_SETTLEMENTS), ("nse_final", NSE_SETTLEMENTS)):
        s = pd.read_csv(path, dtype={"contract": str}).set_index("contract").final_settlement_rs_mwh
        m[name] = s
    return m


def cmd_index(args):
    m = monthly_table(load_daily())
    m.round(2).to_csv(MONTHLY_CSV, index_label="month")
    print(f"wrote {MONTHLY_CSV.relative_to(ROOT)}  {len(m)} months")

    checked = m.dropna(subset=["mcx_final"])
    print("\nMCX final settlement vs candidate IEX averages (Rs/MWh; error = final - candidate)")
    print(f"{'month':8} {'MCX final':>10} {'index':>9} {'err':>6} {'simple':>9} {'err':>6} {'block VW':>9} {'err':>6}")
    for k, r in checked.iterrows():
        print(f"{k:8} {r.mcx_final:10.0f} {r.mcx_index:9.1f} {r.mcx_final - r.mcx_index:6.1f}"
              f" {r.simple_avg:9.1f} {r.mcx_final - r.simple_avg:6.0f}"
              f" {r.block_vw_avg:9.1f} {r.mcx_final - r.block_vw_avg:6.0f}")
    worst = (checked.mcx_final - checked.mcx_index).abs().max()
    print(f"  index formula: worst error Rs {worst:.1f}/MWh over {len(checked)} months")

    nse = m.dropna(subset=["nse_final"])
    if len(nse):
        print("\nNSE final settlement vs IEX averages (NSE averages all three exchanges)")
        for k, r in nse.iterrows():
            print(f"{k:8} NSE {r.nse_final:.0f}  IEX block-VW {r.block_vw_avg:.0f} ({r.nse_final / r.block_vw_avg - 1:+.1%})"
                  f"  IEX MCX-index {r.mcx_index:.0f} ({r.nse_final / r.mcx_index - 1:+.1%})")


# ---------------------------------------------------------------- fair value inside the month

def known_days(df, month, as_of):
    """Delivery days of `month` public by the close of trading day `as_of` (up to as_of + 1)."""
    return df[(df.month == month) & (df.delivery_date <= pd.Timestamp(as_of + timedelta(days=1)))]


def split_month(df, month, as_of, rest_price=None):
    """Known part and an estimate for the rest. Rest defaults to the last RECENT_DAYS days."""
    days = month_days(month)
    known = known_days(df, month, as_of)
    recent = df[df.delivery_date <= pd.Timestamp(as_of + timedelta(days=1))].tail(RECENT_DAYS)
    n_rest = len(days) - len(known)
    rest_vol = recent.mcv_mwh.mean() * n_rest
    rest = settlement_index(recent) if rest_price is None else rest_price
    known_vol = known.mcv_mwh.sum()
    known_idx = settlement_index(known) if len(known) else float("nan")
    fair = ((known_idx * known_vol if len(known) else 0) + rest * rest_vol) / (known_vol + rest_vol)
    return {"known_days": len(known), "rest_days": n_rest, "known_index": known_idx,
            "known_vol": known_vol, "rest_vol": rest_vol, "rest_price": rest, "fair": fair}


def implied_rest(s, futures_price):
    """Average price the rest of the month must have for the futures price to be fair."""
    if s["rest_days"] == 0:
        return float("nan")
    known = s["known_index"] * s["known_vol"] if s["known_days"] else 0
    return (futures_price * (s["known_vol"] + s["rest_vol"]) - known) / s["rest_vol"]


def cmd_fairvalue(args):
    df = load_daily()
    closes = pd.read_csv(MCX_DAILY, parse_dates=["trade_date"], dtype={"contract": str})
    closes = closes[closes.contract == args.month].sort_values("trade_date")
    last_data = df.delivery_date.max().date()
    as_of = date.fromisoformat(args.as_of) if args.as_of else min(datetime.now(IST).date(), last_data - timedelta(days=1))
    if as_of + timedelta(days=1) > last_data and as_of < month_days(args.month)[-1]:
        print(f"note: IEX data ends {last_data}; days after it count as unknown")

    s = split_month(df, args.month, as_of, args.rest)
    print(f"MCX {args.month} as of close {as_of}  (IEX data to {last_data})")
    print(f"  known days      {s['known_days']:3d}   index so far  {s['known_index']:8.0f}")
    print(f"  remaining days  {s['rest_days']:3d}   assumed price {s['rest_price']:8.0f}"
          f"  ({'given' if args.rest is not None else f'last {RECENT_DAYS} days'})")
    print(f"  estimate (known + rest)        {s['fair']:8.0f}")

    if len(closes):
        print(f"\n{'close date':11} {'close':>6} {'known':>6} {'idx so far':>10} {'est':>6} {'gap':>6} {'implied rest':>12}")
        for _, c in closes.iterrows():
            t = c.trade_date.date()
            if t > as_of:
                break
            sc = split_month(df, args.month, t, args.rest)
            known_txt = f"{sc['known_index']:10.0f}" if sc["known_days"] else f"{'-':>10}"
            print(f"{t!s:11} {c.close_rs_mwh:6.0f} {sc['known_days']:6d} {known_txt} {sc['fair']:6.0f}"
                  f" {c.close_rs_mwh - sc['fair']:+6.0f} {implied_rest(sc, c.close_rs_mwh):12.0f}"
                  f"{'  (date inferred)' if c.date_inferred else ''}")
        print("  est = known days + rest at the assumed price; gap = close - est")
        print("  implied rest = average the unknown days need for the close to equal the final index")


# ---------------------------------------------------------------- how fast the month becomes known

def convergence_errors(df):
    """Every complete month after the Rs 10 cap, from 0 known days (the close two days before the
    month starts) to all but one: estimate error vs the final index, in %."""
    months = [m for m, g in df.groupby("month")
              if len(g) == len(month_days(m)) and month_days(m)[0] > CAP_START]
    rows = []
    for m in months:
        days = month_days(m)
        final = settlement_index(df[df.month == m])
        for k in range(0, len(days)):
            as_of = days[0] - timedelta(days=2) + timedelta(days=k)  # k known days at this close
            s = split_month(df, m, as_of)
            rows.append({"month": m, "known": s["known_days"], "err_pct": (s["fair"] / final - 1) * 100})
    return pd.DataFrame(rows)


def convergence_summary(e):
    return e.groupby("known").err_pct.agg(
        months="count",
        mean="mean",
        mean_abs=lambda x: x.abs().mean(),
        p90_abs=lambda x: x.abs().quantile(0.9),
        worst=lambda x: x.abs().max()).reset_index()


def cmd_convergence(args):
    """Error of the estimate vs the final index, by how many days of the month are known.
    The rest of the month is assumed to look like the last 7 known days."""
    e = convergence_errors(load_daily())
    months = sorted(e.month.unique())
    out = convergence_summary(e).set_index("known")
    print(f"Estimate error vs final MCX index, {len(months)} months {months[0]} to {months[-1]}")
    print("  rest of month assumed = last 7 known days (volume-weighted); errors in %")
    print(out.loc[[k for k in (0, 1, 3, 5, 7, 10, 14, 18, 21, 25, 28) if k in out.index]].round(1).to_string())
    e.to_csv(DATA_DIR / "convergence_errors.csv", index=False)
    print(f"wrote {(DATA_DIR / 'convergence_errors.csv').relative_to(ROOT)}")


# ---------------------------------------------------------------- MCX daily prices

UPSTOX_URL = "https://upstox.com/commodity-market-trading/mcx-elecdmbl-price/"
MCX_COLUMNS = ["trade_date", "contract", "open", "high", "low", "close_rs_mwh", "date_inferred", "source"]


def cmd_mcx_upstox(args):
    """MCX ELECDMBL daily OHLC from Upstox's quote page (about the last 20 trading days, near
    contract only). MCX's own site refuses scripted requests, so this is a stopgap until the
    MCX bhavcopy is loaded: rows are tagged source=upstox, and a row from any other source
    for the same day and contract is kept as it is."""
    req = urllib.request.Request(UPSTOX_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8").replace('\\"', '"')
    m = re.search(r'"priceHistory":(\[[^\]]*\])', text)
    if not m:
        sys.exit("no priceHistory on the Upstox page; its layout may have changed")
    rows = []
    for r in json.loads(m.group(1)):
        day = datetime.fromtimestamp(r["date"] / 1000, IST).date()
        expiry = datetime.strptime(r["expiryDate"], "%d %b, %y").date()
        rows.append({"trade_date": day.isoformat(), "contract": f"{expiry:%Y-%m}",
                     "open": r["open"] / 100, "high": r["high"] / 100, "low": r["low"] / 100,
                     "close_rs_mwh": r["close"] / 100, "date_inferred": 0, "source": "upstox"})
    new = pd.DataFrame(rows)
    have = pd.read_csv(MCX_DAILY, dtype={"contract": str})
    for c in MCX_COLUMNS:
        if c not in have:
            have[c] = None
    keyed = have.set_index(["trade_date", "contract"])
    changed = []
    for _, r in new.iterrows():
        k = (r.trade_date, r.contract)
        if k in keyed.index and not str(keyed.loc[k, "source"]).startswith("notes"):
            continue  # keep bhavcopy (or other better) rows
        if k in keyed.index and float(keyed.loc[k, "close_rs_mwh"]) != r.close_rs_mwh:
            changed.append(f"{r.trade_date} {r.contract}: {keyed.loc[k, 'close_rs_mwh']} -> {r.close_rs_mwh}")
        keyed.loc[k, MCX_COLUMNS[2:]] = [r[c] for c in MCX_COLUMNS[2:]]
    out = keyed.reset_index()[MCX_COLUMNS].sort_values(["trade_date", "contract"])
    out["date_inferred"] = out.date_inferred.fillna(0).astype(int)
    out.to_csv(MCX_DAILY, index=False)
    print(f"wrote {MCX_DAILY.relative_to(ROOT)}  {len(out)} rows; Upstox gave {len(new)} days, "
          f"{new.trade_date.min()} to {new.trade_date.max()}")
    for c in changed:
        print(f"  close differs from earlier row: {c}")


# ---------------------------------------------------------------- NSE bhavcopy

NSE_BHAVCOPY_URL = ("https://nsearchives.nseindia.com/content/com/"
                    "BhavCopy_NSE_CO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip")
NSE_BHAVCOPY_CSV = DATA_DIR / "nse_bhavcopy.csv"
NSE_LAUNCH = date(2025, 7, 14)
NSE_DELAY_SECONDS = 3
NSE_FIELDS = {  # our column -> bhavcopy (UDiFF) column
    "trade_date": "TradDt", "instrument": "FinInstrmNm", "expiry": "XpryDt",
    "open": "OpnPric", "high": "HghPric", "low": "LwPric", "close": "ClsPric",
    "settle": "SttlmPric", "prev_close": "PrvsClsgPric", "lots": "TtlTradgVol",
    "value_rs": "TtlTrfVal", "trades": "TtlNbOfTxsExctd", "open_interest": "OpnIntrst",
}


def log_manifest(row):
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["path", "url", "fetched_at", "status", "bytes", "sha256"])
        w.writerow(row)


def cmd_nse_bhavcopy(args):
    """Electricity futures (ELECMBL) rows from NSE's daily commodity bhavcopy, one file per trading day.

    Only the electricity rows are kept (data/nse_bhavcopy.csv); every request is logged in
    raw/manifest.csv with the zip's sha256. Days already in the CSV are skipped. A 404 is a
    holiday; anything else stops the run.
    """
    import io
    import zipfile
    have = pd.read_csv(NSE_BHAVCOPY_CSV, dtype=str) if NSE_BHAVCOPY_CSV.exists() else pd.DataFrame(columns=["contract", *NSE_FIELDS])
    done = set(have.trade_date)
    first = date.fromisoformat(args.start) if args.start else NSE_LAUNCH
    last = date.fromisoformat(args.end) if args.end else datetime.now(IST).date()
    todo = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    todo = [d for d in todo if d.weekday() < 5 and d.isoformat() not in done]
    print(f"{len(todo)} weekdays to fetch, about {len(todo) * NSE_DELAY_SECONDS // 60 + 1} min")
    rows, holidays = [], []
    try:
        for i, d in enumerate(todo):
            if i:
                clock.sleep(NSE_DELAY_SECONDS)
            url = NSE_BHAVCOPY_URL.format(d=d)
            now = datetime.now(IST).isoformat(timespec="seconds")
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = resp.read()
            except urllib.error.HTTPError as e:
                log_manifest(["", url, now, e.code, 0, ""])
                if e.code == 404:
                    holidays.append(d.isoformat())
                    continue
                sys.exit(f"stopped at {d}: HTTP {e.code}")
            log_manifest(["", url, now, 200, len(body), hashlib.sha256(body).hexdigest()])
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                text = z.read(z.namelist()[0]).decode("utf-8")
            day = [r for r in csv.DictReader(io.StringIO(text)) if r["TckrSymb"] == "ELECMBL"]
            for r in day:
                row = {ours: r[theirs] for ours, theirs in NSE_FIELDS.items()}
                row["contract"] = row["expiry"][:7]
                rows.append(row)
            print(f"  {d}  {len(day)} contracts")
    finally:  # keep what was fetched even if a later day stops the run
        if rows:
            out = pd.concat([have, pd.DataFrame(rows)]).drop_duplicates(["trade_date", "instrument"], keep="last")
            out = out[["trade_date", "contract", *[c for c in NSE_FIELDS if c != "trade_date"]]]
            out.sort_values(["trade_date", "contract"]).to_csv(NSE_BHAVCOPY_CSV, index=False)
            print(f"wrote {NSE_BHAVCOPY_CSV.relative_to(ROOT)}  {len(out)} rows, {out.trade_date.nunique()} days")
        if holidays:
            print(f"  no file (holiday) for {len(holidays)} days: {', '.join(holidays)}")


# ---------------------------------------------------------------- dashboard data

DASHBOARD_DIR = DATA_DIR / "dashboard"
DASHBOARD_FROM = "2023-05"  # first full month under the Rs 10 cap


def cmd_export(args):
    """Small CSVs for the dashboard, all from the same functions as the commands above."""
    df = load_daily()
    DASHBOARD_DIR.mkdir(exist_ok=True)
    out = {}

    out["daily"] = df[["delivery_date", "avg_mcp", "vw_mcp", "min_mcp", "max_mcp", "mcv_mwh"]].assign(
        delivery_date=df.delivery_date.dt.strftime("%Y-%m-%d"))

    m = monthly_table(df)
    m.index.name = "month"
    out["monthly"] = m.reset_index().round(2)

    rows = []  # each delivery day: index of the month so far, and the estimate once it is known
    for month, g in df[df.month >= DASHBOARD_FROM].groupby("month"):
        for d in g.delivery_date:
            k = known_days(df, month, (d - timedelta(days=1)).date())
            est = split_month(df, month, (d - timedelta(days=1)).date())
            rows.append({"month": month, "delivery_date": d.strftime("%Y-%m-%d"), "day": d.day,
                         "avg_mcp": k.avg_mcp.iloc[-1], "mcv_mwh": k.mcv_mwh.iloc[-1],
                         "index_so_far": round(settlement_index(k), 2), "estimate": round(est["fair"], 2)})
    out["contract_days"] = pd.DataFrame(rows)

    closes = pd.read_csv(MCX_DAILY, parse_dates=["trade_date"], dtype={"contract": str})
    rows = []
    for _, c in closes.iterrows():
        t = c.trade_date.date()
        sc = split_month(df, c.contract, t)
        rows.append({"trade_date": f"{t}", "contract": c.contract, "close": c.close_rs_mwh,
                     "date_inferred": c.date_inferred, "known_days": sc["known_days"],
                     "index_so_far": round(sc["known_index"], 2) if sc["known_days"] else None,
                     "estimate": round(sc["fair"], 2),
                     "gap": round(c.close_rs_mwh - sc["fair"], 2),
                     "implied_rest": round(implied_rest(sc, c.close_rs_mwh), 2)})
    out["futures"] = pd.DataFrame(rows)

    b = load_blocks()
    b = b[b.delivery_date >= DASHBOARD_FROM]
    b = b.assign(month=b.delivery_date.str[:7], hour=(b.block - 1) // 4)
    out["hourly"] = (b.groupby(["month", "hour"])
                     .agg(avg_mcp=("mcp_rs_mwh", "mean"), avg_mcv_mw=("mcv_mw", "mean"))
                     .round(1).reset_index())

    out["convergence"] = convergence_summary(convergence_errors(df)).round(2)

    for name, table in out.items():
        path = DASHBOARD_DIR / f"{name}.csv"
        table.to_csv(path, index=False)
        print(f"wrote {path.relative_to(ROOT)}  {len(table)} rows")


# ---------------------------------------------------------------- fetch the current month

def cmd_fetch(args):
    """Fetch delivery days of one month up to the latest published day (power_market only does full months)."""
    bess = load_bess()
    days = month_days(args.month)
    now = datetime.now(IST).replace(tzinfo=None)
    latest = (now.date() + timedelta(days=1)) if now.hour >= 15 else now.date()  # DAM for D+1 out by 15:00
    last = min(days[-1], latest)
    if last < days[0]:
        sys.exit(f"nothing published yet for {args.month}")
    url = bess.snapshot_url("DAM", days[0], last)
    path = RAW_DIR / (f"dam_{args.month}.html" if last == days[-1] else f"dam_{args.month}_to_{last:%d}.html")
    if path.exists():
        sys.exit(f"{path.relative_to(ROOT)} exists; nothing fetched")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=bess.SSL_CONTEXT) as resp:
        status, body = resp.status, resp.read()
    got = {r["date"] for r in bess.page_records(body.decode("utf-8", "replace"))}
    expected = (last - days[0]).days + 1
    if status != 200 or len(got) != expected:
        sys.exit(f"status {status}, {len(got)} of {expected} days in page; not saved")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["path", "url", "fetched_at", "status", "bytes", "sha256"])
        w.writerow([path.relative_to(ROOT).as_posix(), url, now.isoformat(timespec="seconds"),
                    status, len(body), hashlib.sha256(body).hexdigest()])
    print(f"  {path.relative_to(ROOT)}  {len(got)} days  {len(body) // 1024} KB")
    clock.sleep(FETCH_DELAY_SECONDS)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daily", help="build data/iex_dam_daily.csv from raw IEX pages")
    sub.add_parser("index", help="monthly settlement index vs MCX/NSE finals")
    fv = sub.add_parser("fairvalue", help="known part of a month, estimate, and what each close implies")
    fv.add_argument("--month", required=True, help="contract month, YYYY-MM")
    fv.add_argument("--as-of", help="trading day (YYYY-MM-DD); default: latest the data allows")
    fv.add_argument("--rest", type=float, help="assumed average for unknown days (Rs/MWh)")
    sub.add_parser("convergence", help="estimate error vs final index, by days known")
    nb = sub.add_parser("nse-bhavcopy", help="fetch NSE electricity futures from the daily commodity bhavcopy")
    nb.add_argument("--from", dest="start", help="first trade date, YYYY-MM-DD (default: launch, 2025-07-14)")
    nb.add_argument("--to", dest="end", help="last trade date (default: today, IST)")
    sub.add_parser("mcx-upstox", help="add MCX daily prices from Upstox (last ~20 days)")
    sub.add_parser("export", help="write the dashboard's CSVs to data/dashboard/")
    fe = sub.add_parser("fetch", help="fetch one month of IEX DAM up to the latest published day")
    fe.add_argument("--month", required=True, help="YYYY-MM")
    args = p.parse_args()
    {"daily": cmd_daily, "index": cmd_index, "fairvalue": cmd_fairvalue,
     "convergence": cmd_convergence, "export": cmd_export, "fetch": cmd_fetch, "nse-bhavcopy": cmd_nse_bhavcopy, "mcx-upstox": cmd_mcx_upstox}[args.cmd](args)


if __name__ == "__main__":
    main()
