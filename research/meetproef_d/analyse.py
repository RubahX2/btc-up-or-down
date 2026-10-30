"""Meetproef D — analyse: verdient een passieve market maker hier iets, na kosten?

Methode ("markout"): stel dat we altijd een kleine koop-order op de beste bied-prijs en een
kleine verkoop-order op de beste laat-prijs hebben staan. Elke trade die tegen die prijs
(of erdoorheen) gebeurt, telt als een fictieve uitvoering van onze order. Daarna kijken we
waar de middenprijs h seconden later staat:
    gekocht op bied  -> resultaat = (midden_later - bied) / bied
    verkocht op laat -> resultaat = (laat - midden_later) / laat
Min de maker-fee van Hyperliquid (0,015% = 1,5 bp). Is dat gemiddeld positief, dan verdient
market making daar iets. Is het negatief, dan "eten" beter geïnformeerde handelaars de spread op
(adverse selectie).

Twee varianten, omdat we niet weten waar we in de wachtrij zouden staan:
    optimistisch:  elke trade op onze prijs vult ons
    pessimistisch: enkel trades die dóór onze prijs gaan vullen ons (wij stonden achteraan)

Gebruik:  python3 analyse.py [map met data, standaard ./data]
"""
import gzip
import json
import math
import sys
from bisect import bisect_left, bisect_right
from pathlib import Path

MAKER_FEE_BP = 1.5
HORIZONS = (1, 10, 60, 300)          # seconden
MAX_BOOK_AGE_MS = 5000          # boek ouder dan dit op het moment van de trade: trade overslaan


def read_jsonl(path):
    rows = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break                    # afgebroken laatste regel na een crash
    except (EOFError, OSError):
        pass                                 # afgebroken gzip: neem wat er is
    return rows


def load(root):
    data = {}
    for f in sorted(root.glob("*/*_book.jsonl.gz")):
        coin = f.name[: -len("_book.jsonl.gz")]
        data.setdefault(coin, {"book": [], "trades": []})["book"] += read_jsonl(f)
    for f in sorted(root.glob("*/*_trades.jsonl.gz")):
        coin = f.name[: -len("_trades.jsonl.gz")]
        data.setdefault(coin, {"book": [], "trades": []})["trades"] += read_jsonl(f)
    for f in sorted(root.glob("*/*_bbo.jsonl.gz")):
        coin = f.name[: -len("_bbo.jsonl.gz")]
        data.setdefault(coin, {"book": [], "trades": []}).setdefault("bbo", [])
        data[coin]["bbo"] += read_jsonl(f)
    for d in data.values():
        if d.get("bbo"):        # nauwkeurige reeks: gebruik die als boek (enkel top-niveau nodig)
            d["book"] = [{"t": r["t"], "b": [[r["b"], r["bs"]]], "a": [[r["a"], r["as"]]]} for r in d["bbo"]]
        d["book"] = [b for b in sorted(d["book"], key=lambda b: b["t"]) if b["b"] and b["a"]]
        d["trades"].sort(key=lambda t: t["t"])
    return data


def mean_t(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else float("nan")), float("nan"), n
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, (m / (sd / math.sqrt(n)) if sd > 0 else float("nan")), n


def analyse_coin(book, trades):
    times = [b["t"] for b in book]
    mids = [(b["b"][0][0] + b["a"][0][0]) / 2 for b in book]

    def book_at(t):
        # strikt VÓÓR de trade: een boekupdate met hetzelfde tijdstip (zelfde blok) is al ná de trade
        i = bisect_left(times, t) - 1
        return i if i >= 0 and t - times[i] <= MAX_BOOK_AGE_MS else None

    def mid_at(t):
        i = bisect_right(times, t) - 1
        return mids[i] if i >= 0 else None

    res = {"optimistisch": {h: [] for h in HORIZONS}, "pessimistisch": {h: [] for h in HORIZONS}}
    spreads = [(b["a"][0][0] - b["b"][0][0]) / ((b["a"][0][0] + b["b"][0][0]) / 2) * 1e4 for b in book]
    end_t = times[-1] if times else 0
    for tr in trades:
        i = book_at(tr["t"])
        if i is None:
            continue
        bid, ask = book[i]["b"][0][0], book[i]["a"][0][0]
        px = tr["px"]
        if px >= ask:            # koper neemt de laat-kant: onze verkooporder op `ask` wordt gevuld
            side, fill, through = -1, ask, px > ask
        elif px <= bid:          # verkoper neemt de bied-kant: onze kooporder op `bid` wordt gevuld
            side, fill, through = 1, bid, px < bid
        else:
            continue             # trade binnen de spread: telt niet
        for h in HORIZONS:
            if tr["t"] + h * 1000 > end_t:
                continue
            m = mid_at(tr["t"] + h * 1000)
            pnl = side * (m - fill) / fill * 1e4 - MAKER_FEE_BP
            res["optimistisch"][h].append(pnl)
            if through:
                res["pessimistisch"][h].append(pnl)
    hours = (end_t - times[0]) / 3.6e6 if times else 0
    return res, (sum(spreads) / len(spreads) if spreads else float("nan")), hours


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "data"
    data = load(root)
    if not data:
        raise SystemExit(f"Geen data gevonden in {root}")
    report = {}
    print(f"Maker-fee {MAKER_FEE_BP} bp per uitvoering. Resultaat in basispunten (1 bp = 0,01%) per fictieve uitvoering, NA fee.\n")
    for coin, d in sorted(data.items()):
        if len(d["book"]) < 10:
            continue
        res, spread_bp, hours = analyse_coin(d["book"], d["trades"])
        print(f"{coin}: {hours:.1f} uur data, gem. spread {spread_bp:.2f} bp, {len(d['trades'])} trades")
        report[coin] = {"uren": hours, "spread_bp": spread_bp}
        for var in ("optimistisch", "pessimistisch"):
            parts = []
            for h in HORIZONS:
                m, t, n = mean_t(res[var][h])
                parts.append(f"{h:>3}s: {m:+7.2f} bp (t={t:+5.1f}, n={n})")
                report[coin][f"{var}_{h}s"] = {"gem_bp": m, "t": t, "n": n}
            print(f"   {var:13s} " + " | ".join(parts))
        p60 = report[coin]["pessimistisch_60s"]
        if p60["n"] >= 100 and p60["gem_bp"] > 0 and p60["t"] > 2:
            verdict = "MOGELIJK VOORDEEL: pessimistisch na 60s positief en significant"
        elif p60["n"] < 100:
            verdict = "te weinig uitvoeringen voor een oordeel"
        else:
            verdict = "geen voordeel: na adverse selectie en fee blijft er niets over"
        report[coin]["oordeel"] = verdict
        print(f"   -> {verdict}\n")
    (root / "resultaat.json").write_text(json.dumps(report, indent=1, default=float))
    print(f"Resultaat bewaard in {root / 'resultaat.json'}")


if __name__ == "__main__":
    main()
