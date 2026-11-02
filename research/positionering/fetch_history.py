"""Historiek van hefboom in de BTC-markt ophalen (publieke data, geen account nodig).

- Binance BTCUSDT-perp: funding per 8 uur, vanaf september 2019
- Bybit BTCUSDT-perp: open interest per dag (in BTC) en funding per 8 uur

Hyperliquid zelf geeft geen open-interest-historiek; Binance en Bybit zijn de grootste perp-markten
en dus de beste maat voor de hefboom in de hele markt.
Enkel standaard-Python (geen extra pakketten). Gebruik:  python3 fetch_history.py
Let op: Binance en Bybit blokkeren Amerikaanse IP-adressen, dus dit draait niet op GitHub Actions.
"""
import csv
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (btc-up-or-down onderzoek)"}


def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f"  poging {attempt + 1} mislukt: {e}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"niet bereikbaar: {url}")


def binance_funding():
    rows, start = [], 1567296000000          # 2019-09-01
    while True:
        batch = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime={start}&limit=1000")
        if not batch:
            break
        rows += [(b["fundingTime"], b["fundingRate"]) for b in batch]
        start = batch[-1]["fundingTime"] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.3)
    return rows


def bybit_paged(path, key_time, fields):
    rows, cursor = [], ""
    while True:
        url = f"https://api.bybit.com/v5/market/{path}&limit=200" + (f"&cursor={cursor}" if cursor else "")
        res = get(url)
        if res.get("retCode") != 0:
            raise RuntimeError(f"Bybit-fout: {res.get('retMsg')}")
        lst = res["result"].get("list", [])
        rows += [tuple(x[f] for f in (key_time,) + fields) for x in lst]
        cursor = res["result"].get("nextPageCursor") or ""
        if not lst or not cursor:
            break
        time.sleep(0.2)
    return rows


def bybit_funding():
    """Bybit geeft funding per pagina terug in de tijd; paginering via endTime."""
    rows, end = [], int(time.time() * 1000)
    while True:
        res = get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=200&endTime={end}")
        lst = res["result"].get("list", [])
        if not lst:
            break
        rows += [(x["fundingRateTimestamp"], x["fundingRate"]) for x in lst]
        oldest = min(int(x["fundingRateTimestamp"]) for x in lst)
        if oldest >= end or len(lst) < 200:
            break
        end = oldest - 1
        time.sleep(0.2)
    return rows


def save(name, header, rows):
    rows = sorted(set(rows), key=lambda r: int(r[0]))
    with open(HERE / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    first = time.strftime("%Y-%m-%d", time.gmtime(int(rows[0][0]) / 1000)) if rows else "-"
    last = time.strftime("%Y-%m-%d", time.gmtime(int(rows[-1][0]) / 1000)) if rows else "-"
    print(f"{name}: {len(rows)} rijen, {first} t/m {last}")


def main():
    print("Binance funding ...")
    save("binance_funding.csv", ["tijd_ms", "funding"], binance_funding())
    print("Bybit open interest (dag) ...")
    save("bybit_oi_dag.csv", ["tijd_ms", "oi_btc"],
         bybit_paged("open-interest?category=linear&symbol=BTCUSDT&intervalTime=1d", "timestamp", ("openInterest",)))
    print("Bybit funding ...")
    save("bybit_funding.csv", ["tijd_ms", "funding"], bybit_funding())


if __name__ == "__main__":
    main()
