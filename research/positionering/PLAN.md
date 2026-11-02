# Hefboom als voorbode van verliezen — testplan (vastgelegd 30-10-2026 ±17:20 UTC, vóór het ophalen van de data)

Vraag: voorspelt de hefboom in de markt (funding, open interest) de verliezen van C1b of grote dalingen?

Kenmerken (enkel informatie bekend op het dagslot, percentielen enkel t.o.v. het verleden, minstens 180 dagen):
- FUND: gemiddelde Binance-funding over 7 dagen, als percentiel t.o.v. de voorbije dagen
- OI30: verandering van Bybit open interest (in BTC, dus los van de koers) over 30 dagen

Toets 1 (beschrijvend): correlatie van elk kenmerk met de grootste daling in de 30 dagen erna; per kwintiel.
Toets 2 (C1b-trades): verschillen winnaars en verliezers bij instap op FUND en OI30? (Mann-Whitney)
Toets 3 (regels op C1b), kiezen op periode 1, controleren op periode 2:
  R1 geen instap als FUND-percentiel > p           (p = 80, 90, 95)
  R2 uitstappen als FUND-percentiel > p             (p = 80, 90, 95)
  R3 geen instap als OI30 > q                       (q = 20%, 30%, 50%)
  R4 uitstappen als FUND-percentiel > 80 én OI30 > q (q = 20%, 30%)
Periode 1 = start data t/m 2022-12-31, periode 2 = 2023-01-01 t/m 2026-10-29.
Slaagt enkel als Sharpe hoger én max. daling niet slechter dan C1b in BEIDE periodes, met de in periode 1 gekozen instelling.

Aanvulling (30-10-2026 ±17:35 UTC, nog steeds vóór het ophalen van de echte data): een proefrun op willekeurige
nepdata liet R1 'slagen' met Sharpe 1,37 tegen 1,36. Het criterium was dus te los. Nieuw: de Sharpe moet in BEIDE
periodes minstens 0,10 hoger liggen dan die van C1b (en de max. daling niet slechter).
