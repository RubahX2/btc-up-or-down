# Spoor C — strategieonderzoek (30-10-2026)

Draaien: `cd research/spoor_c && python families.py` (daarna f5.py, robust.py, f6.py).
Gebruikt `data/btc_daily.csv` (Coinbase) en `data/funding_daily.csv` uit de repo, afgekapt op 2025-10-31: de kluis blijft dicht.
`HYPOTHESES.md` werd vastgelegd vóór de eerste test. `results_f1_f4.csv` bevat alle 85 geteste varianten van F1–F4.

## Kluistoets (eenmalig, 30-10-2026)
Protocol in `VAULT_PROTOCOL.md` (vastgelegd vóór het openen), uitvoering `vault_test.py` (draaien vanuit de repo-root), resultaat `vault_result.json`.
Kluisjaar 01-11-2025 t/m 29-10-2026: kopen-en-vasthouden −29%, max. daling −47%.
C1 trend-ensemble +10,4% (max. daling −8,8%): geslaagd. A −17%, B +13% op 3 handelsdagen (geen bewijs), C2 carry +2,8% (funding gezakt naar 5,8%/jaar).
De kluis is hiermee gebruikt: deze periode telt voortaan niet meer als onafhankelijke toets.
