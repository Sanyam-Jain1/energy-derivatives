"""Electricity futures data: MCX (ELECDMBL) and NSE (ELECMBL) daily prices, plus IEX DAM.

Standard library plus pandas. Run from the terminal:

    python futures.py nse [--from 2025-07-14] [--to 2026-10-14]   # NSE daily bhavcopy -> raw/nse/
    python futures.py mcx                                         # MCX contracts still trading, via Upstox
    python futures.py build                                       # raw/ -> data/futures_daily.csv
    python futures.py check                                       # sanity checks, prints findings
    python futures.py iex [--fetch]                               # IEX DAM daily -> data/iex_daily.csv
    python futures.py join                                        # NSE vs IEX known days -> data/nse_vs_iex.csv
    python futures.py firstlook                                   # settlement vs final, traded days only
    python futures.py export                                      # dashboard CSVs -> data/dashboard/

Raw data. raw/ holds what the sources published and is never edited. Each NSE
trading day is one file, raw/nse/elecmbl_YYYYMMDD.csv: the ELECMBL rows of that
day's commodity bhavcopy, exactly as published (the full zip is ~0.1-1 MB and is
not kept). raw/manifest.csv logs every request: url, time, HTTP status, bytes and
the sha256 of the zip as downloaded. A day with a file is never fetched again.

All dates are Indian Standard Time.
"""

import argparse
import csv
import hashlib
import io
import os
import sys
import time as clock
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
DATA_DIR = ROOT / "data"
MANIFEST = RAW_DIR / "manifest.csv"
IST = timezone(timedelta(hours=5, minutes=30))  # India has no daylight saving
USER_AGENT = "energy-derivatives research (one request every few seconds)"

LOT_MWH = 50  # both exchanges

# ---------------------------------------------------------------- NSE

NSE_DIR = RAW_DIR / "nse"
NSE_URL = "https://nsearchives.nseindia.com/content/com/BhavCopy_NSE_CO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
NSE_SYMBOL = "ELECMBL"
NSE_LAUNCH = date(2025, 7, 14)
NSE_DELAY_SECONDS = 3


def log_request(url, status, body=b""):
    new = not MANIFEST.exists()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["url", "fetched_at", "status", "bytes", "sha256"])
        w.writerow([url, datetime.now(IST).isoformat(timespec="seconds"), status, len(body),
                    hashlib.sha256(body).hexdigest() if body else ""])


RETRY_WAITS = (2, 4, 8, 16)  # seconds, after a dropped connection


