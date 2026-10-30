import numpy as np, pandas as pd
from pathlib import Path
D = Path(__file__).resolve().parents[2] / "data"  # repo/data
DEV_END = pd.Timestamp("2025-10-31"); EVAL_START = pd.Timestamp("2016-01-01")
H1 = (pd.Timestamp("2016-01-01"), pd.Timestamp("2020-12-31")); H2 = (pd.Timestamp("2021-01-01"), DEV_END)
SPOT_FEE, PERP_FEE, ASSUMED_FUND = 0.0009, 0.00045, 0.0003

def load():
    px = pd.read_csv(D/"btc_daily.csv", parse_dates=["date"]).set_index("date")
    px = px[px.index <= DEV_END]                                   # kluis dicht
    f = pd.read_csv(D/"funding_daily.csv", parse_dates=["date"]).set_index("date")["funding"]
    f = f[f.index <= DEV_END]
    return px, f

PX, FUND = load()
RET = PX["close"].pct_change()

def run(signal, venue="spot", px=PX):
    """signal: positie bepaald op slot t (index t), geldt voor dag t+1. Waarden in [-1, 1]."""
    pos = signal.reindex(px.index).fillna(0).clip(-1, 1)
    held = pos.shift(1).fillna(0)                                   # positie tijdens dag t
    turnover = (held - held.shift(1).fillna(0)).abs()
    gross = held * RET.reindex(px.index).fillna(0)
    if venue == "spot":
        assert (pos >= 0).all(), "spot kan niet short"
        cost = turnover * SPOT_FEE; fund = 0
    else:
        fr = FUND.reindex(px.index).fillna(ASSUMED_FUND)
        cost = turnover * PERP_FEE; fund = held * fr
    net = gross - cost - fund
    return net[net.index >= EVAL_START], held[held.index >= EVAL_START]

def stats(r, held=None):
    if len(r) == 0: return {}
    eq = (1 + r).cumprod(); n = len(r)
    sd = r.std()
    dd = (eq / eq.cummax() - 1).min()
    cagr = eq.iloc[-1] ** (365 / n) - 1
    out = {"cagr": cagr, "sharpe": r.mean() / sd * np.sqrt(365) if sd > 0 else np.nan,
           "maxdd": dd, "calmar": cagr / abs(dd) if dd < 0 else np.nan}
    if held is not None:
        out["exposure"] = (held.abs() > 0).mean()
        out["trades_per_yr"] = ((held - held.shift(1).fillna(0)).abs() > 0).sum() / (n / 365)
    return out

def full(r, held):
    s = {"all": stats(r, held)}
    for k, (a, b) in (("h1", H1), ("h2", H2)):
        m = (r.index >= a) & (r.index <= b); s[k] = stats(r[m], held[m])
    return s

BH_SIGNAL = pd.Series(1.0, index=PX.index)
