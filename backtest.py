"""Walk-forward backtest met kluis.

- Het model wordt elke maand opnieuw getraind op ALLES wat vóór die maand
  bekend was, en voorspelt dan die maand. Daarna schuift het een maand op.
- Alles vanaf VAULT_START zit in de kluis en telt NIET mee. De kluis gaat
  één keer open met:  python backtest.py --open-vault   (en daarna nooit meer).
- Scenario's (Hyperliquid perps, 1x, taker-fee bij elke positiewissel, funding):
    1. long/short   2. long/cash   3. kopen en vasthouden (maatstaf)
  plus "altijd long op perps" als baseline.

Gebruik:  python backtest.py [--force] [--open-vault]
"""
import json
import math
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from common import (ASSUMED_FUNDING_PER_DAY, DATA, FEATURES, MIN_TRAIN_DAYS, MODEL_VERSION,
                    STRONG_HI, STRONG_LO, TAKER_FEE, VAULT_START, build_features, fit_model,
                    load_funding, load_prices, max_drawdown)

OUT = DATA / "backtest.json"
BT_VERSION = 2          # verhogen als de backtest zelf verandert (bv. nieuw scenario)
VAULT_OUT = DATA / "vault.json"


def walk_forward(feat: pd.DataFrame, test_start=None, test_end=None) -> pd.DataFrame:
    rows = feat.dropna(subset=FEATURES).copy()
    known = rows.dropna(subset=["y"])
    first_test = known["date"].iloc[0] + pd.Timedelta(days=MIN_TRAIN_DAYS)
    if test_start is not None:
        first_test = max(first_test, test_start)
    months = pd.date_range(first_test.to_period("M").to_timestamp(), rows["date"].max(), freq="MS")
    preds = []
    for m in months:
        nxt = m + pd.offsets.MonthBegin(1)
        # training: enkel rijen waarvan de uitkomst bekend was vóór de eerste voorspelling van de maand
        train = known[known["date"] < m - pd.Timedelta(days=1)]
        test = known[(known["date"] >= m) & (known["date"] < nxt) & (known["date"] >= first_test)]
        if test_end is not None:
            test = test[test["date"] + pd.Timedelta(days=1) < test_end]   # doeldag vóór de kluis
        if len(test) == 0 or len(train) < MIN_TRAIN_DAYS:
            continue
        model = fit_model(train[FEATURES].values, train["y"].values)
        t = test.copy()
        t["p"] = model.predict_proba(test[FEATURES].values)[:, 1]
        # klimatologie: het aandeel stijgdagen dat op dat moment bekend was
        t["p_base"] = train["y"].mean()
        preds.append(t)
    return pd.concat(preds).reset_index(drop=True)


def strategy(pred: pd.DataFrame, pos: pd.Series, funding: pd.Series, perp=True) -> pd.DataFrame:
    target_day = pred["date"] + pd.Timedelta(days=1)
    f = funding.reindex(target_day).fillna(ASSUMED_FUNDING_PER_DAY).values if perp else 0.0
    turnover = (pos - pos.shift(1).fillna(0)).abs()
    fee = turnover * TAKER_FEE
    fund = pos * f
    ret = pos * pred["ret_next"] - fund - fee
    return pd.DataFrame({"date": target_day, "ret": ret, "fee": fee, "fund": fund,
                         "turnover": turnover, "pos": pos})


def summarize(s: pd.DataFrame) -> dict:
    eq = (1 + s["ret"]).cumprod()
    n = len(s)
    sd = s["ret"].std()
    return {
        "total_return": float(eq.iloc[-1] - 1),
        "cagr": float(eq.iloc[-1] ** (365 / n) - 1),
        "max_drawdown": max_drawdown(eq),
        "sharpe": float(s["ret"].mean() / sd * math.sqrt(365)) if sd > 0 else None,
        "trades": int((s["turnover"] > 0).sum()),
        "fees_total": float(s["fee"].sum()),
        "funding_total": float(s["fund"].sum()),
        "time_in_market": float((s["pos"] != 0).mean()),
    }


def hit_stats(pred: pd.DataFrame) -> dict:
    y = pred["y"].values
    p = pred["p"].values
    hit = ((p > 0.5) == (y == 1)).astype(float)
    n = len(y)
    h = hit.mean()
    up_rate = y.mean()
    persist = ((pred["r_today"].values > 0) == (y == 1)).mean()
    brier = float(np.mean((p - y) ** 2))
    brier_base = float(np.mean((pred["p_base"].values - y) ** 2))
    # eenzijdige z-toets: is de hitrate beter dan "altijd omhoog"?
    se = math.sqrt(up_rate * (1 - up_rate) / n)
    z = (h - up_rate) / se
    p_value = 0.5 * math.erfc(z / math.sqrt(2))
    strong = (p >= STRONG_HI) | (p <= STRONG_LO)
    return {
        "n": int(n),
        "hitrate": float(h),
        "hitrate_ci95": [float(h - 1.96 * math.sqrt(h * (1 - h) / n)), float(h + 1.96 * math.sqrt(h * (1 - h) / n))],
        "baseline_always_up": float(up_rate),
        "baseline_persistence": float(persist),
        "baseline_coin": 0.5,
        "p_value_vs_always_up": float(p_value),
        "brier": brier,
        "brier_climatology": brier_base,
        "brier_skill": float(1 - brier / brier_base),
        "strong_n": int(strong.sum()),
        "strong_hitrate": float(hit[strong].mean()) if strong.any() else None,
        "pct_predicted_up": float((p > 0.5).mean()),
    }


