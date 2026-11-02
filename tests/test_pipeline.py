"""Controles: (1) geen look-ahead in features, (2) model vindt een echt patroon,
# Draaien: python tests/make_fake_data.py data && python tests/test_pipeline.py  (overschrijft data/ met nepdata!)
(3) bevroren voorspellingen kunnen niet wijzigen, (4) papieren portefeuille rekent juist."""
import json, sys, tempfile, shutil
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
from common import FEATURES, build_features

prices = common.load_prices()

# 1. look-ahead: features van dag t mogen niet veranderen als je de toekomst weghaalt
full = build_features(prices)
for cut in (1500, 3000, len(prices) - 5):
    part = build_features(prices.iloc[:cut])
    a = full.iloc[:cut][FEATURES].reset_index(drop=True)
    b = part[FEATURES].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)
print("1. geen look-ahead in features: OK")

# 2. plant een echt patroon (momentum) en kijk of het gevonden wordt
rng = np.random.default_rng(7)
n = len(prices); r = np.zeros(n); e = rng.normal(0, 0.03, n)
for i in range(1, n): r[i] = 0.25 * r[i-1] + e[i]
pat = prices.copy(); pat["close"] = 450 * np.exp(np.cumsum(r))
import backtest
pred = backtest.walk_forward(build_features(pat), test_end=common.VAULT_START)
h = backtest.hit_stats(pred)
assert h["hitrate"] > 0.55, h
print(f"2. patroon gevonden: hitrate {h['hitrate']:.3f} (p={h['p_value_vs_always_up']:.2g}): OK")

# 3. bevroren log
import predict
tmp = Path(tempfile.mkdtemp()); predict.PRED = tmp / "p.json"
e1 = predict.update_predictions(prices.iloc[:-2])
e2 = predict.update_predictions(prices.iloc[:-1])
log = json.loads(predict.PRED.read_text())
assert len(log) == 2 and log[0]["outcome"] in ("up", "down") and log[1]["outcome"] is None
again = predict.update_predictions(prices.iloc[:-1])           # zelfde dag: geen duplicaat
assert len(json.loads(predict.PRED.read_text())) == 2
print("3. append-only log + geen duplicaten: OK")
shutil.rmtree(tmp)

# 4. papieren portefeuille met nep-orderboek
tmp = Path(tempfile.mkdtemp()); predict.PAPER = tmp / "paper.json"
state = {"mid": 100_000.0}
def fake_hl(payload):
    if payload["type"] == "l2Book":
        m = state["mid"]
        return {"levels": [[{"px": str(m - 1), "sz": "50"}], [{"px": str(m + 1), "sz": "50"}]]}
    return [{"fundingRate": "0.0000125"}] * 24          # 0,03% per dag
predict.hl = fake_hl
st = predict.update_paper({"target_date": "2026-01-01", "signal": "up"})
eq0 = st["equity"]; assert 999.4 < eq0 < 1000, eq0                    # fee + halve spread
state["mid"] = 110_000.0
st = predict.update_paper({"target_date": "2026-01-02", "signal": "up"})
assert st["history"][-1]["fee"] == 0                                 # geen wissel = geen kosten
exp = eq0 + eq0 / 100_000 * 10_000 - (eq0 / 100_000) * 110_000 * 0.0003
assert abs(st["equity"] - exp) < 0.5, (st["equity"], exp)
st = predict.update_paper({"target_date": "2026-01-03", "signal": "down"})
assert st["position"] == -1 and st["history"][-1]["fee"] > 0
print(f"4. papieren portefeuille: {st['equity']:.2f} na +10% en een wissel naar short: OK")
shutil.rmtree(tmp)

# 5. te late voorspelling wordt gemarkeerd en krijgt geen papieren trade; ander startkapitaal = nieuwe run
tmp = Path(tempfile.mkdtemp()); predict.PRED = tmp / "p.json"; predict.PAPER = tmp / "paper.json"
old = predict.update_predictions(prices.iloc[:-1])             # doeldag = gisteren -> >24u te laat
assert old["late"] is True and old["delay_h"] > 24, old
now_e = predict.update_predictions(prices)                     # doeldag = vandaag
assert now_e["delay_h"] >= 0
st = predict.update_paper(old)
assert st["history"] == [] and st["position"] == 0, "te late voorspelling mag niet traden"
(tmp / "paper.json").write_text(json.dumps({**predict.fresh_paper(), "start_capital": 10000.0, "start_date": "2026-10-29"}))
state["mid"] = 100_000.0
st = predict.update_paper({"target_date": "2026-11-01", "signal": "up", "late": False})
assert st["start_capital"] == 1000.0 and (tmp / "paper_archive_2026-10-29.json").exists()
print("5. te laat gemarkeerd, geen trade; oude run gearchiveerd bij nieuw startkapitaal: OK")
shutil.rmtree(tmp)

