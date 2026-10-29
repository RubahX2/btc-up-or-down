"""Nepdata om de pipeline te testen zonder internet (random walk met drift)."""
import sys, numpy as np, pandas as pd
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(1)
today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
dates = pd.date_range("2014-09-17", today - pd.Timedelta(days=1), freq="D")
r = rng.normal(0.0012, 0.035, len(dates))
close = 450 * np.exp(np.cumsum(r))
pd.DataFrame({"date": dates, "open": close, "high": close*1.01, "low": close*0.99,
              "close": close, "volume": rng.lognormal(20, 0.5, len(dates))}).to_csv(out/"btc_daily.csv", index=False)
fd = pd.date_range("2023-05-01", today - pd.Timedelta(days=1), freq="D")
pd.DataFrame({"date": fd, "funding": rng.normal(0.0003, 0.0002, len(fd))}).to_csv(out/"funding_daily.csv", index=False)
print(len(dates), "dagen")
