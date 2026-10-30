"""Historische meting C1b + HLP (30-10-2026). Draaien vanuit deze map: python3 c1b_hlp_hist.py
HLP-historiek: hlp_raw_2026-10-30.json = Hyperliquid vaultDetails 'allTime' [tijd, winst, vermogen, ok], ±elke 2 weken.
Rendement per interval = winst / gemiddeld vermogen ('gem', klopt met Trading Strategy: 7,1% vs 7,0% laatste 12 mnd)
of winst / hoogste vermogen ('max', streng). Gelijk gespreid over de dagen van het interval."""
import json, os
import pandas as pd, numpy as np, math
HERE = os.path.dirname(os.path.abspath(__file__))
raw = json.load(open(os.path.join(HERE, 'hlp_raw_2026-10-30.json')))
_df = pd.DataFrame(raw, columns=['t','pnl','av','ok']); _df['date'] = pd.to_datetime(_df.t, unit='s')
def hlp_series(method):
    daily = {}
    for a, b in zip(_df.iloc[2:-1].itertuples(), _df.iloc[3:].itertuples()):
        base = (a.av + b.av) / 2 if method == 'gem' else max(a.av, b.av)
        r = (b.pnl - a.pnl) / base; days = (b.t - a.t) / 86400
        for d in pd.date_range(a.date.normalize(), b.date.normalize() - pd.Timedelta(days=1)):
            daily[d] = (1 + r) ** (1 / days) - 1
    return daily
px = pd.read_csv(os.path.join(HERE, '..', '..', 'data', 'btc_daily.csv'), parse_dates=['date']).set_index('date'); c = px.close; ret = c.pct_change().fillna(0)
sigs = [c > c.rolling(n).mean() for n in (20,50,100,200)] + [c/c.shift(L) > 1 for L in (14,30,60,90)]
want = (sum(s.astype(float) for s in sigs) >= 6).astype(float)          # besluit op slot t, geldt voor dag t+1
FEE, LOCK = 0.0007, 4
def sim(hlp, lock=True):
    days = c.index[(c.index >= '2023-05-20') & (c.index <= '2026-10-29')]
    eq, pos, since, out, delayed = 1.0, 0.0, None, [], 0
    for d in days:
        # dag d: resultaat van de positie die op het slot van d-1 gekozen werd
        if pos == 1: eq *= 1 + ret[d]
        else: eq *= 1 + (hlp.get(d, 0.0) if hlp is not None else 0.0)
        # slot van d: nieuwe beslissing
        w = want[d]
        if w == 1 and pos == 0 and lock and hlp is not None and since is not None and (d - since).days < LOCK:
            w = 0; delayed += 1
        if w != pos:
            eq *= 1 - FEE
            if w == 0: since = d          # verkocht: cash gaat naar HLP, 4 dagen vast
            pos = w
        if pos == 0 and since is None: since = d
        out.append((d, eq, pos))
    s = pd.DataFrame(out, columns=['d','eq','pos']).set_index('d')
    return s, delayed
def stats(eq):
    r = eq.pct_change().fillna(eq.iloc[0] - 1); n = len(eq)
    return f"{(eq.iloc[-1]/1 if True else 0) and ((eq.iloc[-1])**(365/n)-1)*100:6.1f}%/j  Sharpe {r.mean()/r.std()*math.sqrt(365):4.2f}  max.daling {((eq/eq.cummax())-1).min()*100:5.1f}%"
gem = hlp_series('gem')
mx = hlp_series('max')
const = {d: (1.043)**(1/365) - 1 for d in c.index}
bh = (1 + ret[(c.index >= '2023-05-20') & (c.index <= '2026-10-29')]).cumprod()
runs = {"Kopen en vasthouden": (bh.to_frame('eq'), 0), "C1b (cash zonder rente)": sim(None),
        "C1b + HLP (echte historiek)": sim(gem), "C1b + HLP (strenge berekening)": sim(mx),
        "C1b + vaste 4,3% (HLP-niveau van nu)": sim(const), "C1b + HLP zonder blokkering": sim(gem, lock=False)}
for lab, (a, b) in (("HELE PERIODE mei 2023 - okt 2026", ('2023-05-20','2026-10-29')), ("mei 2023 - okt 2025", ('2023-05-20','2025-10-31')), ("kluisjaar nov 2025 - okt 2026", ('2025-11-01','2026-10-29'))):
    print(f"\n{lab}")
    for k, (s, delayed) in runs.items():
        e = s['eq']; e = e[(e.index >= a) & (e.index <= b)]; e = e / e.iloc[0] * (1 + 0)
        cash = (1 - s['pos'][(s.index >= a) & (s.index <= b)].mean())*100 if 'pos' in s else 0
        print(f"  {k:38s} {stats(e)}   in cash {cash:3.0f}%" + (f"   uitgestelde instapdagen {delayed}" if delayed else ""))