# 6. uitdager sterk60: long bij p>=0.60, cash eronder; eigen bestand, kampioen ongemoeid
tmp = Path(tempfile.mkdtemp()); cpath = tmp / "paper_sterk60.json"
rule = predict.CHALLENGERS["sterk60"]["position"]
assert rule(0.60) == 1.0 and rule(0.5999) == 0.0
state["mid"] = 100_000.0
st = predict.update_paper({"target_date": "2026-11-01", "signal": "up", "late": False}, rule(0.55), cpath)
assert st["position"] == 0 and st["history"][-1]["fee"] == 0 and st["equity"] == 1000.0      # cash: geen kosten
st = predict.update_paper({"target_date": "2026-11-02", "signal": "up", "late": False}, rule(0.65), cpath)
assert st["position"] == 1 and st["history"][-1]["fee"] > 0
state["mid"] = 105_000.0
st = predict.update_paper({"target_date": "2026-11-03", "signal": "up", "late": False}, rule(0.52), cpath)
assert st["position"] == 0 and 1040 < st["equity"] < 1050, st["equity"]                    # +5% min kosten/funding
print(f"6. uitdager sterk60: cash -> long -> cash, eindwaarde {st['equity']:.2f}: OK")
shutil.rmtree(tmp)

# 7. C1-signalen: stijgende reeks = 8/8 aan, dalende = 0/8; spot zonder funding met spot-fee
up = pd.DataFrame({"close": np.linspace(100, 300, 400)}); dn = pd.DataFrame({"close": np.linspace(300, 100, 400)})
assert predict.c1_signals(up) == 8 and predict.c1_signals(dn) == 0
# zelfde definitie als het onderzoek (research/spoor_c/f6.py) op de nepdata
c = prices["close"]
sigs = [c > c.rolling(n).mean() for n in (20, 50, 100, 200)] + [c / c.shift(L) > 1 for L in (14, 30, 60, 90)]
assert predict.c1_signals(prices) == int(sum(s.iloc[-1] for s in sigs))
tmp = Path(tempfile.mkdtemp()); p1 = tmp / "paper_c1.json"; state["mid"] = 100_000.0
st = predict.update_paper({"target_date": "2026-11-01", "signal": "down", "late": False}, 1.0, p1, fee_rate=predict.SPOT_FEE, perp=False)
assert abs(st["history"][-1]["fee"] - 0.70) < 0.01, st["history"][-1]["fee"]               # 0,07% van ~1000
state["mid"] = 110_000.0
st = predict.update_paper({"target_date": "2026-11-02", "signal": "down", "late": False}, 1.0, p1, fee_rate=predict.SPOT_FEE, perp=False)
assert st["history"][-1]["funding"] == 0 and 1097 < st["equity"] < 1100, st["equity"]
print(f"7. C1: signalen kloppen met het onderzoek; spot zonder funding, eindwaarde {st['equity']:.2f}: OK")
shutil.rmtree(tmp)

# 8. C2 carry: koers +10% verandert niets, funding wordt ontvangen, herbalancering bij grote stijging
tmp = Path(tempfile.mkdtemp()); p2 = tmp / "carry.json"; state["mid"] = 100_000.0
st = predict.update_carry("2026-11-01", p2); e0 = st["equity"]
assert 998.5 < e0 < 1000 and abs(st["units"] * 100_000 - st["collateral"]) < 1e-6           # 50/50
state["mid"] = 110_000.0
st = predict.update_carry("2026-11-02", p2)
exp = e0 + st["units"] * 110_000 * 0.0000125 * 24                                           # 24 uur funding ontvangen
assert abs(st["equity"] - exp) < 0.01 and not st["history"][-1]["rebalanced"], (st["equity"], exp)
state["mid"] = 200_000.0                                                                      # +100%: short-onderpand op
st = predict.update_carry("2026-11-03", p2)
assert st["history"][-1]["rebalanced"] and abs(st["units"] * 200_000 - st["collateral"]) < 1e-6
print(f"8. C2 carry: koersneutraal, funding ontvangen, herbalanceert bij +100%; vermogen {st['equity']:.2f}: OK")
shutil.rmtree(tmp)

