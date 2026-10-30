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
START_CAPITAL = 1_000.0
LATE_HOURS = 8   # een voorspelling die later dan 08:00 UTC op de doeldag gemaakt wordt, is "te laat"
SPOT_FEE = 0.0007   # Hyperliquid spot, taker, basisniveau
# Spoor B (30-10-2026): enkel long als het model minstens 60% kans op "omhoog" geeft, anders cash.
# Vastgelegd vóór de start van de live run; niet bijsturen tijdens de run.
CHALLENGERS = {
    "sterk60": {"label": "Uitdager B: long bij ≥60%, anders cash",
                "position": lambda p: 1.0 if p >= 0.60 else 0.0},
}
# Spoor C (30-10-2026), uit research/spoor_c. Vastgelegd vóór de start; niet bijsturen tijdens de run.
#  C1: trend-ensemble, spot long/cash: long als minstens 5 van 8 trendsignalen aan staan
#  C2: funding carry: helft spot-BTC, helft onderpand voor een even grote perp-short; verdient funding
C1_SMA = (20, 50, 100, 200)
C1_MOM = (14, 30, 60, 90)
C1_MIN_ON = 5
# C1b (30-10-2026, na de kluistoets): zelfde signalen, strengere drempel 6/8 = midden van het plateau 5–7/8.
# Gekozen met kennis van de kluis, dus enkel de live run telt als toets. C1 zelf blijft ongewijzigd.
C1B_MIN_ON = 6
# C1b+HLP (30-10-2026): C1b, maar de cash staat in de HLP-kluis van Hyperliquid zolang C1b uit staat.
# Echte HLP-opbrengst via de API. Na een storting zit HLP-geld 4 dagen vast: een koopsignaal binnen
# die 4 dagen wordt uitgesteld tot het geld vrijkomt (zoals in het echt).
HLP_VAULT = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
HLP_LOCK_MS = 4 * 24 * 3600 * 1000
CARRY_REBAL_LEV = 2.0   # herbalanceren als de short meer dan 2x zijn resterende onderpand waard is


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
        made = now_utc()
        delay_h = (made - pd.Timestamp(target, tz="UTC")).total_seconds() / 3600
        new_entry = {
            "target_date": target,
            "made_at": made.isoformat(timespec="seconds"),
            "delay_h": round(delay_h, 2),
            # te laat = meer dan LATE_HOURS na het begin van de doeldag; telt niet mee in de officiële cijfers
            "late": bool(delay_h > LATE_HOURS or delay_h < 0),
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


def fresh_paper() -> dict:
    return {"start_capital": START_CAPITAL, "equity": START_CAPITAL, "position": 0.0,
            "units": 0.0, "last_mark": None, "last_time_ms": None,
            "start_date": None, "start_mark": None, "history": []}


def c1_signals(prices: pd.DataFrame) -> int:
    """Aantal trendsignalen dat aan staat op het laatste afgesloten slot (0..8)."""
    c = prices["close"].reset_index(drop=True)
    on = [c.iloc[-1] > c.iloc[-n:].mean() for n in C1_SMA] + [c.iloc[-1] > c.iloc[-1 - L] for L in C1_MOM]
    return int(sum(bool(x) for x in on))


def update_paper(pred_entry: dict, target_pos: float = None, path=None,
                 fee_rate: float = TAKER_FEE, perp: bool = True, extra: dict = None) -> dict:
    """Papieren portefeuille bijwerken. target_pos: +1 long, 0 cash, -1 short.
    Standaard (kampioen): long bij 'up', short bij 'down'."""
    path = path or PAPER
    if target_pos is None:
        target_pos = 1.0 if pred_entry["signal"] == "up" else -1.0
    st = load_json(path, None) or fresh_paper()
    if st.get("start_capital") != START_CAPITAL:
        # ander startkapitaal = nieuwe run; de oude blijft bewaard in een archief
        archive = path.parent / f"{path.stem}_archive_{st.get('start_date') or 'leeg'}.json"
        archive.write_text(json.dumps(st, indent=1))
        print(f"Startkapitaal gewijzigd: oude run gearchiveerd in {archive.name}, nieuwe run start")
        st = fresh_paper()
    if any(h["target_date"] == pred_entry["target_date"] for h in st["history"]):
        return st                                     # vandaag al verwerkt
    if pred_entry.get("late"):
        print("Voorspelling te laat: geen papieren trade vandaag")
        path.write_text(json.dumps(st, indent=1))
        return st
    t_ms = int(now_utc().timestamp() * 1000)
    book = hl({"type": "l2Book", "coin": "BTC"})
    bid, ask = float(book["levels"][0][0]["px"]), float(book["levels"][1][0]["px"])
    mid = (bid + ask) / 2

    # a. resultaat van de lopende positie sinds de vorige run
    funding_paid = 0.0
    if st["units"] and st["last_mark"]:
        pnl = st["units"] * (mid - st["last_mark"])
        if perp:                                      # spot betaalt geen funding
            fh = hl({"type": "fundingHistory", "coin": "BTC", "startTime": st["last_time_ms"], "endTime": t_ms})
            # funding per uur: units * mark * rate, positief = long betaalt
            funding_paid = sum(st["units"] * mid * float(f["fundingRate"]) for f in fh)
        st["equity"] += pnl - funding_paid

    # b. herbalanceren naar de doelpositie (+1 long, 0 cash, -1 short)
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
        fee = abs(delta) * px * fee_rate
        slip = abs(delta) * abs(px - mid)
        st["equity"] -= fee + slip
        target_units = target_pos * st["equity"] / mid
    st.update({"units": target_units, "position": target_pos, "last_mark": mid, "last_time_ms": t_ms})
    if st["start_date"] is None:
        st["start_date"], st["start_mark"] = pred_entry["target_date"], mid

    st["history"].append({
        "target_date": pred_entry["target_date"], "time": now_utc().isoformat(timespec="seconds"),
        "signal": pred_entry["signal"], "position": target_pos, "mid": round(mid, 2), "fill": round(px, 2),
        "fee": round(fee, 4), "slippage": round(slip, 4), "funding": round(funding_paid, 4),
        "equity": round(st["equity"], 2),
        "buy_hold": round(st["start_capital"] * mid / st["start_mark"], 2),
        **(extra or {}),
    })
    path.write_text(json.dumps(st, indent=1))
    return st


def hlp_return(t0_ms: int, t1_ms: int) -> float:
    """Rendement van de HLP-kluis tussen t0 en t1: (winst(t1) - winst(t0)) / vermogen(t0).
    Gebruikt het kortste venster (dag/week/maand/alles) dat t0 nog bevat. Stortingen en opnames
    van anderen tellen niet mee, want we gebruiken de winstreeks, niet het vermogen."""
    d = hl({"type": "vaultDetails", "vaultAddress": HLP_VAULT})
    port = dict(d["portfolio"])
    for window in ("day", "week", "month", "allTime"):
        w = port.get(window)
        if not w or not w["pnlHistory"] or w["pnlHistory"][0][0] > t0_ms:
            continue
        pnl = [(t, float(v)) for t, v in w["pnlHistory"]]
        av = [(t, float(v)) for t, v in w["accountValueHistory"]]
        at = lambda series, t: [v for ts, v in series if ts <= t][-1]
        base = at(av, t0_ms)
        if base <= 0:
            continue
        return (at(pnl, t1_ms) - at(pnl, t0_ms)) / base
    raise RuntimeError("geen HLP-venster dat het begin bevat")


def update_c1b_hlp(entry: dict, n_on: int, path=None) -> dict:
    path = path or DATA / "paper_c1b_hlp.json"
    st = load_json(path, None) or {**fresh_paper(), "kind": "c1b_hlp", "hlp_since_ms": None, "hlp_last_ms": None}
    if any(h["target_date"] == entry["target_date"] for h in st["history"]):
        return st
    now_ms = int(now_utc().timestamp() * 1000)
    hlp_gain, note = 0.0, None
    # 1. HLP-opbrengst op de cash sinds de vorige run
    if st["position"] == 0 and st.get("hlp_last_ms"):
        try:
            r = hlp_return(st["hlp_last_ms"], now_ms)
            hlp_gain = st["equity"] * r
            st["equity"] += hlp_gain
        except Exception as e:
            note = f"HLP-opbrengst onbekend ({e}); als 0 geteld"
        st["hlp_last_ms"] = now_ms
    # 2. doelpositie, rekening houdend met de 4 dagen blokkering
    want = 1.0 if n_on >= C1B_MIN_ON else 0.0
    target = want
    if want == 1.0 and st["position"] == 0 and st.get("hlp_since_ms") and now_ms - st["hlp_since_ms"] < HLP_LOCK_MS:
        target = 0.0
        note = "koopsignaal, maar HLP-geld zit nog vast (4 dagen na storting): instap uitgesteld"
    path.write_text(json.dumps(st, indent=1))
    before = st["position"]
    st = update_paper(entry, target, path, fee_rate=SPOT_FEE, perp=False,
                      extra={"signals_on": n_on, "hlp_gain": round(hlp_gain, 4), **({"note": note} if note else {})})
    # 3. cash gaat (terug) naar HLP
    if st["position"] == 0 and (before != 0 or not st.get("hlp_since_ms")) and st["history"] \
            and st["history"][-1]["target_date"] == entry["target_date"]:
        st["hlp_since_ms"], st["hlp_last_ms"] = now_ms, now_ms
    if st["position"] != 0:
        st["hlp_since_ms"], st["hlp_last_ms"] = None, None
    path.write_text(json.dumps(st, indent=1))
    return st


def fresh_carry() -> dict:
    return {"kind": "carry", "start_capital": START_CAPITAL, "equity": START_CAPITAL, "position": 0.0,
            "units": 0.0, "entry": None, "collateral": START_CAPITAL, "last_time_ms": None,
            "start_date": None, "start_mark": None, "history": []}


def update_carry(target_date: str, path=None) -> dict:
    """C2: long `units` BTC spot + short `units` BTC perp. Koersbewegingen heffen elkaar op;
    het resultaat is de funding die de short ontvangt (of betaalt als ze negatief is), min kosten.
    Vermogen = units*entry + onderpand (blijft gelijk behalve funding en kosten)."""
    path = path or DATA / "paper_carry.json"
    st = load_json(path, None) or fresh_carry()
    if any(h["target_date"] == target_date for h in st["history"]):
        return st
    t_ms = int(now_utc().timestamp() * 1000)
    book = hl({"type": "l2Book", "coin": "BTC"})
    mid = (float(book["levels"][0][0]["px"]) + float(book["levels"][1][0]["px"])) / 2
    received = fee = 0.0
    if st["units"]:
        fh = hl({"type": "fundingHistory", "coin": "BTC", "startTime": st["last_time_ms"], "endTime": t_ms})
        received = sum(st["units"] * mid * float(f["fundingRate"]) for f in fh)   # positief = short ontvangt
        st["collateral"] += received
    equity = st["units"] * (st["entry"] or mid) + st["collateral"]
    margin_left = st["collateral"] + st["units"] * ((st["entry"] or mid) - mid)
    rebalance = (not st["units"]) or margin_left <= 0 or st["units"] * mid / margin_left > CARRY_REBAL_LEV
    if rebalance:                                     # (opnieuw) 50/50 zetten tegen de huidige koers
        new_units = equity / (2 * mid)
        d = abs(new_units - st["units"])
        fee = d * mid * (SPOT_FEE + TAKER_FEE)
        equity -= fee
        new_units = equity / (2 * mid)
        st.update({"units": new_units, "entry": mid, "collateral": equity - new_units * mid})
    st.update({"equity": equity, "last_time_ms": t_ms, "position": 0.0})
    if st["start_date"] is None:
        st["start_date"], st["start_mark"] = target_date, mid
    st["history"].append({
        "target_date": target_date, "time": now_utc().isoformat(timespec="seconds"), "mid": round(mid, 2),
        "fee": round(fee, 4), "slippage": 0.0, "funding": round(-received, 4), "rebalanced": rebalance,
        "equity": round(equity, 2), "buy_hold": round(st["start_capital"] * mid / st["start_mark"], 2),
    })
    path.write_text(json.dumps(st, indent=1))
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
    # uitdagers: zelfde voorspelling, andere handelsregel, eigen portefeuille
    for name, rule in CHALLENGERS.items():
        try:
            st = update_paper(entry, rule["position"](entry["p_up"]), DATA / f"paper_{name}.json")
            print(f"Uitdager {name}: {st['equity']:.2f} USD, positie {st['position']:+.0f}")
        except Exception as e:
            print(f"Uitdager {name} overgeslagen: {e}")
    # C1: trend-ensemble, spot long/cash (onafhankelijk van het voorspellingsmodel)
    try:
        n_on = c1_signals(prices)
        st = update_paper(entry, 1.0 if n_on >= C1_MIN_ON else 0.0, DATA / "paper_c1.json",
                          fee_rate=SPOT_FEE, perp=False, extra={"signals_on": n_on})
        print(f"C1 trend-ensemble ({n_on}/8 aan): {st['equity']:.2f} USD, positie {st['position']:+.0f}")
    except Exception as e:
        print(f"C1 overgeslagen: {e}")
    try:
        n_on = c1_signals(prices)
        st = update_paper(entry, 1.0 if n_on >= C1B_MIN_ON else 0.0, DATA / "paper_c1b.json",
                          fee_rate=SPOT_FEE, perp=False, extra={"signals_on": n_on})
        print(f"C1b trend 6/8 ({n_on}/8 aan): {st['equity']:.2f} USD, positie {st['position']:+.0f}")
    except Exception as e:
        print(f"C1b overgeslagen: {e}")
    try:
        st = update_c1b_hlp(entry, c1_signals(prices))
        print(f"C1b+HLP: {st['equity']:.2f} USD, positie {st['position']:+.0f}")
    except Exception as e:
        print(f"C1b+HLP overgeslagen: {e}")
    # C2: funding carry (marktneutraal)
    try:
        st = update_carry(entry["target_date"])
        print(f"C2 carry: {st['equity']:.2f} USD")
    except Exception as e:
        print(f"C2 overgeslagen: {e}")


if __name__ == "__main__":
    main()