def calibration(pred: pd.DataFrame) -> list:
    edges = [0, 0.40, 0.45, 0.50, 0.55, 0.60, 1.0]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (pred["p"] >= lo) & (pred["p"] < hi)
        if m.sum() == 0:
            continue
        out.append({"bin": f"{lo:.2f}–{hi:.2f}", "n": int(m.sum()),
                    "mean_p": float(pred.loc[m, "p"].mean()), "observed": float(pred.loc[m, "y"].mean())})
    return out


def evaluate(pred: pd.DataFrame, funding: pd.Series) -> dict:
    p = pred["p"]
    scen = {
        "long_short": strategy(pred, pd.Series(np.where(p > 0.5, 1.0, -1.0)), funding),
        "long_cash": strategy(pred, pd.Series(np.where(p > 0.5, 1.0, 0.0)), funding),
        "sterk60": strategy(pred, pd.Series(np.where(p >= STRONG_HI, 1.0, 0.0)), funding),
        "buy_hold": strategy(pred, pd.Series(np.ones(len(pred))), funding, perp=False),
        "always_long_perp": strategy(pred, pd.Series(np.ones(len(pred))), funding),
    }
    years = []
    for yr, g in pred.groupby(pred["date"].dt.year):
        idx = g.index
        years.append({
            "year": int(yr), "n": len(g),
            "hitrate": float(((g["p"] > 0.5) == (g["y"] == 1)).mean()),
            "always_up": float(g["y"].mean()),
            "long_short": float((1 + scen["long_short"].loc[idx, "ret"]).prod() - 1),
            "long_cash": float((1 + scen["long_cash"].loc[idx, "ret"]).prod() - 1),
            "sterk60": float((1 + scen["sterk60"].loc[idx, "ret"]).prod() - 1),
            "buy_hold": float((1 + scen["buy_hold"].loc[idx, "ret"]).prod() - 1),
        })
    curves = pd.DataFrame({"date": scen["buy_hold"]["date"]})
    for k, s in scen.items():
        curves[k] = (1 + s["ret"]).cumprod().values
    weekly = curves.set_index("date").resample("W").last().dropna().reset_index()
    return {
        "period": [str(pred["date"].min().date()), str((pred["date"].max() + pd.Timedelta(days=1)).date())],
        "hits": hit_stats(pred),
        "calibration": calibration(pred),
        "scenarios": {k: summarize(s) for k, s in scen.items()},
        "per_year": years,
        "curves": {"dates": [str(d.date()) for d in weekly["date"]],
                   **{k: [round(float(v), 5) for v in weekly[k]] for k in scen}},
    }


def coefficients(feat: pd.DataFrame) -> list:
    known = feat.dropna(subset=FEATURES + ["y"])
    known = known[known["date"] + pd.Timedelta(days=1) < VAULT_START]
    model = fit_model(known[FEATURES].values, known["y"].values)
    coefs = model[-1].coef_[0]
    order = np.argsort(-np.abs(coefs))
    return [{"feature": FEATURES[i], "coef": round(float(coefs[i]), 4)} for i in order]


def main():
    force = "--force" in sys.argv
    open_vault = "--open-vault" in sys.argv
    prices, funding = load_prices(), load_funding()
    feat = build_features(prices)

    if open_vault:
        if VAULT_OUT.exists():
            sys.exit("De kluis is al geopend. Nieuwe kluis = nieuwe VAULT_START + nieuwe run.")
        pred = walk_forward(feat, test_start=VAULT_START - pd.Timedelta(days=1))
        res = evaluate(pred, funding)
        res.update({"model_version": MODEL_VERSION,
                    "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        VAULT_OUT.write_text(json.dumps(res, indent=1))
        print(json.dumps(res["hits"], indent=1))
        return

    if OUT.exists() and not force:
        old = json.loads(OUT.read_text())
        if old.get("model_version") == MODEL_VERSION and old.get("bt_version") == BT_VERSION:
            print("Backtest bestaat al voor", MODEL_VERSION, "— overgeslagen (gebruik --force).")
            return

    pred = walk_forward(feat, test_end=VAULT_START)
    res = evaluate(pred, funding)
    res.update({
        "model_version": MODEL_VERSION,
        "bt_version": BT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vault_start": str(VAULT_START.date()),
        "settings": {"taker_fee": TAKER_FEE, "assumed_funding_per_day": ASSUMED_FUNDING_PER_DAY,
                     "funding_hl_from": str(funding.index.min().date()) if len(funding) else None,
                     "min_train_days": MIN_TRAIN_DAYS, "retrain": "maandelijks", "features": FEATURES},
        "coefficients": coefficients(feat),
    })
    OUT.write_text(json.dumps(res, indent=1))
    h = res["hits"]
    print(f"n={h['n']} hitrate={h['hitrate']:.3f} altijd-omhoog={h['baseline_always_up']:.3f} "
          f"p={h['p_value_vs_always_up']:.3f} brier-skill={h['brier_skill']:.4f}")
    for k, s in res["scenarios"].items():
        print(f"{k:18s} CAGR={s['cagr']:+.1%} maxDD={s['max_drawdown']:.1%} trades={s['trades']}")


if __name__ == "__main__":
    main()
