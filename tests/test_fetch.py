"""Test fetch_prices met een nagemaakte Coinbase-API (paginering, lopende dag eruit, geen gaten)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_data

class Resp:
    status_code = 200
    def __init__(self, d): self.d = d; self.text = str(d)[:50]
    def json(self): return self.d

calls = []
def fake_get(url, params, headers, timeout):
    calls.append(params)
    s = pd.Timestamp(params["start"].rstrip("Z")); e = pd.Timestamp(params["end"].rstrip("Z"))
    days = pd.date_range(s, e, freq="D")                          # Coinbase geeft start t/m end
    return Resp([[int(d.timestamp()), 1, 2, 1, 100 + i, 5] for i, d in enumerate(days)][::-1])

fetch_data.requests.get = fake_get
fetch_data.time.sleep = lambda s: None
df = fetch_data.fetch_prices()
today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
assert df["date"].min() == pd.Timestamp("2015-07-20")
assert df["date"].max() == today - pd.Timedelta(days=1), df["date"].max()
assert df["date"].diff().dt.days.dropna().eq(1).all() and df["date"].is_unique
assert fetch_data.check_prices(df) == []
print(f"fetch: {len(df)} dagen in {len(calls)} aanroepen, laatste {df['date'].max().date()}, geen gaten: OK")
