# Hefboom als voorbode — resultaat (2 november 2026)

**Afwijking van PLAN.md (vooraf gemeld):** Binance en Bybit zijn onbereikbaar vanuit de onderzoeksomgeving en vanaf
GitHub (VS). De analyse liep daarom in de browser op Ruben's Mac (`analyse_browser.js`, dezelfde toetsen en regels),
per beurs met de eigen perp-dagkoersen i.p.v. Coinbase. Binance: funding + prijs. Bybit: funding + open interest + prijs.
Twee onafhankelijke bronnen = een extra robuustheidscontrole.

| | Binance | Bybit |
|---|---|---|
| Testperiode | 2020-03-26 t/m 2026-10-29 | 2020-10-11 t/m 2026-10-29 |
| Toets 1: rangcorrelatie funding-percentiel met grootste daling 30d | −0,045 | +0,002 |
| Toets 1: rangcorrelatie OI30 met grootste daling 30d | – | −0,024 |
| Toets 2: funding bij instap, winnaars vs verliezers | 34,6 vs 38,2 (p = 0,37) | 36,9 vs 34,3 (p = 0,74) |
| Toets 2: OI30 bij instap, winnaars vs verliezers | – | **+9,8% vs +1,8% (p = 0,011)** |

Toets 3 (Sharpe, gekozen op periode 1, gecontroleerd op periode 2; lat = +0,10 in beide):

| Regel | Binance P1 / P2 | Bybit P1 / P2 | Oordeel |
|---|---|---|---|
| C1b zonder regel | 1,61 / 1,39 | 1,93 / 1,39 | referentie |
| R1 geen instap bij hoge funding | 1,61 / 1,38 | 1,93 / 1,38 | slaagt niet (vrijwel nooit actief) |
| R2 uit bij hoge funding | 0,88–0,99 / 1,40–1,50 | 0,57–0,70 / 1,34–1,49 | slaagt niet: vernielt periode 1 (stierenmarkten hebben hoge funding) |
| R3 geen instap bij snel stijgend OI | – | 2,04 / 1,39 | slaagt niet |
| R4 uit bij hoge funding én stijgend OI | – | 1,09–1,13 / 1,39 | slaagt niet |

**Verkennend (niet vooraf vastgelegd):** toets 2 toonde het omgekeerde van de hypothese: winnende instappen hadden vaker
een STIJGEND open interest (nieuw geld dat de trend draagt). Een regel "enkel instappen als OI30 > 0" gaf P1 2,08 (vs 1,93)
maar P2 1,31 (vs 1,39): niet robuust. Mogelijke kandidaat-hypothese voor later, enkel met eigen data (`data/positioning.csv`).

**Conclusie:** funding en open interest voorspellen de verliezen van C1b niet bruikbaar. Hoge funding gaat samen met sterke
stijgingen, dus erop uitstappen kost de grote winnaars. C1b blijft ongewijzigd.
