import sys; sys.path.insert(0,'.')
from engine import *
c = PX["close"]; rng = np.random.default_rng(42)
res = pd.read_csv("results_f1_f4.csv")
trend = res[res.family.str.startswith("F1") & (res.venue == "spot")]
print(f"trendvarianten (spot): {len(trend)}; Sharpe mediaan {trend.all_sharpe.median():.2f}, min {trend.all_sharpe.min():.2f}; "
      f"beter dan K&V (1,17) in beide helften: {((trend.h1_sharpe>1.488)&(trend.h2_sharpe>0.76)).sum()}/{len(trend)}")
# Toevalstest: willekeurige long/cash-timing met dezelfde blootstelling (58%) en hetzelfde wisseltempo als SMA50 (~18 wissels/jaar)
sig = (c > c.rolling(50).mean()).astype(float)
r0, h0 = run(sig); s0 = stats(r0, h0)
held = h0.values; runs_on, runs_off, cur, ln = [], [], held[0], 0
for v in held:
    if v == cur: ln += 1
    else: (runs_on if cur else runs_off).append(ln); cur, ln = v, 1
N = 3000; sh = np.empty(N); dd = np.empty(N); idx = PX.index
for i in range(N):
    out, state = [], rng.random() < 0.58
    while len(out) < len(idx):
        out += [float(state)] * int(rng.choice(runs_on if state else runs_off)); state = not state
    r, h = run(pd.Series(out[:len(idx)], index=idx)); s = stats(r, h); sh[i], dd[i] = s["sharpe"], s["maxdd"]
print(f"SMA50: Sharpe {s0['sharpe']:.2f}, maxDD {s0['maxdd']*100:.0f}% | willekeurige timing (n={N}): Sharpe mediaan {np.median(sh):.2f}, 95e pct {np.percentile(sh,95):.2f}")
print(f"  aandeel willekeurig >= SMA50-Sharpe: {(sh >= s0['sharpe']).mean()*100:.2f}%  | >= mediaan trendfamilie ({trend.all_sharpe.median():.2f}): {(sh >= trend.all_sharpe.median()).mean()*100:.2f}%")
print(f"  aandeel willekeurig met maxDD beter dan -59%: {(dd > s0['maxdd']).mean()*100:.1f}%")
# Beste-van-85 correctie: kans dat de BESTE van 85 willekeurige strategieën de beste trendvariant (1,61) haalt
best = np.array([sh[rng.choice(N, 85, replace=False)].max() for _ in range(2000)])
print(f"  beste van 85 willekeurige: mediaan {np.median(best):.2f}; kans >= 1,61: {(best >= 1.61).mean()*100:.1f}%")
# Per jaar: waar komt de winst vandaan?
bh, _ = run(BH_SIGNAL)
for y in range(2016, 2026):
    m = r0.index.year == y
    print(f"  {y}: SMA50 {((1+r0[m]).prod()-1)*100:+6.0f}%   K&V {((1+bh[m]).prod()-1)*100:+6.0f}%")
