"""Dagelijkse voorspelling + papieren portefeuille.

Draait elke dag rond 00:30 UTC, na het slot van 00:00 UTC.

1. Vult uitkomsten in van eerdere voorspellingen waarvan het slot nu bekend is.
2. Voegt de voorspelling voor VANDAAG toe (slot vandaag > slot gisteren?).
3. Werkt de papieren portefeuille bij tegen het echte Hyperliquid-orderboek.

Het log is append-only: bestaande voorspellingen worden nooit gewijzigd,
alleen hun uitkomst wordt ingevuld. Het script controleert dat zelf en
stopt als een bevroren veld toch zou veranderen.
"""
import json
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

from common import (DATA, FEATURES, MODEL_VERSION, TAKER_FEE, build_features, fit_model,
                    load_prices)

PRED = DATA / "predictions.json"
PAPER = DATA / "paper.json"
HL = "https://api.hyperliquid.xyz/info"
FROZEN = ("target_date", "made_at", "model_version", "p_up", "signal", "ref_close", "ref_date")
START_CAPITAL = 10_000.0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


# ---------- voorspelling ----------

def update_predictions(prices: pd.DataFrame) -> dict:
    log = load_json(PRED, [])
    before = {e["target_date"]: {k: e.get(k) for k in FROZEN} for e in log}
    closes = dict(zip(prices["date"].dt.strftime("%Y-%m-%d"), prices["close"]))

    # 1. uitkomsten invullen
    for e in log:
        if e.get("outcome") is None and e["target_date"] in closes:
            c = float(closes[e["target_date"]])
            e["close"] = c
            e["outcome"] = "up" if c > e["ref_close"] else "down"
            e["hit"] = (e["signal"] == e["outcome"])

    # 2. nieuwe voorspelling voor de dag na het laatste slot
    feat = build_features(prices)
    last = feat.iloc[-1]
    target = (last["date"] + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    new_entry = None
    if target not in before:
        train = feat.dropna(subset=FEATURES + ["y"])
        model = fit_model(train[FEATURES].values, train["y"].values)
        p = float(model.predict_proba(last[FEATURES].values.reshape(1, -1).astype(float))[0, 1])
        new_entry = {
            "target_date": target,
            "made_at": now_utc().isoformat(timespec="seconds"),
            "model_version": MODEL_VERSION,
            "p_up": round(p, 4),
            "signal": "up" if p > 0.5 else "down",
            "ref_date": last["date"].strftime("%Y-%m-%d"),
            "ref_close": round(float(last["close"]), 2),
            "outcome": None,
        }
        log.append(new_entry)

    # 3. bewaking: niets dat al gelogd was mag veranderd zijn
    for e in log:
        if e["target_date"] in before:
            now = {k: e.get(k) for k in FROZEN}
            if now != before[e["target_date"]]:
                sys.exit(f"STOP — bevroren voorspelling {e['target_date']} zou wijzigen")
    log.sort(key=lambda e: e["target_date"])
    PRED.write_text(json.dumps(log, indent=1))
    return new_entry or next(e for e in log if e["target_date"] == target)


# ---------- papieren portefeuille (Hyperliquid perps, 1x) ----------

def hl(payload):
    r = requests.post(HL, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def fill_price(book, side: str, notional: float) -> float:
    """VWAP als je als taker `notional` USD koopt (side=buy) of verkoopt."""
    levels = book["levels"][1] if side == "buy" else book["levels"][0]
    left, cost, qty = notional, 0.0, 0.0
    for lv in levels:
        px, sz = float(lv["px"]), float(lv["sz"])
        take = min(left, px * sz)
        cost += take
        qty += take / px
        left -= take
        if left <= 1e-9:
            break
    if left > 1e-9:
        raise RuntimeError("orderboek te dun voor dit bedrag")
    return cost / qty


def update_paper(pred_entry: dict) -> dict:
    st = load_json(PAPER, {"start_capital": START_CAPITAL, "equity": START_CAPITAL, "position": 0.0,
                           "units": 0.0, "last_mark": None, "last_time_ms": None,
                           "start_date": None, "start_mark": None, "history": []})
    if any(h["target_date"] == pred_entry["target_date"] for h in st["history"]):
        return st                                     # vandaag al verwerkt
    t_ms = int(now_utc().timestamp() * 1000)
    book = hl({"type": "l2Book", "coin": "BTC"})
    bid, ask = float(book["levels"][0][0]["px"]), float(book["levels"][1][0]["px"])
    mid = (bid + ask) / 2

    # a. resultaat van de lopende positie sinds de vorige run
    funding_paid = 0.0
    if st["units"] and st["last_mark"]:
        pnl = st["units"] * (mid - st["last_mark"])
        fh = hl({"type": "fundingHistory", "coin": "BTC", "startTime": st["last_time_ms"], "endTime": t_ms})
        # funding per uur: units * mark * rate, positief = long betaalt
        funding_paid = sum(st["units"] * mid * float(f["fundingRate"]) for f in fh)
        st["equity"] += pnl - funding_paid

    # b. herbalanceren naar de doelpositie (+1 long, -1 short)
    target_pos = 1.0 if pred_entry["signal"] == "up" else -1.0
    fee = slip = 0.0
    px = mid
    if target_pos == st["position"] and st["units"]:
        target_units = st["units"]                    # zelfde richting: niets doen, geen kosten
    else:
        target_units = target_pos * st["equity"] / mid
    delta = target_units - st["units"]
    if abs(delta) * mid > 1:                          # alleen handelen als de richting wijzigt
        side = "buy" if delta > 0 else "sell"
        px = fill_price(book, side, abs(delta) * mid)
        fee = abs(delta) * px * TAKER_FEE
        slip = abs(delta) * abs(px - mid)
        st["equity"] -= fee + slip
        target_units = target_pos * st["equity"] / mid
    st.update({"units": target_units, "position": target_pos, "last_mark": mid, "last_time_ms": t_ms})
    if st["start_date"] is None:
        st["start_date"], st["start_mark"] = pred_entry["target_date"], mid

    st["history"].append({
        "target_date": pred_entry["target_date"], "time": now_utc().isoformat(timespec="seconds"),
        "signal": pred_entry["signal"], "mid": round(mid, 2), "fill": round(px, 2),
        "fee": round(fee, 4), "slippage": round(slip, 4), "funding": round(funding_paid, 4),
        "equity": round(st["equity"], 2),
        "buy_hold": round(st["start_capital"] * mid / st["start_mark"], 2),
    })
    PAPER.write_text(json.dumps(st, indent=1))
    return st


def main():
    prices = load_prices()
    entry = update_predictions(prices)
    print(f"Voorspelling {entry['target_date']}: {entry['signal']} (p_up={entry['p_up']})")
    try:
        st = update_paper(entry)
        print(f"Papieren portefeuille: {st['equity']:.2f} USD, positie {st['position']:+.0f}")
    except Exception as e:                            # papier mag de voorspelling nooit blokkeren
        print(f"Papieren portefeuille overgeslagen: {e}")


if __name__ == "__main__":
    main()
