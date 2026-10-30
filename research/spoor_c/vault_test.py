import sys, json, math, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np, pandas as pd
import backtest as bt
from common import VAULT_START, build_features, load_prices, load_funding, STRONG_HI
VEND = pd.Timestamp("2026-10-29")
prices, funding = load_prices(), load_funding()
prices = prices[prices["date"] <= VEND].reset_index(drop=True)
c = prices.set_index("date")["close"]; ret = c.pct_change()
def st(r):
    eq = (1 + r).cumprod(); sd = r.std()
    return {"rendement": eq.iloc[-1] - 1, "sharpe": r.mean() / sd * math.sqrt(365) if sd > 0 else float("nan"),
            "maxdd": (eq / eq.cummax() - 1).min(), "dagen": len(r)}
out = {}
# A en B: walk-forward, enkel voorspellingen waarvan de DOELdag in de kluis valt
feat = build_features(prices)
pred = bt.walk_forward(feat, test_start=VAULT_START - pd.Timedelta(days=1))
pred = pred[(pred["date"] + pd.Timedelta(days=1) >= VAULT_START) & (pred["date"] + pd.Timedelta(days=1) <= VEND)].reset_index(drop=True)
p = pred["p"]
scen = {"A long/short (perps)": bt.strategy(pred, pd.Series(np.where(p > 0.5, 1.0, -1.0)), funding),
        "B ≥60% long (perps)": bt.strategy(pred, pd.Series(np.where(p >= STRONG_HI, 1.0, 0.0)), funding),
        "altijd long (perps)": bt.strategy(pred, pd.Series(np.ones(len(pred))), funding),
        "kopen-en-vasthouden (spot)": bt.strategy(pred, pd.Series(np.ones(len(pred))), funding, perp=False)}
for k, s in scen.items(): out[k] = st(s["ret"].reset_index(drop=True)) | {"trades": int((s["turnover"] > 0).sum())}
hit = ((p > 0.5) == (pred["y"] == 1)).mean(); up = pred["y"].mean(); n = len(pred)
z = (hit - up) / math.sqrt(up * (1 - up) / n); pval = 0.5 * math.erfc(z / math.sqrt(2))
strong = p >= STRONG_HI
out["A hitrate"] = {"hitrate": hit, "altijd_omhoog": up, "p": pval, "n": n,
                    "B_dagen_long": int(strong.sum()), "B_hitrate_op_die_dagen": float((pred.loc[strong, "y"] == 1).mean()) if strong.any() else None}
# C1: trend-ensemble op spot, signaal op slot t, positie dag t+1
sigs = [c > c.rolling(n).mean() for n in (20, 50, 100, 200)] + [c / c.shift(L) > 1 for L in (14, 30, 60, 90)]
on = (sum(s.astype(float) for s in sigs) >= 5).astype(float)
held = on.shift(1).fillna(0); turn = (held - held.shift(1).fillna(0)).abs()
r1 = held * ret - turn * 0.0009
m = (r1.index >= VAULT_START) & (r1.index <= VEND)
out["C1 trend-ensemble (spot)"] = st(r1[m]) | {"trades": int((turn[m] > 0).sum()), "blootstelling": float(held[m].mean())}
rbh = ret[m]; out["kopen-en-vasthouden (spot, dagreeks)"] = st(rbh)
# C2: carry
f = funding[(funding.index >= VAULT_START) & (funding.index <= VEND)]
r2 = 0.5 * f.copy(); r2.iloc[0] -= 0.5 * (0.0009 + 0.00045); r2.iloc[-1] -= 0.5 * (0.0009 + 0.00045)
monthly = (1 + r2).groupby(r2.index.to_period("M")).prod() - 1
out["C2 carry"] = st(r2) | {"slechtste_maand": float(monthly.min()), "funding_jaarbasis_voor_short": float(f.mean() * 365),
                            "dagen_negatieve_funding": int((f < 0).sum())}
# maand per maand: C1 vs K&V
mm = pd.DataFrame({"C1": (1 + r1[m]).groupby(r1[m].index.to_period("M")).prod() - 1,
                   "K&V": (1 + rbh).groupby(rbh.index.to_period("M")).prod() - 1,
                   "C1 blootstelling": held[m].groupby(held[m].index.to_period("M")).mean(),
                   "C2": monthly})
print(json.dumps(out, indent=1, default=float))
print((mm * 100).round(1).to_string())
json.dump({"protocol": "research/spoor_c/VAULT_PROTOCOL.md", "periode": [str(VAULT_START.date()), str(VEND.date())],
           "resultaten": out, "per_maand": {str(k): v for k, v in (mm.round(4).T.to_dict()).items()}},
          open("vault_result.json", "w"), indent=1, default=float)
