# Kluistoets — protocol, vastgelegd vóór het openen (30-10-2026, ±10:15 UTC)

Periode: 2025-11-01 t/m 2026-10-29 (laatste afgesloten Coinbase-dag). Eenmalig. Niets wordt daarna bijgesteld op basis van deze uitkomst.
Strategieën en instellingen exact zoals vastgelegd vóór het openen:
- A  kampioen 0.2-logreg-cb, long/short, Hyperliquid perps (0,045%/kant + echte funding), maandelijks hertraind op enkel verleden
- B  zelfde voorspelling, long als p>=0,60 anders cash, perps
- C1 trend-ensemble: long als >=5 van 8 signalen (slot>SMA20/50/100/200, rendement 14/30/60/90d>0), spot 0,09%/kant
- C2 funding carry: helft spot, helft onderpand voor perp-short 1x; opbrengst = 0,5 × funding − kosten
Referenties: kopen-en-vasthouden spot; altijd long perps.

Slaagcriteria (per strategie):
- A, B: hitrate (A) boven 'altijd omhoog' op dezelfde dagen; rendement na kosten boven 'altijd long perps'.
- C1: Sharpe hoger dan kopen-en-vasthouden ÉN max. daling kleiner dan die van kopen-en-vasthouden.
- C2: positief netto rendement en geen maand met verlies > 2%.
Kanttekening vooraf: 1 jaar = ±364 dagen; één jaar kan door één marktregime gedomineerd worden. Een geslaagde toets is bemoedigend, geen bewijs.