def download(url):
    """GET with retries on network errors (not on HTTP errors, which the caller handles)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    for wait in (*RETRY_WAITS, None):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            if wait is None:
                log_request(url, "network error")
                sys.exit(f"gave up on {url}: {e}")
            print(f"    network error ({e}); retrying in {wait} s")
            clock.sleep(wait)


def holidays_seen():
    """Days NSE answered 404 for (no bhavcopy): not fetched again."""
    if not MANIFEST.exists():
        return set()
    with MANIFEST.open(newline="") as f:
        return {r["url"] for r in csv.DictReader(f) if r["status"] == "404"}


def cmd_nse(args):
    """One raw file per NSE trading day with the ELECMBL rows of the commodity bhavcopy.

    Weekdays only. A 404 is a holiday (logged, not retried); any other error stops the run,
    and whatever was saved before it stays saved.
    """
    first = date.fromisoformat(args.start) if args.start else NSE_LAUNCH
    last = date.fromisoformat(args.end) if args.end else datetime.now(IST).date()
    NSE_DIR.mkdir(parents=True, exist_ok=True)
    skip = holidays_seen()
    todo = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    todo = [d for d in todo if d.weekday() < 5 and not (NSE_DIR / f"elecmbl_{d:%Y%m%d}.csv").exists()
            and NSE_URL.format(d=d) not in skip]
    print(f"{len(todo)} weekdays to fetch, about {len(todo) * NSE_DELAY_SECONDS // 60 + 1} min or more")
    saved = holidays = 0
    for i, d in enumerate(todo):
        if i:
            clock.sleep(NSE_DELAY_SECONDS)
        url = NSE_URL.format(d=d)
        try:
            body = download(url)
        except urllib.error.HTTPError as e:
            log_request(url, e.code)
            if e.code == 404:
                holidays += 1
                print(f"  {d}  no file (holiday)")
                continue
            sys.exit(f"stopped at {d}: HTTP {e.code}")
        log_request(url, 200, body)
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            text = z.read(z.namelist()[0]).decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = [r for r in reader if r["TckrSymb"] == NSE_SYMBOL]
        with (NSE_DIR / f"elecmbl_{d:%Y%m%d}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=reader.fieldnames)
            w.writeheader()
            w.writerows(rows)
        saved += 1
        print(f"  {d}  {len(rows)} contracts")
    print(f"saved {saved} days, {holidays} holidays")


# ---------------------------------------------------------------- MCX via Upstox

# MCX's own site refuses scripted requests. Upstox's public API serves daily candles for
# contracts still trading (back to their listing day); expired contracts need a logged-in
# Upstox token. Each run saves the answer as published: raw/mcx_upstox/<key>_<fetch date>.json.
MCX_DIR = RAW_DIR / "mcx_upstox"
UPSTOX_INSTRUMENTS = "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json.gz"
UPSTOX_CANDLES = "https://api.upstox.com/v2/historical-candle/{key}/day/{to}/{frm}"
MCX_SYMBOL = "ELECDMBL"
MCX_LAUNCH = date(2025, 7, 10)


def fetch(url):
    try:
        body = download(url)
    except urllib.error.HTTPError as e:
        log_request(url, e.code)
        sys.exit(f"HTTP {e.code} for {url}")
    log_request(url, 200, body)
    return body


def cmd_mcx(args):
    """Daily candles for every ELECDMBL contract Upstox lists as trading today."""
    import gzip
    import json
    listed = json.loads(gzip.decompress(fetch(UPSTOX_INSTRUMENTS)))
    contracts = sorted((x for x in listed if x.get("underlying_symbol") == MCX_SYMBOL
                        or x.get("trading_symbol", "").startswith(MCX_SYMBOL + " ")),
                       key=lambda x: x["expiry"])
    today = datetime.now(IST).date()
    MCX_DIR.mkdir(parents=True, exist_ok=True)
    for x in contracts:
        clock.sleep(NSE_DELAY_SECONDS)
        expiry = datetime.fromtimestamp(x["expiry"] / 1000, IST).date()
        url = UPSTOX_CANDLES.format(key=x["instrument_key"].replace("|", "%7C"), to=today, frm=MCX_LAUNCH)
        body = fetch(url)
        answer = json.loads(body)
        if answer.get("status") != "success":
            sys.exit(f"Upstox refused {x['trading_symbol']}: {answer.get('errors')}")
        out = {"instrument": {k: x.get(k) for k in ("instrument_key", "trading_symbol", "expiry", "lot_size")},
               "expiry_date": expiry.isoformat(), "fetched_at": datetime.now(IST).isoformat(timespec="seconds"),
               "url": url, "answer": answer}
        path = MCX_DIR / f"{MCX_SYMBOL}_{expiry:%Y%m%d}_{today:%Y%m%d}.json"
        path.write_text(json.dumps(out, indent=1))
        candles = answer["data"]["candles"]
        print(f"  {x['trading_symbol']:26} {len(candles):3} days"
              f"{'  ' + candles[-1][0][:10] + ' to ' + candles[0][0][:10] if candles else ''}")


def mcx_rows():
    """Latest fetch of each contract wins; candles are [time, open, high, low, close, volume, oi]."""
    import json
    latest = {}
    for p in sorted(MCX_DIR.glob(f"{MCX_SYMBOL}_*.json")):
        latest[p.name.split("_")[1]] = p  # later fetch dates sort last
    rows = []
    for p in latest.values():
        doc = json.loads(p.read_text())
        for t, o, h, l, c, vol, oi in doc["answer"]["data"]["candles"]:
            rows.append({"exchange": "MCX", "trade_date": t[:10], "contract": doc["expiry_date"][:7],
                         "expiry": doc["expiry_date"], "open": o, "high": h, "low": l, "close": c,
                         "lots": vol, "open_interest_lots": oi, "source": p.relative_to(ROOT).as_posix()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- build

FUTURES_CSV = DATA_DIR / "futures_daily.csv"
COLUMNS = ["exchange", "trade_date", "contract", "expiry", "open", "high", "low", "close", "settle",
           "prev_close", "lots", "mwh", "value_rs", "open_interest_lots", "trades", "source"]
NSE_MAP = {"trade_date": "TradDt", "expiry": "XpryDt", "open": "OpnPric", "high": "HghPric",
           "low": "LwPric", "close": "ClsPric", "settle": "SttlmPric", "prev_close": "PrvsClsgPric",
           "lots": "TtlTradgVol", "value_rs": "TtlTrfVal", "open_interest_lots": "OpnIntrst",
           "trades": "TtlNbOfTxsExctd"}


def nse_rows():
    parts = []  # one per trading day
    for p in sorted(NSE_DIR.glob("elecmbl_*.csv")):
        raw = pd.read_csv(p, dtype=str)
        if raw.empty:
            continue
        df = pd.DataFrame({ours: raw[theirs] for ours, theirs in NSE_MAP.items()})
        df["source"] = p.relative_to(ROOT).as_posix()
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df["exchange"] = "NSE"
    df["contract"] = df.expiry.str[:7]
    return df


CONTRACTS_CSV = DATA_DIR / "contracts.csv"


def contract_table(df):
    """One row per exchange and contract. final_settle is the settlement price on the expiry
    day, so it is filled only once a contract has expired and that day is in the data."""
    rows = []
    for (ex, c), g in df.sort_values("trade_date").groupby(["exchange", "contract"]):
        expiry = g.expiry.iloc[-1]
        last = g[g.trade_date == expiry]
        traded = g[g.lots > 0]
        rows.append({"exchange": ex, "contract": c, "expiry": expiry,
                     "first_listed": g.trade_date.iloc[0],
                     "first_traded": traded.trade_date.iloc[0] if len(traded) else None,
                     "last_date": g.trade_date.iloc[-1], "days_listed": len(g), "days_traded": len(traded),
                     "lots": int(g.lots.sum()), "mwh": int(g.mwh.sum()),
                     "value_rs": g.value_rs.sum() if ex == "NSE" else None,
                     "final_settle": last.settle.iloc[0] if len(last) and ex == "NSE" else None})
    return pd.DataFrame(rows)


def cmd_build(args):
    parts = [f() for f, d in ((nse_rows, NSE_DIR), (mcx_rows, MCX_DIR)) if d.exists()]
    df = pd.concat([p for p in parts if len(p)], ignore_index=True).reindex(columns=COLUMNS)
    for c in ["open", "high", "low", "close", "settle", "prev_close", "value_rs"]:
        df[c] = pd.to_numeric(df[c])
    for c in ["lots", "open_interest_lots", "trades"]:
        df[c] = pd.to_numeric(df[c]).astype("Int64")  # MCX via Upstox has no trade count
    df["mwh"] = df.lots * LOT_MWH
    df = df[COLUMNS].sort_values(["exchange", "trade_date", "contract"])
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(FUTURES_CSV, index=False)
    print(f"wrote {FUTURES_CSV.relative_to(ROOT)}  {len(df)} rows")
    contracts = contract_table(df)
    contracts.to_csv(CONTRACTS_CSV, index=False)
    print(f"wrote {CONTRACTS_CSV.relative_to(ROOT)}  {len(contracts)} contracts")
    for ex, g in df.groupby("exchange"):
        print(f"  {ex}: {g.trade_date.nunique()} days {g.trade_date.min()} to {g.trade_date.max()}, "
              f"{g.contract.nunique()} contracts {g.contract.min()} to {g.contract.max()}")


# ---------------------------------------------------------------- IEX day-ahead market

# Complete months come from the sibling power_market repo (../power_market/raw/dam, or
# $POWER_MARKET_DIR), parsed with its own bess.parse_snapshot. The current month, which
# power_market does not fetch, is saved here as raw/iex/dam_YYYY-MM_to_DD.html.
POWER_MARKET_DIR = Path(os.environ.get("POWER_MARKET_DIR", ROOT.parent / "power_market")).resolve()
IEX_DIR = RAW_DIR / "iex"
IEX_DAILY_CSV = DATA_DIR / "iex_daily.csv"
IEX_FROM = "2025-06"  # a month before the futures launched


def load_bess():
    if not (POWER_MARKET_DIR / "bess.py").exists():
        sys.exit(f"bess.py not found in {POWER_MARKET_DIR}; set POWER_MARKET_DIR")
    sys.path.insert(0, str(POWER_MARKET_DIR))
    import bess
    return bess


def fetch_iex_month_to_date(bess):
    """DAM for the current month up to the latest published day (D+1 is out by 15:00 IST)."""
    now = datetime.now(IST)
    first = now.date().replace(day=1)
    last = now.date() + timedelta(days=1) if now.hour >= 15 else now.date()
    path = IEX_DIR / f"dam_{first:%Y-%m}_to_{last:%d}.html"
    if path.exists():
        print(f"  {path.relative_to(ROOT)} already saved")
        return
    url = bess.snapshot_url("DAM", first, last)
    body = download(url)
    log_request(url, 200, body)
    days = {r["date"] for r in bess.page_records(body.decode("utf-8", "replace"))}
    if len(days) != (last - first).days + 1:
        sys.exit(f"IEX page has {len(days)} days, expected {(last - first).days + 1}; not saved")
    IEX_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    print(f"  saved {path.relative_to(ROOT)}  {len(days)} days")


def cmd_iex(args):
    """data/iex_daily.csv: one row per DAM delivery day. Prices Rs/MWh, volumes MWh."""
    bess = load_bess()
    if args.fetch:
        fetch_iex_month_to_date(bess)
    complete = [p for p in sorted((POWER_MARKET_DIR / "raw" / "dam").glob("dam_*.html")) if p.stem[4:] >= IEX_FROM]
    partial = sorted(IEX_DIR.glob("dam_*_to_*.html"), reverse=True)  # latest first
    seen, rows = set(), []
    for p in complete + partial:  # a complete month wins over a partial one
        b = pd.DataFrame(bess.parse_snapshot("DAM", p.read_text()))
        b = b[~((b.mcv_mw == 0) & (b.mcp_rs_mwh == 0))]  # no-trade blocks are not Rs 0 prices
        for d, g in b.groupby("delivery_date"):
            if d in seen:
                continue
            seen.add(d)
            rows.append({"delivery_date": d, "blocks": len(g),
                         "simple_avg": round(g.mcp_rs_mwh.mean(), 2),
                         "vw_avg": round((g.mcp_rs_mwh * g.mcv_mw).sum() / g.mcv_mw.sum(), 2),
                         "min_block": g.mcp_rs_mwh.min(), "max_block": g.mcp_rs_mwh.max(),
                         "mcv_mwh": round(g.mcv_mw.sum() / 4, 2),
                         "source": p.relative_to(p.parents[2]).as_posix() if p.is_relative_to(ROOT)
                         else f"power_market/{p.relative_to(POWER_MARKET_DIR).as_posix()}"})
    df = pd.DataFrame(rows).sort_values("delivery_date")
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(IEX_DAILY_CSV, index=False)
    print(f"wrote {IEX_DAILY_CSV.relative_to(ROOT)}  {len(df)} days, {df.delivery_date.min()} to {df.delivery_date.max()}")


# ---------------------------------------------------------------- NSE against IEX

NSE_IEX_CSV = DATA_DIR / "nse_vs_iex.csv"
RECENT_DAYS = 7  # volume assumed for unknown days: the mean of the last 7 known days


def settlement_days(contract, expiry):
    """Delivery days NSE's final settlement covers: the month's days IEX has published by the
    expiry date, i.e. up to expiry + 1 (DAM for day D is out on D-1), never past month-end.
    Inferred from the 3 contracts expiring 2+ days before month-end (README)."""
    first = pd.Timestamp(contract + "-01")
    last = min(pd.Timestamp(expiry) + pd.Timedelta(days=1), first + pd.offsets.MonthEnd(0))
    return first, last


def cmd_join(args):
    """One row per NSE contract and trade date, with what IEX had published by that close.

    NSE settles on the IEX volume-weighted price of the delivery days published by expiry
    (settlement_days). DAM prices for day D are public by 15:00 on D-1 and NSE commodities
    trade until 23:30, so the close on trade date T knows delivery days up to T+1. Columns:
      settle_days                       delivery days the final settlement covers
      days_known, known_mwh, vw_so_far  those days known at this close, their MWh and VW price
      final_vw                          IEX VW over all settle_days (once all are published)
      implied_rest                      VW the unknown settle_days need for the settlement price
                                        to equal final_vw, their volume set to the last 7 days' mean
    """
    fut = pd.read_csv(FUTURES_CSV, dtype={"contract": str})
    fut = fut[fut.exchange == "NSE"]
    iex = pd.read_csv(IEX_DAILY_CSV, parse_dates=["delivery_date"])
    iex["pv"] = iex.vw_avg * iex.mcv_mwh
    last_day = iex.delivery_date.max()
    finals = pd.read_csv(CONTRACTS_CSV, dtype={"contract": str}).query("exchange == 'NSE'").set_index("contract").final_settle
    windows = {}
    for c, expiry in fut.groupby("contract").expiry.last().items():
        first, last = settlement_days(c, expiry)
        days = iex[iex.delivery_date.between(first, last)]
        n = (last - first).days + 1
        windows[c] = (first, last, n, days.pv.sum() / days.mcv_mwh.sum() if len(days) == n else None)
    rows = []
    for r in fut.itertuples():
        first, last, n_days, final_vw = windows[r.contract]
        cutoff = min(pd.Timestamp(r.trade_date) + pd.Timedelta(days=1), last_day)
        known = iex[iex.delivery_date.between(first, min(cutoff, last))]
        recent = iex[iex.delivery_date <= cutoff].tail(RECENT_DAYS)
        known_mwh = known.mcv_mwh.sum()
        rest_mwh = (n_days - len(known)) * recent.mcv_mwh.mean()
        price = r.settle if pd.notna(r.settle) else r.close
        rest = (price * (known_mwh + rest_mwh) - known.pv.sum()) / rest_mwh if rest_mwh else None
        rows.append({"trade_date": r.trade_date, "contract": r.contract, "settle": r.settle, "close": r.close,
                     "lots": r.lots, "settle_days": n_days, "days_known": len(known),
                     "known_mwh": round(known_mwh), "vw_so_far": round(known.pv.sum() / known_mwh, 2) if len(known) else None,
                     "last_7d_vw": round(recent.pv.sum() / recent.mcv_mwh.sum(), 2),
                     "implied_rest": round(rest, 2) if rest is not None else None,
                     "final_vw": round(final_vw, 2) if final_vw else None,
                     "nse_final": finals.get(r.contract)})
    out = pd.DataFrame(rows)
    out.to_csv(NSE_IEX_CSV, index=False)
    print(f"wrote {NSE_IEX_CSV.relative_to(ROOT)}  {len(out)} rows; IEX data to {last_day.date()}")


def cmd_firstlook(args):
    """How far NSE's settlement price was from the final, against a naive estimate, on traded
    days only (a day with no trades has a price NSE sets itself, not a market price)."""
    d = pd.read_csv(NSE_IEX_CSV, dtype={"contract": str})
    d = d[d.nse_final.notna() & d.settle.notna() & (d.lots > 0)]
    d = d[d.days_known < d.settle_days].copy()  # expiry day: the settlement is the final itself
    iex = pd.read_csv(IEX_DAILY_CSV, parse_dates=["delivery_date"])
    t = pd.to_datetime(d.trade_date)
    # naive: known days at their VW, the rest at the last 7 days' VW, volume as in implied_rest
    rest_mwh = [(r.settle_days - r.days_known) * iex[iex.delivery_date <= tt + pd.Timedelta(days=1)].tail(RECENT_DAYS).mcv_mwh.mean()
                for r, tt in zip(d.itertuples(), t)]
    d["rest_mwh"] = rest_mwh
    d["naive"] = (d.vw_so_far.fillna(0) * d.known_mwh + d.last_7d_vw * d.rest_mwh) / (d.known_mwh + d.rest_mwh)
    d["err_nse"] = (d.settle / d.nse_final - 1) * 100
    d["err_naive"] = (d.naive / d.nse_final - 1) * 100
    before = (pd.to_datetime(d.contract + "-01") - t).dt.days
    d["when"] = pd.cut(before, [0, 30, 60, 1000], labels=["1 month before", "2 months before", "3 months before"])
    d["when"] = d.when.astype(str).where(d.days_known == 0, pd.cut(d.days_known, [0, 10, 20, 31],
                                         labels=["1-10 days known", "11-20 days known", "21+ days known"]).astype(str))
    order = ["3 months before", "2 months before", "1 month before", "1-10 days known", "11-20 days known", "21+ days known"]
    out = d.groupby("when").agg(rows=("err_nse", "size"), contracts=("contract", "nunique"),
                                nse=("err_nse", lambda x: x.abs().mean()), naive=("err_naive", lambda x: x.abs().mean()),
                                nse_bias=("err_nse", "mean"), nse_beats_naive=("err_nse", lambda x: None))
    out["nse_beats_naive"] = d.assign(b=d.err_nse.abs() < d.err_naive.abs()).groupby("when").b.mean() * 100
    out = out.reindex([o for o in order if o in out.index])
    print(f"traded days only: {len(d)} rows, {d.contract.nunique()} contracts; errors in % of the final")
    print(out.round(1).to_string())


# ---------------------------------------------------------------- dashboard data

DASHBOARD_DIR = DATA_DIR / "dashboard"


def cmd_export(args):
    """Small CSVs for the NSE dashboard, built only from the tables above."""
    fut = pd.read_csv(FUTURES_CSV, dtype={"contract": str}).query("exchange == 'NSE'")
    join = pd.read_csv(NSE_IEX_CSV, dtype={"contract": str})
    iex = pd.read_csv(IEX_DAILY_CSV)
    con = pd.read_csv(CONTRACTS_CSV, dtype={"contract": str}).query("exchange == 'NSE'")
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    days = fut[["trade_date", "contract", "expiry", "open", "high", "low", "close", "settle", "lots",
                "open_interest_lots"]].merge(
        join[["trade_date", "contract", "settle_days", "days_known", "vw_so_far", "last_7d_vw", "implied_rest",
              "final_vw", "nse_final"]], on=["trade_date", "contract"], how="left")
    days["days_to_expiry"] = (pd.to_datetime(days.expiry) - pd.to_datetime(days.trade_date)).dt.days
    days["pct_from_final"] = ((days.settle / days.nse_final - 1) * 100).round(2)
    for c in ("open", "high", "low"):  # untraded days are published as 0
        days.loc[days.lots == 0, c] = None

    iex["pv"] = iex.vw_avg * iex.mcv_mwh
    dates = pd.to_datetime(iex.delivery_date)
    stats = []
    for k in con.itertuples():  # IEX over the delivery days the final settlement covers
        first, last = settlement_days(k.contract, k.expiry)
        g = iex[dates.between(first, last)]
        stats.append({"contract": k.contract, "settle_days": (last - first).days + 1, "iex_days": len(g),
                      "iex_vw": round(g.pv.sum() / g.mcv_mwh.sum(), 2) if len(g) else None,
                      "iex_simple": round((g.simple_avg * g.blocks).sum() / g.blocks.sum(), 2) if len(g) else None})
    con = con[["contract", "expiry", "first_listed", "first_traded", "days_listed", "days_traded", "lots",
               "mwh", "value_rs", "final_settle"]].merge(pd.DataFrame(stats), on="contract", how="left")
    con["final_vs_iex_vw_pct"] = ((con.final_settle / con.iex_vw - 1) * 100).round(2)

    out = {"contract_days": days, "iex_daily": iex[["delivery_date", "vw_avg", "simple_avg", "min_block",
                                                     "max_block", "mcv_mwh"]], "contracts": con}
    for name, t in out.items():
        path = DASHBOARD_DIR / f"{name}.csv"
        t.to_csv(path, index=False)
        print(f"wrote {path.relative_to(ROOT)}  {len(t)} rows")


# ---------------------------------------------------------------- checks

DAILY_LIMIT = 0.09  # widest daily price band (6%, widening to 9%), around the previous settlement


def cmd_check(args):
    """Sanity checks on data/futures_daily.csv. Prints findings by kind; changes nothing."""
    df = pd.read_csv(FUTURES_CSV, dtype={"contract": str}).sort_values("trade_date")
    traded = df[df.lots > 0]
    found = {}

    def add(kind, text):
        found.setdefault(kind, []).append(text)

    for r in traded.itertuples():
        if r.low > min(r.open, r.close) or r.high < max(r.open, r.close):
            add("low/high do not bracket open and close", f"{r.exchange} {r.trade_date} {r.contract}")
    nse = df[df.exchange == "NSE"].copy()
    nse["prev_settle"] = nse.groupby("contract").settle.shift()
    for r in nse[nse.lots > 0].itertuples():
        if r.value_rs / r.mwh < r.low * 0.999 or r.value_rs / r.mwh > r.high * 1.001:
            add("NSE traded value / MWh outside the day's range", f"{r.trade_date} {r.contract}")
        if pd.notna(r.prev_settle) and r.prev_settle > 0:
            for name, v in (("high", r.high), ("low", r.low)):
                move = v / r.prev_settle - 1
                if abs(move) > DAILY_LIMIT + 0.001:
                    add("NSE price beyond 9% of the previous settlement",
                        f"{r.trade_date} {r.contract} {name} {v:.0f} vs {r.prev_settle:.0f} ({move:+.1%})")
    for (ex, d), n in df.groupby(["exchange", "trade_date"]).contract.nunique().items():
        if ex == "NSE" and n < 3:
            add("NSE days with fewer than 3 contracts listed", f"{d}: {n}")

    print(f"{len(df)} rows checked")
    for kind, items in found.items():
        print(f"  {kind}: {len(items)}")
        for t in items[:args.show]:
            print(f"    {t}")
    if not found:
        print("  no findings")
    mcx = df[df.exchange == "MCX"]
    if len(mcx):
        print(f"  MCX coverage: {', '.join(sorted(mcx.contract.unique()))} only "
              f"(expired contracts are not available from Upstox without a login)")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nse", help="fetch NSE electricity futures from the daily commodity bhavcopy")
    n.add_argument("--from", dest="start", help="first trade date, YYYY-MM-DD (default: launch, 2025-07-14)")
    n.add_argument("--to", dest="end", help="last trade date (default: today, IST)")
    sub.add_parser("mcx", help="fetch MCX electricity futures still trading, via Upstox")
    sub.add_parser("build", help="raw/ -> data/futures_daily.csv")
    ix = sub.add_parser("iex", help="IEX DAM daily table from power_market (+ current month here)")
    ix.add_argument("--fetch", action="store_true", help="first fetch the current month to date from IEX")
    sub.add_parser("join", help="NSE contract-days against the IEX days known at each close")
    sub.add_parser("firstlook", help="settlement price vs final, traded days only, against a naive estimate")
    sub.add_parser("export", help="CSVs for the NSE dashboard -> data/dashboard/")
    ck = sub.add_parser("check", help="sanity checks on data/futures_daily.csv")
    ck.add_argument("--show", type=int, default=5, help="examples to print per kind of finding")
    args = p.parse_args()
    {"nse": cmd_nse, "mcx": cmd_mcx, "build": cmd_build, "check": cmd_check,
     "iex": cmd_iex, "join": cmd_join, "export": cmd_export, "firstlook": cmd_firstlook}[args.cmd](args)


if __name__ == "__main__":
    main()
