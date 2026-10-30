"""Nep-Hyperliquid-websocket: zelfde berichtformaat, twee kunstmatige markten.
EDGE: trades zijn ruis (koers onafhankelijk van wie koopt) -> market maker verdient de halve spread.
TOXIC: na elke koop stijgt de koers sterk (geïnformeerde handelaars) -> market maker verliest.
Verbreekt na 6 s één keer de verbinding om het herverbinden te testen."""
import asyncio, json, random, sys, time
import websockets
mid = {"EDGE": 100.0, "TOXIC": 100.0}
first = {"done": False}
async def handler(ws):
    subs = set()
    start = time.time()
    async def reader():
        async for m in ws:
            d = json.loads(m)
            if d.get("method") == "subscribe":
                subs.add((d["subscription"]["type"], d["subscription"]["coin"]))
    rt = asyncio.ensure_future(reader())
    try:
        while True:
            await asyncio.sleep(0.05)
            now = int(time.time() * 1000)
            for coin in mid:
                spread = mid[coin] * 0.001                      # 10 bp
                if random.random() < 0.3:
                    buy = random.random() < 0.5
                    bid, ask = mid[coin] - spread / 2, mid[coin] + spread / 2
                    px = ask if buy else bid
                    if random.random() < 0.3: px = px + (spread * 0.2 if buy else -spread * 0.2)   # door het niveau
                    if ("trades", coin) in subs:
                        await ws.send(json.dumps({"channel": "trades", "data": [{"coin": coin, "side": "B" if buy else "A", "px": f"{px:.4f}", "sz": "1.0", "time": now}]}))
                    if coin == "TOXIC":
                        mid[coin] *= 1 + (0.0015 if buy else -0.0015)                         # 15 bp in de richting van de trade
                mid[coin] *= 1 + random.gauss(0, 0.00005)
                if ("l2Book", coin) in subs:
                    m, sp = mid[coin], mid[coin] * 0.001
                    lv = lambda p: {"px": f"{p:.4f}", "sz": "5.0", "n": 1}
                    await ws.send(json.dumps({"channel": "l2Book", "data": {"coin": coin, "time": now,
                        "levels": [[lv(m - sp/2 - i*sp) for i in range(6)], [lv(m + sp/2 + i*sp) for i in range(6)]]}}))
            if not first["done"] and time.time() - start > 6:
                first["done"] = True
                await ws.close(); return
    except websockets.ConnectionClosed:
        pass
    finally:
        rt.cancel()
async def main():
    async with websockets.serve(handler, "127.0.0.1", 8799):
        await asyncio.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 30)
asyncio.run(main())
