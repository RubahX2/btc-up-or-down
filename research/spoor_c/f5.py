import sys; sys.path.insert(0,'.')
from engine import *
f = FUND.copy(); c = PX["close"]
print("funding-dagen:", len(f), f.index.min().date(), "t/m", f.index.max().date())
ann = f.mean()*365
print(f"gem. funding/dag {f.mean()*100:.4f}%  -> {ann*100:.1f}%/jaar voor wie short perp zit; dagen positief {(f>0).mean()*100:.0f}%")
for y, g in f.groupby(f.index.year): print(f"  {y}: {g.mean()*365*100:5.1f}%/jaar, positief {(g>0).mean()*100:.0f}% van de dagen, min-dag {g.min()*100:.3f}%")
# cash-and-carry: long spot + short perp. Kapitaal: K. Spot = K/2, perp-onderpand = K/2 bij 1x short op K/2.
# Rendement op K = 0.5*funding - kosten. Kosten: openen + sluiten (spot 0,09% + perp 0,045%) eenmalig, op K/2.
for frac, label in ((0.5, "veilig: helft spot, helft onderpand (1x)"), (2/3, "2/3 spot, 1/3 onderpand (2x short)")):
    days = len(f); gross = frac * f.sum(); cost = frac * 2 * (0.0009 + 0.00045)
    print(f"carry {label}: {((1+gross-cost)**(365/days)-1)*100:.1f}%/jaar netto, slechtste 30d som {frac*f.rolling(30).sum().min()*100:.2f}%")
# Selectieve carry: enkel in positie als funding van gisteren > drempel (vermijdt negatieve periodes)
for th in (0.0, 0.0001, 0.0003):
    on = (f.shift(1) > th)
    switches = (on.astype(int).diff().abs() > 0).sum()
    gross = 0.5 * f[on].sum(); cost = 0.5 * switches * (0.0009 + 0.00045)
    print(f"selectieve carry (funding gisteren > {th*100:.2f}%): in positie {on.mean()*100:.0f}%, {switches} wissels, {((1+gross-cost)**(365/len(f))-1)*100:.1f}%/jaar")
# contrair: voorspelt extreme funding de volgende dag/week?
r1 = c.pct_change().shift(-1).reindex(f.index); r7 = (c.shift(-7)/c - 1).reindex(f.index)
q = f.rank(pct=True)
for lo, hi in ((0, .1), (.1, .5), (.5, .9), (.9, 1.0)):
    m = (q > lo) & (q <= hi)
    print(f"funding-kwantiel {lo:.1f}-{hi:.1f}: n={m.sum():3d}  volgende dag {r1[m].mean()*100:+.2f}%  volgende week {r7[m].mean()*100:+.2f}%")
