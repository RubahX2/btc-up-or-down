# Meetproef D — verdient market making op kleine Hyperliquid-markten iets?

**Vraag:** als je altijd een kleine koop- en verkooporder op de beste prijzen laat staan, verdien je dan de spread,
of verlies je meer aan handelaars die beter geïnformeerd of sneller zijn (adverse selectie)?

**Methode (markout):** elke echte trade op onze prijs telt als fictieve uitvoering van onze order. We kijken waar de
middenprijs 1, 10, 60 en 300 seconden later staat, en trekken de maker-fee van 0,015% (1,5 bp) af.
Twee varianten: *optimistisch* (elke trade op onze prijs vult ons) en *pessimistisch* (enkel trades die dóór onze prijs gaan).

**Oordeel vooraf vastgelegd:** "mogelijk voordeel" enkel als de pessimistische variant na 60 seconden gemiddeld
positief is, met t > 2 en minstens 100 uitvoeringen. Anders: geen voordeel.

## Starten op de Mac (één week laten lopen)

1. Laptop aan de lader, deksel open, wifi aan.
2. Terminal openen (Programma's → Hulpprogramma's → Terminal) en eenmalig:
   ```
   pip3 install "websockets>=10,<14" requests
   ```
3. Naar deze map gaan en starten:
   ```
   cd ~/Documents/GitHub/btc-up-or-down/research/meetproef_d
   caffeinate -is python3 collect.py
   ```
   Het script kiest zelf 4 kleine maar actieve markten (24u-volume tussen 2 en 50 miljoen USD) plus BTC als referentie.
   `caffeinate` houdt de Mac wakker zolang het script loopt.
4. Laat het venster open staan. Elk uur verschijnt een regel met tellingen. Valt de verbinding weg, dan verbindt het vanzelf opnieuw.
5. Na een week: **Ctrl+C**. Dan:
   ```
   python3 analyse.py
   ```

Stoppen en later herstarten mag: er wordt bijgeschreven. Data komt in `data/` (±50–100 MB per dag) en gaat **niet** mee naar GitHub.

## Wat je niet nodig hebt
Geen account, geen sleutels, geen geld: het script leest enkel publieke marktdata.

## Getest
`tests/mock_server.py` is een nep-Hyperliquid met hetzelfde berichtformaat en twee kunstmatige markten:
een eerlijke (de analyse vindt +3,5 bp = halve spread min fee) en een met geïnformeerde handelaars (de analyse vindt −11 bp).
Ook het herverbinden en het netjes afsluiten bij stoppen zijn getest.
