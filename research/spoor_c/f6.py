import sys; sys.path.insert(0,'.')
from engine import *
c = PX["close"]; lr = np.log(c).diff(); vol30 = lr.rolling(30).std()*np.sqrt(365)
def thresh(w, th):
    """herbalanceer enkel als het doelgewicht meer dan th afwijkt (minder trades)"""
    out, cur = [], 0.0
    for v in w.fillna(0).values:
        if abs(v - cur) > th or (v == 0 and cur != 0) or (v > 0 and cur == 0): cur = v
        out.append(cur)
    return pd.Series(out, index=w.index)
sigs = [c > c.rolling(n).mean() for n in (20, 50, 100, 200)] + [c / c.shift(L) > 1 for L in (14, 30, 60, 90)]
ens = sum(s.astype(float) for s in sigs) / len(sigs)                 # 0, 1/8, ... 1
rows = []
def rec(name, sig, venue="spot"):
    r, h = run(sig, venue); s = full(r, h)
    rows.append([name, venue, s["all"]["cagr"], s["all"]["sharpe"], s["all"]["maxdd"], s["h1"]["sharpe"], s["h2"]["sharpe"], s["h1"]["maxdd"], s["h2"]["maxdd"], s["all"]["exposure"], s["all"]["trades_per_yr"]])
    return r, h
rec("kopen-en-vasthouden", BH_SIGNAL)
rec("SMA50 (beste enkelvoudige ter vergelijking)", (c > c.rolling(50).mean()).astype(float))
rec("ensemble 8 trendsignalen (gewicht = aandeel 'aan')", thresh(ens, 0.2))
rec("ensemble, enkel long als ≥ 5/8 aan", (ens >= 5/8).astype(float))
for tv in (0.5, 0.7):
    rec(f"ensemble × vol-doel {int(tv*100)}%, drempel 20%", thresh(ens * (tv/vol30).clip(upper=1), 0.2))
rec("ensemble op Hyperliquid perps (echte/aangenomen funding)", thresh(ens, 0.2), "perp")
df = pd.DataFrame(rows, columns=["strategie","venue","cagr","sharpe","maxdd","h1_sh","h2_sh","h1_dd","h2_dd","blootst","trades/j"])
for col in ("cagr","maxdd","h1_dd","h2_dd","blootst"): df[col] = (df[col]*100).round(0)
for col in ("sharpe","h1_sh","h2_sh","trades/j"): df[col] = df[col].round(2)
pd.set_option("display.width", 250); print(df.to_string(index=False))
# carry in de cash-periodes (enkel 2023-05+): wanneer ensemble = 0, verdien funding (half kapitaal, 1x short)
r_e, h_e = run(thresh(ens * (0.7/vol30).clip(upper=1), 0.2))
f = FUND; m = r_e.index >= f.index.min()
base = r_e[m]; idle = (1 - h_e[m].abs())                              # ongebruikt kapitaal
carry = 0.5 * idle * f.reindex(base.index).fillna(0)
for lab, rr in (("ensemble × vol70 (2023-05+)", base), ("+ carry op ongebruikt kapitaal", base + carry)):
    s = stats(rr); print(f"{lab}: CAGR {s['cagr']*100:.0f}%  Sharpe {s['sharpe']:.2f}  maxDD {s['maxdd']*100:.0f}%")
bh, _ = run(BH_SIGNAL); s = stats(bh[bh.index >= f.index.min()]); print(f"K&V zelfde periode: CAGR {s['cagr']*100:.0f}%  Sharpe {s['sharpe']:.2f}  maxDD {s['maxdd']*100:.0f}%")
