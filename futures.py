"""Electricity futures data: MCX (ELECDMBL) and NSE (ELECMBL) daily prices, plus IEX DAM.

Standard library plus pandas. Run from the terminal:

    python futures.py nse [--from 2025-07-14] [--to 2026-10-14]   # NSE daily bhavcopy -> raw/nse/
    python futures.py mcx                                         # MCX contracts still trading, via Upstox
    python futures.py build                                       # raw/ -> data/futures_daily.csv
    python futures.py check                                       # sanity checks, prints findings

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
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
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
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
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
    for ex, g in df.groupby("exchange"):
        print(f"  {ex}: {g.trade_date.nunique()} days {g.trade_date.min()} to {g.trade_date.max()}, "
              f"{g.contract.nunique()} contracts {g.contract.min()} to {g.contract.max()}")


# ---------------------------------------------------------------- checks

DAILY_LIMIT = 0.09  # widest daily price band (6%, widening to 9%)


def cmd_check(args):
    """Sanity checks on data/futures_daily.csv. Prints findings; changes nothing."""
    df = pd.read_csv(FUTURES_CSV, dtype={"contract": str})
    traded = df[df.lots > 0]
    problems = []
    bad = traded[(traded.low > traded[["open", "close"]].min(axis=1)) | (traded.high < traded[["open", "close"]].max(axis=1))]
    problems += [f"{r.exchange} {r.trade_date} {r.contract}: low/high do not bracket open/close" for r in bad.itertuples()]
    nse = traded[traded.exchange == "NSE"].copy()
    implied = nse.value_rs / nse.mwh
    off = nse[(implied < nse.low * 0.999) | (implied > nse.high * 1.001)]
    problems += [f"NSE {r.trade_date} {r.contract}: value/MWh outside the day's range" for r in off.itertuples()]
    for (ex, c), g in df.sort_values("trade_date").groupby(["exchange", "contract"]):
        g = g[g.lots > 0]
        move = g.close.pct_change().abs()
        for r, m in zip(g.itertuples(), move):
            if m > DAILY_LIMIT + 0.005:
                problems.append(f"{ex} {r.trade_date} {c}: close moved {m:.1%} since the last traded day")
    per_day = df.groupby(["exchange", "trade_date"]).contract.nunique()
    for (ex, d), n in per_day.items():
        if n < 3:
            problems.append(f"{ex} {d}: only {n} contracts listed")
    print(f"{len(df)} rows checked, {len(problems)} findings")
    for p in problems:
        print("  " + p)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nse", help="fetch NSE electricity futures from the daily commodity bhavcopy")
    n.add_argument("--from", dest="start", help="first trade date, YYYY-MM-DD (default: launch, 2025-07-14)")
    n.add_argument("--to", dest="end", help="last trade date (default: today, IST)")
    sub.add_parser("mcx", help="fetch MCX electricity futures still trading, via Upstox")
    sub.add_parser("build", help="raw/ -> data/futures_daily.csv")
    sub.add_parser("check", help="sanity checks on data/futures_daily.csv")
    args = p.parse_args()
    {"nse": cmd_nse, "mcx": cmd_mcx, "build": cmd_build, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    main()