# 9. C1b+HLP: cash groeit met de echte HLP-winstreeks, 4 dagen blokkering stelt instap uit
import datetime as _dt
tmp = Path(tempfile.mkdtemp()); p3 = tmp / "c1b_hlp.json"; state["mid"] = 100_000.0
clock = {"ms": 1_800_000_000_000}
predict.now_utc = lambda: _dt.datetime.fromtimestamp(clock["ms"] / 1000, _dt.timezone.utc)
DAY = 86_400_000
def fake_hl2(payload):
    if payload["type"] == "vaultDetails":       # HLP: vermogen 100M, winst 10.000 USD per dag = 0,01%/dag
        t0 = 1_800_000_000_000 - 40 * DAY
        pts = [(t0 + i * DAY // 4, 100e6, 10_000 * i / 4) for i in range(4 * 60)]
        win = {"accountValueHistory": [[t, str(a)] for t, a, _ in pts], "pnlHistory": [[t, str(p)] for t, _, p in pts], "vlm": "0"}
        return {"portfolio": [["day", {**win, "pnlHistory": win["pnlHistory"][-4:], "accountValueHistory": win["accountValueHistory"][-4:]}], ["allTime", win]]}
    return fake_hl(payload)
predict.hl = fake_hl2
e = lambda d: {"target_date": d, "signal": "up", "late": False}
st = predict.update_c1b_hlp(e("2026-11-01"), 2, p3)                 # cash -> naar HLP
assert st["position"] == 0 and st["hlp_since_ms"] == clock["ms"] and st["equity"] == 1000.0
clock["ms"] += DAY; st = predict.update_c1b_hlp(e("2026-11-02"), 7, p3)   # koopsignaal op dag 1: nog vast
assert st["position"] == 0 and "vast" in st["history"][-1]["note"], st["history"][-1]
assert abs(st["equity"] - 1000 * 1.0001) < 1e-6, st["equity"]       # 1 dag HLP-opbrengst
clock["ms"] += 4 * DAY; st = predict.update_c1b_hlp(e("2026-11-03"), 7, p3)   # na de blokkering: instappen
assert st["position"] == 1 and st["hlp_since_ms"] is None
assert abs(st["history"][-1]["hlp_gain"] - 1000.1 * 0.0004) < 0.01   # 4 dagen opbrengst vóór de instap
clock["ms"] += DAY; st = predict.update_c1b_hlp(e("2026-11-04"), 3, p3)       # verkopen -> terug naar HLP
assert st["position"] == 0 and st["hlp_since_ms"] == clock["ms"]
print(f"9. C1b+HLP: HLP-opbrengst, 4 dagen blokkering, instap en terugstorting kloppen; vermogen {st['equity']:.2f}: OK")
shutil.rmtree(tmp)

# 10. uitdagerslog (v0.7): backfill, één regel per dag per uitdager, tweede run schrijft niets, uitkomst achteraf
tmp = Path(tempfile.mkdtemp())
predict.DATA = tmp; predict.PRED = tmp / "predictions.json"; predict.CHAL = tmp / "challengers.json"; predict.PAPER = tmp / "paper.json"
predict.now_utc = lambda: _dt.datetime.now(_dt.timezone.utc)
(tmp / "paper_c1b.json").write_text(json.dumps({"history": [{"target_date": "2026-10-31", "time": "2026-10-31T06:10:00+00:00", "position": 0.0, "signals_on": 3}]}))
e1 = dict(predict.update_predictions(prices.iloc[:-1]))               # doeldag = gisteren (te laat)
res = {"paper_c1b.json": ({"signals_on": 7}, 1.0), "paper_c1.json": ({"signals_on": 7}, 1.0)}
log = predict.log_challengers(e1, res, prices.iloc[:-1])
bf = [r for r in log if r["backfilled"]]
assert len(bf) == 1 and bf[0]["challenger_id"] == "C1b-trend6of8-v1" and bf[0]["delay_h"] == 6.17
new = [r for r in log if not r["backfilled"]]
assert len(new) == 2 and all(r["late"] for r in new) and [r["primary"] for r in new if r["challenger_id"] == "C1b-trend6of8-v1"] == [True]
n1 = len(log); raw1 = (tmp / "challengers.json").read_text()
log2 = predict.log_challengers(e1, {"paper_c1b.json": ({"signals_on": 2}, 0.0)}, prices.iloc[:-1])   # tweede run zelfde dag
assert len(log2) == n1 and (tmp / "challengers.json").read_text() == raw1, "tweede run mag niets schrijven"
log3 = predict.log_challengers(e1, {}, prices)                        # slot van de doeldag nu bekend
r = [x for x in log3 if x["target_date"] == e1["target_date"] and x["challenger_id"] == "C1-trend5of8-v1"][0]
c = prices.set_index("date")["close"]; td = pd.Timestamp(e1["target_date"])
assert abs(r["btc_ret"] - (c[td] / c[td - pd.Timedelta(days=1)] - 1)) < 1e-6 and r["strat_ret"] == r["btc_ret"]
print(f"10. uitdagerslog: backfill, primaire markering, geen dubbele regels, uitkomst achteraf: OK")
shutil.rmtree(tmp)

# 11. positionering: één momentopname per UTC-dag
import fetch_data
tmp = Path(tempfile.mkdtemp()); fetch_data.DATA = tmp
class _R:
    def __init__(s, d): s.d = d
    def json(s): return s.d
fetch_data.requests.post = lambda url, json, timeout: _R([{"universe": [{"name": "BTC"}]}, [{"markPx": "1", "oraclePx": "1", "openInterest": "1", "funding": "0", "dayNtlVlm": "1"}]])
fetch_data.log_positioning({}); s2 = {}; fetch_data.log_positioning(s2)
assert len((tmp / "positioning.csv").read_text().strip().splitlines()) == 2 and s2["positioning"] == "vandaag al gelogd"
print("11. positionering: maximaal één regel per dag: OK")
shutil.rmtree(tmp)
