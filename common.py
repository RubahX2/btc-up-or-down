"""Gedeelde instellingen en features voor BTC up or down.

Hoofdregel: een feature voor dag t gebruikt ALLEEN informatie die bekend is
op het slot van dag t (00:00 UTC van dag t+1). Het doel is: slot t+1 > slot t.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

UI_VERSION = "0.1.2"
MODEL_VERSION = "0.1-logreg"

# Kluis: alles vanaf deze datum blijft buiten de backtest. Vaste datum,
# zodat de kluis niet elke dag mee opschuift. Eén keer openen, op het einde.
VAULT_START = pd.Timestamp("2025-11-01")

# Kosten Hyperliquid perps, basisniveau (per kant, als fractie)
TAKER_FEE = 0.00045
MAKER_FEE = 0.00015
# Aangenomen funding vóór er Hyperliquid-historiek is (long betaalt per dag).
# 0,01% per 8 uur = 0,03% per dag: een normaal marktgemiddelde.
ASSUMED_FUNDING_PER_DAY = 0.0003

MIN_TRAIN_DAYS = 730          # minstens 2 jaar training vóór de eerste voorspelling
LOGREG_C = 0.1                # sterke regularisatie: liever te simpel dan overfit
STRONG_HI, STRONG_LO = 0.60, 0.40

FEATURES = [
    "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r14", "r30",
    "vol7", "vol30", "vol_ratio",
    "d_ema8", "d_ema21", "d_ema50", "d_ema200",
    "rsi14", "macd_hist", "volu_chg", "target_weekend",
]


def load_prices() -> pd.DataFrame:
    df = pd.read_csv(DATA / "btc_daily.csv", parse_dates=["date"])
    return df.sort_values("date").drop_duplicates("date").reset_index(drop=True)


def load_funding() -> pd.Series:
    """Funding per dag (som van uurtarieven), positief = longs betalen."""
    path = DATA / "funding_daily.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    f = pd.read_csv(path, parse_dates=["date"])
    return f.set_index("date")["funding"].sort_index()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rij t = alles wat bekend is op slot t + het doel (slot t+1 > slot t)."""
    out = pd.DataFrame({"date": df["date"], "close": df["close"]})
    c = df["close"]
    lr = np.log(c).diff()

    for k in range(1, 8):
        out[f"r{k}"] = lr.shift(k - 1)          # r1 = rendement van dag t zelf
    out["r14"] = np.log(c / c.shift(14))
    out["r30"] = np.log(c / c.shift(30))
    out["vol7"] = lr.rolling(7).std()
    out["vol30"] = lr.rolling(30).std()
    out["vol_ratio"] = out["vol7"] / out["vol30"]
    for n in (8, 21, 50, 200):
        out[f"d_ema{n}"] = c / c.ewm(span=n, adjust=False).mean() - 1
    out["rsi14"] = (_rsi(c) - 50) / 50
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    out["macd_hist"] = (macd - macd.ewm(span=9, adjust=False).mean()) / c
    v = df["volume"].replace(0, np.nan)
    out["volu_chg"] = np.log(v / v.rolling(20).mean())
    # weekdag van de DOELdag (t+1) is vooraf bekend: geen look-ahead
    out["target_weekend"] = ((df["date"] + pd.Timedelta(days=1)).dt.dayofweek >= 5).astype(float)

    out["next_close"] = c.shift(-1)
    out["ret_next"] = out["next_close"] / c - 1
    out["y"] = np.where(out["next_close"].isna(), np.nan, (out["ret_next"] > 0).astype(float))
    out["r_today"] = c / c.shift(1) - 1
    return out


def fit_model(X: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), LogisticRegression(C=LOGREG_C, max_iter=2000))
    model.fit(X, y)
    return model


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())
