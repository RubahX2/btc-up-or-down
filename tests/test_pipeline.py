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
