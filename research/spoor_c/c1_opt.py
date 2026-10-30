import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, math
import os; D=os.path.join(os.path.dirname(__file__), '..', '..', 'data') + '/'
px = pd.read_csv(D+'btc_daily.csv', parse_dates=['date']).set_index('date'); c = px['close']; ret = c.pct_change().fillna(0)
VS, VE = pd.Timestamp('2025-11-01'), pd.Timestamp('2026-10-29')
sigs = [c > c.rolling(n).mean() for n in (20,50,100,200)] + [c/c.shift(L) > 1 for L in (14,30,60,90)]
cnt = sum(s.astype(float) for s in sigs)
lr = np.log(c).diff(); vol30 = lr.rolling(30).std()*np.sqrt(365)
def ev(pos, fee=0.0009, idle_yield=0.0, label=''):
    held = pos.shift(1).fillna(0); turn = (held-held.shift(1).fillna(0)).abs()
    r = held*ret - turn*fee + (1-held)*idle_yield/365
    out = []
    for a,b in ((pd.Timestamp('2016-01-01'), pd.Timestamp('2020-12-31')), (pd.Timestamp('2021-01-01'), pd.Timestamp('2025-10-31')), (VS, VE)):
        x = r[(r.index>=a)&(r.index<=b)]; eq=(1+x).cumprod()
        cagr = eq.iloc[-1]**(365/len(x))-1; sh = x.mean()/x.std()*math.sqrt(365); dd=(eq/eq.cummax()-1).min()
        out += [f"{cagr*100:5.0f}%", f"{sh:5.2f}", f"{dd*100:4.0f}%"]
    tpy = (turn>0)[(turn.index>='2016-01-01')&(turn.index<=VE)].sum()/((VE-pd.Timestamp('2016-01-01')).days/365)
    print(f"{label:46s} " + "  ".join(out) + f"  {tpy:5.1f}")
print(f"{'variant':46s} {'2016-20: cagr sharpe dd':24s} {'2021-25: cagr sharpe dd':24s} {'kluis: cagr sharpe dd':22s} tr/j")
ev(pd.Series(1.0,index=c.index), 0, 0, 'kopen-en-vasthouden')
base = (cnt>=5).astype(float)
ev(base, 0.0009, 0, 'C1 zoals vastgelegd (taker 0,09%)')
ev(base, 0.0007, 0, 'C1 Hyperliquid spot taker 0,07%')
ev(base, 0.0004, 0, 'C1 Hyperliquid spot maker 0,04%')
for k in (4,6): ev((cnt>=k).astype(float), 0.0007, 0, f'drempel {k}/8 (gevoeligheid)')
# bevestiging: wissel pas als het signaal 2 dagen op rij hetzelfde zegt (minder heen-en-weer)
b2 = base.copy(); st=0.0; out=[]
for v,p in zip(base.values, base.shift(1).fillna(0).values):
    if v==p: st=v
    out.append(st)
ev(pd.Series(out,index=c.index), 0.0007, 0, 'wissel pas na 2 dagen bevestiging')
# trapsgewijs: positie = aandeel signalen aan (geen alles-of-niets), herbalans bij >=25% verschil
def thresh(w, th):
    o, cur = [], 0.0
    for v in w.fillna(0).values:
        if abs(v-cur) >= th or (v==0 and cur!=0): cur=v
        o.append(cur)
    return pd.Series(o, index=w.index)
ev(thresh(cnt/8, 0.25), 0.0007, 0, 'trapsgewijs (aandeel aan), drempel 25%')
ev(thresh(base*(0.6/vol30).clip(upper=1), 0.2), 0.0007, 0, 'C1 × volatiliteitsdoel 60%')
for y in (0.04, 0.07): ev(base, 0.0007, y, f'C1 + {int(y*100)}% rente op cash als C1 uit staat')
