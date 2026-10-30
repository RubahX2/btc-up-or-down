"""Haalt BTC-dagkoersen (Yahoo) en Hyperliquid-funding op.

- Alleen AFGESLOTEN dagen: de lopende dag (UTC) wordt weggelaten.
- Controle op gaten en uitschieters; bij verdachte data stopt het script,
  zodat er die dag niets voorspeld wordt op foute data.
"""
import json
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from common import DATA

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD"
HL = "https://api.hyperliquid.xyz/info"
START = int(datetime(2014, 9, 17, tzinfo=timezone.utc).timestamp())
HL_START_MS = int(datetime(2023, 5, 1, tzinfo=timezone.utc).timestamp() * 1000)
UA = {"User-Agent": "Mozilla/5.0 (btc-up-or-down)"}


def fetch_prices() -> pd.DataFrame:
    now = int(time.time())
    params = {"period1": START, "period2": now, "interval": "1d", "events": "history"}
    res, last_err = None, None
    for attempt in range(4):
        try:
            r = requests.get(YAHOO, params=params, headers=UA, timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            body = r.json()
            chart = body.get("chart") or {}
            if chart.get("error") or not chart.get("result"):
                raise RuntimeError(f"Yahoo-fout: {chart.get('error') or 'lege result'}")
            res = chart["result"][0]
            break
        except Exception as e:
            last_err = e
            print(f"Yahoo poging {attempt + 1}/4 mislukt: {e}")
            time.sleep(10 * (attempt + 1))
    if res is None:
        sys.exit(f"STOP — Yahoo niet bereikbaar na 4 pogingen: {last_err}")
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_localize(None).normalize(),
        "open": q["open"], "high": q["high"], "low": q["low"],
        "close": q["close"], "volume": q["volume"],
    })
    df = df.dropna(subset=["close"]).drop_duplicates("date", keep="last")
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    df = df[df["date"] < today]                       # lopende dag eruit
    return df.sort_values("date").reset_index(drop=True)


def check_prices(df: pd.DataFrame) -> list:
    problems = []
    gaps = df["date"].diff().dt.days.fillna(1)
    recent = df["date"] >= df["date"].max() - pd.Timedelta(days=60)
    if (gaps[recent] > 1).any():
        problems.append(f"gat in de recente reeks: {int((gaps[recent] > 1).sum())} keer")
    jumps = df["close"].pct_change().abs()
    if jumps.iloc[-1] > 0.20:
        problems.append(f"sprong van {jumps.iloc[-1]:.0%} op de laatste dag")
    yesterday = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - pd.Timedelta(days=1)
    if df["date"].max() < yesterday:
        problems.append(f"verouderde data: laatste slot {df['date'].max().date()}")
    return problems


def fetch_funding(existing: pd.DataFrame) -> pd.DataFrame:
    """Uurlijkse funding van Hyperliquid, opgeteld per UTC-dag."""
    if len(existing):
        start = int(existing["date"].max().timestamp() * 1000)   # laatste dag opnieuw
    else:
        start = HL_START_MS
    rows = []
    while True:
        r = requests.post(HL, json={"type": "fundingHistory", "coin": "BTC", "startTime": start}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows += [(b["time"], float(b["fundingRate"])) for b in batch]
        last = batch[-1]["time"]
        if len(batch) < 500 or last <= start:
            break
        start = last + 1
        time.sleep(0.3)
    if not rows:
        return existing
    h = pd.DataFrame(rows, columns=["t", "rate"]).drop_duplicates("t")
    h["date"] = pd.to_datetime(h["t"], unit="ms").dt.normalize()
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    daily = h[h["date"] < today].groupby("date")["rate"].sum().rename("funding").reset_index()
    if len(existing):
        existing = existing[existing["date"] < daily["date"].min()] if len(daily) else existing
    return pd.concat([existing, daily]).sort_values("date").reset_index(drop=True)


def main():
    DATA.mkdir(exist_ok=True)
    status = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "problems": []}

    prices = fetch_prices()
    status["problems"] += check_prices(prices)
    prices.to_csv(DATA / "btc_daily.csv", index=False, float_format="%.6f")
    status["last_close_date"] = str(prices["date"].max().date())
    status["n_days"] = len(prices)

    fpath = DATA / "funding_daily.csv"
    existing = pd.read_csv(fpath, parse_dates=["date"]) if fpath.exists() else pd.DataFrame(columns=["date", "funding"])
    try:
        funding = fetch_funding(existing)
        funding.to_csv(fpath, index=False, float_format="%.8f")
        status["funding_days"] = len(funding)
    except Exception as e:                       # funding is niet kritiek voor de voorspelling
        status["problems"].append(f"funding niet opgehaald: {e}")

    (DATA / "fetch_status.json").write_text(json.dumps(status, indent=1))
    print(json.dumps(status, indent=1))
    critical = [p for p in status["problems"] if not p.startswith("funding")]
    if critical:
        print("Laatste 5 rijen:\n" + prices.tail(5).to_string())
        sys.exit("STOP — verdachte data: " + "; ".join(critical))


if __name__ == "__main__":
    main()
