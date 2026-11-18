"""Hourly crash exit for the dip bot (Nov 17 2026). Research only, not financial advice.
Question: if the bot checked SPY every hour and sold its dip stocks (and the parking ETF) when the market is crashing that day,
would it earn more or have smaller drops?
Base bot = live rules: point-in-time S&P 500, price >= $5, above 200-day avg, 5-day return >= 10% worse than SPY, volume <= 2x;
10 slots x 10%, buy at the close, sell when close > 5-day avg (after >= 1 day) or after 5 days; idle money in SPY (stand-in for the
Clear Leader ETF) when SPY > 100-day avg, else cash. Costs 0.05%/side.
Crash rule: at the end of each regular-hours hour (10:00 ... 15:00 ET), if SPY is down >= X% from yesterday's close, sell
everything at that hour's price (+0.1% slippage). Variants: X = 1.5 / 2 / 3%; after the exit the bot either skips new buys that day or
buys dips at the close as usual. Hourly bars: Alpaca (SIP, raw prices) 2016-2026; a held stock's exit price = its hourly close
vs its own previous raw close; if Alpaca has no bar for it, its move is estimated as 1.2 x SPY's (counted and reported).
Second trigger type ('falling market'): SPY already 5/7/10% below its 20-day high AND down 1/2% today.
Checks: X = never must equal the base bot exactly; DRY=planted gives crash exits a free +3% (must be found).
DRY=1 uses synthetic hourly data (no network)."""
import os, sys, json, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DRY = os.environ.get("DRY", ""); OUT = os.environ.get("OUT", "data/crash_exit.json" if not DRY else f"/tmp/crash_exit_{DRY}.json")
START = os.environ.get("START", "2016-01-04"); ET = ZoneInfo("America/New_York")
COST, SLIP = 0.0005, 0.001
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "2014-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOL = P("adj_close"), P("close"), P("volume"); del px
tick = [t for t in ALLT if t != "SPY"]; D = len(dates)
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
valid = A[tick].notna(); M &= valid & valid.shift(-1, fill_value=False)
Cs = A[tick].ffill(); spy = A["SPY"].ffill()
ex5 = (Cs / Cs.shift(5) - 1).sub(spy / spy.shift(5) - 1, axis=0)
vr = VOL[tick].rolling(5).mean() / VOL[tick].shift(5).rolling(50).mean()
SIG = (M & (RAW[tick] >= 5) & (vr <= 2.0) & (Cs > Cs.rolling(200).mean()) & (ex5 <= -0.10)).values
C, M5, RK, SP = Cs.values, Cs.rolling(5).mean().values, ex5.values, spy.values
RAWC, SPRAW = RAW[tick].values, RAW["SPY"].values
spyr = np.r_[0, SP[1:] / SP[:-1] - 1]; park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]
dn = dates.values; t0 = int(np.searchsorted(dn, np.datetime64(START))); ds = [str(d)[:10] for d in dn]

# ---------------- hourly data
H = {"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""), "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", "")}
RATE = float(os.environ.get("RATE_PER_MIN", "150")); _last = [0.0]; CALLS = [0]
def get(url):
    for i in range(10):
        w = 60.0 / RATE - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.time(); CALLS[0] += 1
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = e.headers.get("Retry-After"); time.sleep(float(ra) if ra and ra.replace(".", "").isdigit() else min(120, 15 * (i + 1))); continue
            if e.code in (400, 403, 404, 422): print("HTTP", e.code, e.read()[:200], flush=True); return None
            time.sleep(5 * (i + 1))
        except Exception: time.sleep(3 * (i + 1))
    return None
def hourly(symbols, start, end):
    """{sym: {date: [(hour_end_et, close), ...]}} regular-hours checkpoints 10:00..15:00 ET, raw prices"""
    out, tok = {}, None
    while True:
        p = {"symbols": ",".join(symbols), "timeframe": "1Hour", "start": start, "end": end, "adjustment": "raw", "feed": "sip", "limit": "10000"}
        if tok: p["page_token"] = tok
        js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p))
        if not js: break
        for s, bars in (js.get("bars") or {}).items():
            for b in bars:
                t = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET); end_h = t.hour + 1
                if 10 <= end_h <= 15 and t.minute == 0: out.setdefault(s, {}).setdefault(t.strftime("%Y-%m-%d"), []).append((end_h, b["c"]))
        tok = js.get("next_page_token")
        if not tok: break
    return out
