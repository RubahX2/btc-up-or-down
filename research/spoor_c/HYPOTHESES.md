# Spoor C — vooraf vastgelegde onderzoeksopzet (30-10-2026, vóór enige test)

Data: Coinbase BTC-USD dagcandles 2015-07-20 t/m 2025-10-31. Alles vanaf 2025-11-01 = kluis, niet gebruikt.
Evaluatie: 2016-01-01 t/m 2025-10-31 (warmup 2015). Signaal op slot t, positie geldt voor dag t+1.
Robuustheid: twee helften (2016-01..2020-12 en 2021-01..2025-10), per jaar, parameterburen.

Kostenmodellen
- SPOT (long/cash; Revolut X taker 0,09%/kant, geen funding)
- PERP (Hyperliquid taker 0,045%/kant + funding: echte HL-funding vanaf 2023-05, ervoor 0,03%/dag voor long)

Families (alles hieronder wordt getest, ook wat niets oplevert, en geteld):
F1 Trend: slot > SMA(n); EMA-kruising; Donchian-uitbraak; tijdreeks-momentum (rendement over L dagen > 0)
F2 Volatiliteitssturing: positie = min(1, doelvol / gerealiseerde vol), op F1 en op kopen-en-vasthouden
F3 Mean reversion: kopen na extreme daling (z-score, RSI), h dagen houden
F4 Seizoenen: weekdag, maand, maandwissel
F5 Funding (enkel 2023-05+): contrair op extreme funding; cash-and-carry (long spot + short perp)
F6 Combinaties van de beste families (enkel als F1-F5 iets robuusts opleveren)

Succescriterium voor een kandidaat (voor kosten én na kosten):
1. Sharpe hoger dan kopen-en-vasthouden in BEIDE helften
2. Max drawdown duidelijk lager (minstens 1/3 kleiner) dan kopen-en-vasthouden
3. Parameterburen geven gelijkaardig resultaat (geen piek op één instelling)
4. Overleeft correctie voor het aantal geteste varianten (bootstrap van de beste Sharpe)
Pas daarna: één toets op de kluis — enkel met akkoord van Ruben.
