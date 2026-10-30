import sys; sys.path.insert(0, '.')
from engine import *
import itertools, json
c = PX["close"]; lr = np.log(c).diff()
vol30 = lr.rolling(30).std() * np.sqrt(365)
RES = []

def rec(fam, name, sig, venue="spot"):
    r, h = run(sig, venue); s = full(r, h)
    RES.append({"family": fam, "name": name, "venue": venue, **{f"{k}_{m}": s[k].get(m) for k in ("all", "h1", "h2") for m in ("cagr", "sharpe", "maxdd")},
                "exposure": s["all"]["exposure"], "tpy": s["all"]["trades_per_yr"]})
    return r

# referentie
rec("REF", "kopen-en-vasthouden", BH_SIGNAL)
# F1 trend
for n in (10, 20, 30, 50, 75, 100, 150, 200):
    rec("F1-SMA", f"slot>SMA{n}", (c > c.rolling(n).mean()).astype(float))
for f, s_ in ((5, 20), (10, 30), (10, 50), (20, 50), (20, 100), (50, 200)):
    rec("F1-EMAx", f"EMA{f}>EMA{s_}", (c.ewm(span=f).mean() > c.ewm(span=s_).mean()).astype(float))
for L in (7, 14, 30, 60, 90, 120, 180, 365):
    rec("F1-TSMOM", f"rendement{L}d>0", (c / c.shift(L) > 1).astype(float))
for ent, ex in ((20, 10), (30, 15), (55, 20), (100, 50)):
    hi = c.rolling(ent).max(); lo = c.rolling(ex).min()
    st = pd.Series(np.nan, index=c.index); st[c >= hi] = 1; st[c <= lo] = 0
    rec("F1-Donchian", f"uitbraak{ent}/{ex}", st.ffill().fillna(0))
# F2 vol-sturing
for tv in (0.4, 0.6, 0.8):
    w = (tv / vol30).clip(upper=1).fillna(0)
    rec("F2-vol", f"BH vol-doel {int(tv*100)}%", w)
    for n in (50, 100, 150):
        rec("F2-vol", f"SMA{n} + vol-doel {int(tv*100)}%", w * (c > c.rolling(n).mean()))
# F3 mean reversion
z = lr / lr.rolling(60).std()
for k in (1.5, 2.0, 2.5):
    for hold in (1, 3, 5, 10):
        ev = (z < -k).astype(float)
        rec("F3-MR", f"na daling <-{k}σ, {hold}d houden", ev.rolling(hold, min_periods=1).max())
delta = c.diff(); up = delta.clip(lower=0); dn = -delta.clip(upper=0)
for n, th in ((2, 10), (2, 20), (14, 30)):
    rsi = 100 - 100 / (1 + up.ewm(alpha=1/n).mean() / dn.ewm(alpha=1/n).mean())
    for hold in (1, 3, 5):
        rec("F3-RSI", f"RSI{n}<{th}, {hold}d", (rsi < th).astype(float).rolling(hold, min_periods=1).max())
# F4 seizoenen: positie voor dag t+1 wordt bepaald op slot t => kijk naar weekdag van t+1
nxt = c.index + pd.Timedelta(days=1)
for wd, nm in enumerate(["ma", "di", "wo", "do", "vr", "za", "zo"]):
    rec("F4-weekdag", f"enkel op {nm}", pd.Series((nxt.dayofweek == wd).astype(float), index=c.index))
rec("F4-weekdag", "enkel weekdagen", pd.Series((nxt.dayofweek < 5).astype(float), index=c.index))
rec("F4-weekdag", "enkel weekend", pd.Series((nxt.dayofweek >= 5).astype(float), index=c.index))
rec("F4-maandwissel", "laatste 3 + eerste 3 dagen", pd.Series(((nxt.day <= 3) | (nxt.day >= 28)).astype(float), index=c.index))
for m in range(1, 13):
    rec("F4-maand", f"enkel maand {m}", pd.Series((nxt.month == m).astype(float), index=c.index))
# F1 op perps long/short (trend aan beide kanten)
for n in (50, 100, 200):
    rec("F1-SMA-LS", f"SMA{n} long/short", np.where(c > c.rolling(n).mean(), 1.0, -1.0) * pd.Series(1, index=c.index), "perp")

df = pd.DataFrame(RES)
df.to_csv("results_f1_f4.csv", index=False)
print("aantal geteste varianten:", len(df))
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
show = df[["family","name","venue","all_cagr","all_sharpe","all_maxdd","h1_sharpe","h2_sharpe","exposure","tpy"]].copy()
for col in ("all_cagr","all_maxdd","exposure"): show[col] = (show[col]*100).round(0)
for col in ("all_sharpe","h1_sharpe","h2_sharpe","tpy"): show[col] = show[col].round(2)
print(show.sort_values("all_sharpe", ascending=False).to_string(index=False))
