# BTC up or down

Leerproject: elke dag een kansvoorspelling of bitcoin vandaag hoger sluit dan gisteren
(slot 00:00 UTC), publiek en onveranderbaar gelogd, met een papieren portefeuille op
Hyperliquid-perps (1x, long/short) en een walk-forward backtest.

**Geen beleggingsadvies.** Dit is een experiment.

## Bestanden

| Bestand | Wat |
|---|---|
| `fetch_data.py` | BTC-dagkoersen (Coinbase) en Hyperliquid-funding ophalen, data controleren |
| `predict.py` | voorspelling van vandaag loggen, uitkomsten invullen, papieren portefeuille bijwerken |
| `backtest.py` | walk-forward backtest; `--open-vault` opent de kluis (één keer) |
| `common.py` | instellingen, features, versienummers |
| `index.html` | de pagina |
| `data/` | alle output; wordt elke nacht door de workflow gecommit |

## Spelregels

1. Een feature gebruikt alleen wat bekend is op het slot van de dag zelf.
2. Bestaande voorspellingen worden nooit gewijzigd; het script stopt als dat toch zou gebeuren.
3. De kluis (alles vanaf `VAULT_START`) wordt niet gebruikt om te tunen en gaat één keer open.
4. Een nieuw model krijgt een nieuw `MODEL_VERSION` en draait eerst mee als uitdager.
