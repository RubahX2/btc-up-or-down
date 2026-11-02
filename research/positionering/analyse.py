"""Analyse volgens PLAN.md. Draaien vanuit deze map: python3 analyse.py  (pandas, scipy nodig)."""
import math, os
import numpy as np, pandas as pd
from scipy.stats import mannwhitneyu, spearmanr
HERE = os.path.dirname(os.path.abspath(__file__))
px = pd.read_csv(os.path.join(HERE, '..', '..', 'data', 'btc_daily.csv'), parse_dates=['date']).set_index('date')
px.index = px.index.as_unit('ns'); c = px.close; ret = c.pct_change().fillna(0); END = pd.Timestamp('2026-10-29')
def daily(name, col, how):
    d = pd.read_csv(os.path.join(HERE, name)); d['date'] = pd.to_datetime(d.tijd_ms, unit='ms').dt.normalize()
    out = getattr(d.groupby('date')[col], how)(); out.index = pd.DatetimeIndex(out.index).as_unit('ns'); return out
fund = daily('binance_funding.csv', 'funding', 'sum')                 # per dag (3 x 8u)
oi = daily('bybit_oi_dag.csv', 'oi_btc', 'last')
f7 = fund.rolling(7).mean()
def past_pct(s, minp=180):          # percentiel t.o.v. enkel het verleden (geen look-ahead)
    v = s.values; out = np.full(len(v), np.nan)
    for i in range(minp, len(v)):
        h = v[:i+1]; h = h[~np.isnan(h)]
        if len(h) >= minp: out[i] = (h < v[i]).mean() * 100
    return pd.Series(out, index=s.index)
FUND = past_pct(f7).reindex(c.index)
OI30 = (oi / oi.shift(30) - 1).reindex(c.index)
start = max(FUND.first_valid_index(), OI30.first_valid_index())
print(f"Funding vanaf {fund.index.min().date()}, open interest vanaf {oi.index.min().date()}; gezamenlijke test vanaf {start.date()} t/m {END.date()}")
P1, P2 = (start, pd.Timestamp('2022-12-31')), (pd.Timestamp('2023-01-01'), END)
# Toets 1: grootste daling in de 30 dagen erna
fwd_dd = pd.Series([(c.iloc[i+1:i+31].min() / c.iloc[i] - 1) if i + 30 < len(c) else np.nan for i in range(len(c))], index=c.index)
fwd_r = c.shift(-30) / c - 1
print("\nTOETS 1: kenmerk vs grootste daling (en rendement) in de 30 dagen erna")
for nm, f in (("FUND-percentiel", FUND), ("OI30", OI30)):
    m = f.notna() & fwd_dd.notna() & (f.index >= start)
    rho, p = spearmanr(f[m], fwd_dd[m]); rho2, p2 = spearmanr(f[m], fwd_r[m])
    print(f"  {nm:16s} rang-correlatie met daling {rho:+.3f} (p={p:.3f}), met rendement {rho2:+.3f} (p={p2:.3f})  n={m.sum()}")
    q = pd.qcut(f[m], 5, labels=False)
    for k in range(5):
        mm = q == k
        print(f"     kwintiel {k+1}: gem. kenmerk {f[m][mm].mean():8.2f} | gem. grootste daling 30d {fwd_dd[m][mm].mean()*100:6.1f}% | gem. rendement 30d {fwd_r[m][mm].mean()*100:+6.1f}%")
    print("     (let op: overlappende 30-dagenvensters, dus de p-waarden zijn te optimistisch)")
# C1b
sigs = [c > c.rolling(n).mean() for n in (20,50,100,200)] + [c/c.shift(L) > 1 for L in (14,30,60,90)]
cnt = sum(s.astype(int) for s in sigs)
FEE = 0.0007
def run(no_entry=None, force_exit=None, a=None, b=None):
    days = c.index[(c.index >= a) & (c.index <= b)]
    pos, eq, armed, out, trades = 0, 1.0, True, [], []
    for i, d in enumerate(days):
        if i and pos: eq *= 1 + ret[d]
        want = cnt[d] >= 6
        if not want: armed = True
        if pos:
            stop = force_exit is not None and bool(force_exit.get(d, False))
            if not want or stop:
                pos, eq = 0, eq * (1 - FEE); trades[-1].append(c[d])
                if stop and want: armed = False
        elif want and armed and not (no_entry is not None and bool(no_entry.get(d, False))):
            pos, eq = 1, eq * (1 - FEE); trades.append([d, c[d]])
        out.append((d, eq))
    e = pd.Series(dict(out)); r = e.pct_change().dropna()
    return (e.iloc[-1] ** (365 / len(e)) - 1, r.mean() / r.std() * math.sqrt(365), (e / e.cummax() - 1).min()), trades
print("\nTOETS 2: C1b-trades, kenmerk bij instap (winnaars vs verliezers)")
_, tr = run(a=start, b=END)
T = pd.DataFrame([t for t in tr if len(t) == 3], columns=['in', 'pin', 'puit']); T['win'] = T.puit / T.pin - 1 - 2*FEE > 0
for nm, f in (("FUND-percentiel", FUND), ("OI30", OI30)):
    w, l = f.reindex(T['in'][T.win]).dropna(), f.reindex(T['in'][~T.win]).dropna()
    print(f"  {nm:16s} winnaars mediaan {w.median():7.2f} (n={len(w)}) | verliezers mediaan {l.median():7.2f} (n={len(l)}) | p={mannwhitneyu(w, l).pvalue:.3f}")
print("\nTOETS 3: regels op C1b (jaar%, Sharpe, max. daling)")
fmt = lambda s: f"{s[0]*100:6.0f}% {s[1]:5.2f} {s[2]*100:5.0f}%"
base = [run(a=a, b=b)[0] for a, b in (P1, P2)]
print(f"  {'C1b':42s} P1 {fmt(base[0])}   P2 {fmt(base[1])}")
rules = {}
for p in (80, 90, 95): rules[f"R1 geen instap als FUND > p{p}"] = dict(no_entry=(FUND > p).to_dict())
for p in (80, 90, 95): rules[f"R2 uit als FUND > p{p}"] = dict(force_exit=(FUND > p).to_dict())
for q in (0.2, 0.3, 0.5): rules[f"R3 geen instap als OI30 > {q:.0%}"] = dict(no_entry=(OI30 > q).to_dict())
for q in (0.2, 0.3): rules[f"R4 uit als FUND > p80 en OI30 > {q:.0%}"] = dict(force_exit=((FUND > 80) & (OI30 > q)).to_dict())
res = {}
for k, kw in rules.items():
    s = [run(a=a, b=b, **kw)[0] for a, b in (P1, P2)]; res[k] = s
    print(f"  {k:42s} P1 {fmt(s[0])}   P2 {fmt(s[1])}")
print("\nGEKOZEN OP PERIODE 1, GECONTROLEERD OP PERIODE 2:")
for fam in ("R1", "R2", "R3", "R4"):
    ks = [k for k in res if k.startswith(fam)]; best = max(ks, key=lambda k: res[k][0][1])
    s1, s2 = res[best]
    ok = s1[1] >= base[0][1] + 0.10 and s1[2] >= base[0][2] and s2[1] >= base[1][1] + 0.10 and s2[2] >= base[1][2]
    print(f"  {best:42s} P2 Sharpe {s2[1]:.2f} vs {base[1][1]:.2f}, daling {s2[2]*100:.0f}% vs {base[1][2]*100:.0f}%  -> {'SLAAGT' if ok else 'slaagt niet'}")
