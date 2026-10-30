"""Meetproef D — verzamelscript.

Legt een week lang het orderboek vast (beste bied/laat bij elke wijziging, top 5 één keer
per seconde) en alle trades
van een paar kleine Hyperliquid-perps plus BTC als referentie. Daarmee meet analyse.py of
passief market making daar na kosten iets oplevert.

Gebruik (Mac, laptop aan de lader, deksel open):
    pip3 install "websockets>=10,<14" requests
    caffeinate -is python3 collect.py              # coins automatisch kiezen
    caffeinate -is python3 collect.py SOL WIF ...  # of zelf kiezen

Stoppen: Ctrl+C. Opnieuw starten mag altijd: er wordt gewoon bijgeschreven.
Data komt in ./data/<datum>/ (niet in git). Reken op ±50–100 MB per dag (gecomprimeerd).
Werkt met Python 3.8 en nieuwer. Geen sleutels, geen account: enkel publieke marktdata.
"""
import asyncio
import gzip
import os
import json
import random
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import websockets

WS = os.environ.get("HL_WS", "wss://api.hyperliquid.xyz/ws")   # HL_WS enkel voor tests
INFO = "https://api.hyperliquid.xyz/info"
OUT = Path(os.environ.get("MEETPROEF_OUT", Path(__file__).resolve().parent / "data"))
DEPTH = 5
N_SMALL = 4
VOL_MIN, VOL_MAX = 2e6, 50e6        # 24u-volume in USD voor "kleine maar actieve" markten


def pick_coins():
    meta, ctxs = requests.post(INFO, json={"type": "metaAndAssetCtxs"}, timeout=20).json()
    rows = []
    for asset, ctx in zip(meta["universe"], ctxs):
        if asset.get("isDelisted"):
            continue
        vol = float(ctx.get("dayNtlVlm") or 0)
        if VOL_MIN <= vol <= VOL_MAX:
            rows.append((vol, asset["name"]))
    rows.sort()
    if len(rows) < N_SMALL:
        raise SystemExit(f"Te weinig markten tussen {VOL_MIN:,.0f} en {VOL_MAX:,.0f} USD volume")
    # spreiden over het volumebereik: van rustig tot redelijk druk
    idx = [round(i * (len(rows) - 1) / (N_SMALL - 1)) for i in range(N_SMALL)]
    return [rows[i][1] for i in idx], {name: vol for vol, name in rows}


class Writer:
    """Eén gzip-bestand per coin per soort per UTC-dag; wordt elke 10 seconden geflusht."""

    def __init__(self):
        self.files, self.day, self.last_flush = {}, None, time.time()

    def _f(self, coin, kind):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if day != self.day:
            self.close()
            self.day = day
            (OUT / day).mkdir(parents=True, exist_ok=True)
        key = (coin, kind)
        if key not in self.files:
            self.files[key] = gzip.open(OUT / self.day / f"{coin}_{kind}.jsonl.gz", "at", encoding="utf-8")
        return self.files[key]

    def write(self, coin, kind, row):
        self._f(coin, kind).write(json.dumps(row, separators=(",", ":")) + "\n")
        if time.time() - self.last_flush > 10:
            for f in self.files.values():
                f.flush()
            self.last_flush = time.time()

    def close(self):
        for f in self.files.values():
            f.close()
        self.files = {}


async def run(coins):
    writer = Writer()
    latest = {}                       # coin -> laatste boek (top 5)
    last_bbo = {}                     # coin -> laatste (beste bied, beste laat)
    written = {}                      # coin -> tijd van laatst weggeschreven boek
    counts = {c: {"books": 0, "trades": 0} for c in coins}
    backoff = 1

    async def snapshotter():
        while True:
            await asyncio.sleep(1)
            for coin, book in list(latest.items()):
                if written.get(coin) != book["t"]:
                    writer.write(coin, "book", book)
                    written[coin] = book["t"]
                    counts[coin]["books"] += 1

    async def reporter():
        while True:
            await asyncio.sleep(3600)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            print(f"[{now} UTC] " + ", ".join(f"{c}: {v['books']} boeken/{v['trades']} trades" for c, v in counts.items()),
                  flush=True)

    tasks = [asyncio.ensure_future(snapshotter()), asyncio.ensure_future(reporter())]
    try:
        while True:
            try:
                async with websockets.connect(WS, ping_interval=None, max_size=2 ** 22) as ws:
                    for coin in coins:
                        for typ in ("l2Book", "trades"):
                            await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": typ, "coin": coin}}))
                    print(f"Verbonden, {len(coins)} markten: {', '.join(coins)}", flush=True)
                    backoff = 1
                    last_ping = time.time()
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=20)
                        except asyncio.TimeoutError:
                            raw = None
                        if time.time() - last_ping > 30:
                            await ws.send(json.dumps({"method": "ping"}))
                            last_ping = time.time()
                        if raw is None:
                            continue
                        msg = json.loads(raw)
                        ch, data = msg.get("channel"), msg.get("data")
                        if ch == "l2Book":
                            bids, asks = data["levels"]
                            if not bids or not asks:
                                continue
                            coin = data["coin"]
                            latest[coin] = {"t": data["time"],
                                            "b": [[float(x["px"]), float(x["sz"])] for x in bids[:DEPTH]],
                                            "a": [[float(x["px"]), float(x["sz"])] for x in asks[:DEPTH]]}
                            # beste bied/laat bij ELKE wijziging (klein, nauwkeurig in de tijd)
                            bbo = (float(bids[0]["px"]), float(asks[0]["px"]))
                            if last_bbo.get(coin) != bbo:
                                last_bbo[coin] = bbo
                                writer.write(coin, "bbo", {"t": data["time"], "b": bbo[0], "bs": float(bids[0]["sz"]),
                                                           "a": bbo[1], "as": float(asks[0]["sz"])})
                        elif ch == "trades":
                            for tr in data:
                                writer.write(tr["coin"], "trades", {"t": tr["time"], "px": float(tr["px"]),
                                                                    "sz": float(tr["sz"]), "side": tr.get("side")})
                                counts[tr["coin"]]["trades"] += 1
            except (OSError, websockets.WebSocketException, asyncio.TimeoutError) as e:
                print(f"Verbinding verbroken ({e.__class__.__name__}: {e}); opnieuw over {backoff}s", flush=True)
                await asyncio.sleep(backoff + random.random())
                backoff = min(backoff * 2, 60)
    finally:
        for t in tasks:
            t.cancel()
        writer.close()


def main():
    OUT.mkdir(exist_ok=True)
    if len(sys.argv) > 1:
        small = sys.argv[1:]
        vols = {}
    else:
        small, vols = pick_coins()
    coins = small + (["BTC"] if "BTC" not in small else [])
    sel = {"started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "coins": coins,
           "volume_24h_usd": {c: vols.get(c) for c in small}}
    (OUT / "selectie.json").write_text(json.dumps(sel, indent=1))
    print(json.dumps(sel, indent=1), flush=True)
    def _stop(*_):
        raise KeyboardInterrupt            # ook bij 'kill' netjes afsluiten en alles wegschrijven
    signal.signal(signal.SIGTERM, _stop)
    try:
        asyncio.run(run(coins))
    except KeyboardInterrupt:
        print("Gestopt; alle data is weggeschreven.")


if __name__ == "__main__":
    main()