if DRY:
    rng = np.random.default_rng(5); SPYH = {}
    for i in range(t0, D):
        r = SPRAW[i] / SPRAW[i - 1] - 1; path = [SPRAW[i - 1] * (1 + r * k / 6 + rng.normal(0, 0.003)) for k in range(1, 7)]
        SPYH[ds[i]] = list(zip(range(10, 16), path))
else:
    end = (pd.Timestamp.today(tz="UTC") - pd.Timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")
    SPYH = {}
    for y in range(int(START[:4]), 2027):
        a = f"{y}-01-01T00:00:00Z"; b = min(f"{y + 1}-01-01T00:00:00Z", end)
        if a >= end: break
        SPYH.update(hourly(["SPY"], a, b).get("SPY", {}))
    print("SPY hourly days:", len(SPYH), flush=True)
    if len(SPYH) < 1000: raise SystemExit("too little SPY hourly data - check Alpaca keys / feed")

SPHI20 = pd.Series(SPRAW).rolling(20, min_periods=15).max().values      # SPY's highest close of the last 20 days (raw)
def trigger(i, X, falling=None):
    """first hourly checkpoint today where SPY is down >= X from yesterday's close -> (hour, spy_return_at_that_hour).
    falling=F: only when SPY is ALSO already >= F below its 20-day high (a market that keeps sliding, not one bad day)."""
    if falling and not (SPRAW[i - 1] / SPHI20[i - 1] - 1 <= -falling): return None
    for h, c in sorted(SPYH.get(ds[i], [])):
        r = c / SPRAW[i - 1] - 1
        if r <= -X: return h, r
    return None
STOCKH, FALLBACK = {}, [0, 0]
def stock_ret_at(j, i, h, spy_r):
    s = tick[j].rsplit("-", 1)[0] if tick[j][-7:-6] == "-" and tick[j][-6:].isdigit() else tick[j]
    FALLBACK[1] += 1
    if DRY: return (RAWC[i, j] / RAWC[i - 1, j] - 1) * h / 15
    if (s, ds[i]) not in STOCKH:
        d = hourly([s.replace("-", ".")], ds[i] + "T00:00:00Z", ds[i] + "T23:59:00Z"); STOCKH[(s, ds[i])] = (d.get(s.replace("-", ".")) or {}).get(ds[i], [])
    for hh, c in STOCKH[(s, ds[i])]:
        if hh == h and RAWC[i - 1, j] > 0: return c / RAWC[i - 1, j] - 1
    FALLBACK[0] += 1; return 1.2 * spy_r

def sim(X=None, buy_after=True, sell_park=True, bonus=0.0, falling=None):
    pos, eq, curve, trades, events = [], 1.0, np.ones(D), [], []
    for t in range(t0, D):
        trig = trigger(t, X, falling) if X else None
        if trig:
            h, sr = trig; r = 0.0
            for j, e, bp in pos:
                rr = stock_ret_at(j, t, h, sr); r += 0.10 * (rr - SLIP - COST + bonus)
                trades.append((e, (C[t - 1, j] * (1 + rr)) / bp - 1 - 2 * COST))
            later = sum(0.10 * (C[t, j] / C[t - 1, j] - 1) for j, _, _ in pos)            # what the stocks did by the close instead
            if park_on[t]: r += (1 - 0.10 * len(pos)) * ((sr - SLIP) if sell_park else spyr[t])
            events.append({"day": ds[t], "hour_et": h, "spy_at_exit_pct": round(sr * 100, 2), "spy_close_pct": round(spyr[t] * 100, 2),
                           "stocks_sold": len(pos), "stocks_by_close_pct_of_account": round(later * 100, 2)})
            eq *= 1 + r; pos = []
            if not buy_after: curve[t] = eq; continue
        else:
            r = sum(0.10 * (C[t, j] / C[t - 1, j] - 1) for j, _, _ in pos)
            if park_on[t]: r += (1 - 0.10 * len(pos)) * spyr[t]
            eq *= 1 + r; keep = []
            for j, e, bp in pos:
                age = t - e
                if age >= 1 and (C[t, j] > M5[t, j] or age >= 5): eq *= 1 - 0.10 * COST; trades.append((e, C[t, j] / bp - 1 - 2 * COST))
                else: keep.append((j, e, bp))
            pos = keep
        held = {j for j, _, _ in pos}
        for j in sorted([j for j in np.flatnonzero(SIG[t]) if j not in held], key=lambda j: RK[t, j])[:10 - len(pos)]:
            pos.append((j, t, C[t, j])); eq *= 1 - 0.10 * COST
        curve[t] = eq
    out = {"exits": len(events)}
    for name, a, b in (("2016-2026", START, "2100-01-01"), ("2016-2020", START, "2021-01-01"), ("2021-2026", "2021-01-01", "2100-01-01"), ("2020 (covid)", "2020-01-01", "2021-01-01"), ("2022 (bear)", "2022-01-01", "2023-01-01")):
        ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
        cv = curve[ix] / curve[ix[0]]; y = len(ix) / 252
        out[name] = {"per_year_pct" if y > 1.5 else "return_pct": round(((cv[-1] ** (1 / y)) - 1) * 100 if y > 1.5 else (cv[-1] - 1) * 100, 1),
                     "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1)}
    if events:
        ev = pd.DataFrame(events)
        out["avg_spy_at_exit_pct"] = round(ev.spy_at_exit_pct.mean(), 2); out["avg_spy_close_on_exit_days_pct"] = round(ev.spy_close_pct.mean(), 2)
        out["exits_where_spy_recovered_by_close"] = int((ev.spy_close_pct > ev.spy_at_exit_pct).sum())
        out["events"] = events[-40:]
    return out

RES = {"rules as now (no crash exit)": sim()}
chk = sim(X=9.99)
assert abs(chk["2016-2026"]["per_year_pct"] - RES["rules as now (no crash exit)"]["2016-2026"]["per_year_pct"]) < 1e-9, "X=never must equal the base bot"
print("check ok: crash exit that never fires = base bot", flush=True)
V = [(f"SPY -{x*100:g}% intraday -> sell all{'' if ba else ', no buys that day'}{'' if sp else ' (keep parking)'}", dict(X=x, buy_after=ba, sell_park=sp))
     for x in (0.015, 0.02, 0.03) for ba in (True, False) for sp in (True, False)]
V += [(f"falling market: SPY {f*100:g}%+ below 20-day high AND -{x*100:g}% today -> sell all", dict(X=x, falling=f)) for f in (0.05, 0.07, 0.10) for x in (0.01, 0.02)]
if DRY == "planted": V.append(("PLANTED: -2% exit with a free +3%", dict(X=0.02, bonus=0.03)))
for name, kw in V:
    RES[name] = sim(**kw)
base = RES["rules as now (no crash exit)"]
for name, r in RES.items():
    print(f"{name:58s} {r['2016-2026']['per_year_pct']}%/yr worst {r['2016-2026']['worst_drop_pct']}% | exits {r['exits']} | 2016-20 {r['2016-2020']['per_year_pct']} 2021-26 {r['2021-2026']['per_year_pct']} | 2020 {r['2020 (covid)']['return_pct']}% (dd {r['2020 (covid)']['worst_drop_pct']}) 2022 {r['2022 (bear)']['return_pct']}%"
          + (f" | SPY at exit {r.get('avg_spy_at_exit_pct')}% -> close {r.get('avg_spy_close_on_exit_days_pct')}%, recovered {r.get('exits_where_spy_recovered_by_close')}" if r.get("exits") else ""), flush=True)
print(f"stock exit prices: {FALLBACK[1]} needed, {FALLBACK[0]} estimated (no Alpaca bar); Alpaca calls {CALLS[0]}", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "fallback_estimates": FALLBACK, "results": RES},
          open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
