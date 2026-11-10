# Shared helpers for the intraday research scripts: Alpaca historical bars (free SIP history from 2016), metrics. Research only.
import os, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd

H = {"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""), "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", "")}
START = "2016-01-04"

_last = [0.0]
def _get(url):
    """Throttled (~180 requests/min, under Alpaca's free 200/min) with patient retries on rate limits and network errors."""
    for i in range(40):
        wait = 0.34 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=90))
        except Exception as e:
            code = getattr(e, "code", None)
            body = e.read().decode()[:300] if hasattr(e, "read") else ""
            print("retry", i + 1, code, str(e)[:120], body, flush=True)
            if code in (401, 403) and i >= 1: raise RuntimeError(f"alpaca {code}: {body}")
            time.sleep(60 if code == 429 else min(60, 5 * (i + 1)))
    raise RuntimeError("alpaca failed: " + url[:200])

def bars(symbols, timeframe, start=START, end=None, regular=True):
    """All bars for symbols -> DataFrame [sym, t (NY time), o, h, l, c, v]; regular session only by default."""
    end = end or (pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")  # free plan: no SIP data from the last 15 minutes
    p = {"symbols": ",".join(symbols), "timeframe": timeframe, "start": start, "end": end, "adjustment": "all", "feed": "sip", "limit": "10000"}
    rows = []
    while True:
        js = _get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p))
        for s, bl in (js.get("bars") or {}).items():
            for b in bl: rows.append((s, b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]))
        tok = js.get("next_page_token")
        if not tok: break
        p["page_token"] = tok
    df = pd.DataFrame(rows, columns=["sym", "t", "o", "h", "l", "c", "v"])
    if df.empty: return df
    df["t"] = pd.to_datetime(df.t, utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    if regular:
        mins = df.t.dt.hour * 60 + df.t.dt.minute
        df = df[(mins >= 570) & (mins < 960)]
    return df.sort_values(["sym", "t"]).reset_index(drop=True)

def stats(daily, label=None):
    """daily: pd.Series of daily returns indexed by date -> summary dict."""
    daily = daily.fillna(0)
    if len(daily) < 2: return {}
    eq = (1 + daily).cumprod(); yrs = len(daily) / 252
    o = {"cagr": round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (eq / eq.cummax() - 1).min(), 1),
         "sharpe": round(float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0, 2), "total": round(100 * (eq.iloc[-1] - 1), 1)}
    yr = {}
    for y, q in daily.groupby(daily.index.year): yr[str(y)] = round(100 * ((1 + q).prod() - 1), 1)
    o["by_year"] = yr
    for a, b, k in [("2016", "2024-04-30", "to_apr2024"), ("2024-05-01", "2100", "may2024_on")]:
        q = daily[(daily.index >= a) & (daily.index <= b)]
        if len(q) > 20: o[k] = round(100 * ((1 + q).prod() ** (252 / len(q)) - 1), 1)
    return o

def spy_daily_stats(start=START):
    d = bars(["SPY"], "1Day", start=start, regular=False)
    s = d.set_index(d.t.dt.normalize()).c
    return stats(s.pct_change().dropna())

def save(name, obj):
    os.makedirs("data", exist_ok=True); json.dump(obj, open(f"data/{name}.json", "w"), indent=1, default=float)
