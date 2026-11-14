# ATR limit-order check with 1-minute bars (research only, not advice).
# Daily-bar tests can't tell whether a stock hit its low (our limit buy) before or after its high (our target).
# Here, for every signal (top 10 a day per setup), we replay the entry day minute by minute from Alpaca SIP data (2016+):
#   limit buy at yesterday's close - 0.5 ATR; once filled, sell at entry + k ATR if a LATER minute reaches it;
#   otherwise hold to the close of day `hold` (later days use daily bars: gap above target sells at the open).
# The same trades are also scored with the old optimistic daily rule (v2) and the strict daily rule (v3) for comparison.
import os, re, sys, json, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd, numpy as np

REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e); time.sleep(20 * (i + 1))
KEY, SEC = os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"]
NY = ZoneInfo("America/New_York")
START, END = os.environ.get("START", "2016-06-01"), os.environ.get("END", "2026-10-30")

px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "high", "low", "close", "adj_close"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "2015-01-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})].copy()
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); T = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v).reindex(index=dates, columns=T)
RO, RH, RL, RC, AC = P("open"), P("high"), P("low"), P("close"), P("adj_close"); del px
tick = [t for t in T if t != "SPY"]
f = AC[tick] / RC[tick]                          # adjusted / raw
aH, aL, aC = RH[tick] * f, RL[tick] * f, AC[tick]
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
valid = aC.notna(); M &= valid & valid.shift(-1, fill_value=False)
spy = AC["SPY"].ffill()
pc = aC.shift(1)
tr = np.maximum.reduce([(aH - aL).values, (aH - pc).abs().values, (aL - pc).abs().values])
atrp = (pd.DataFrame(tr, index=dates, columns=tick).rolling(14).mean() / aC).values
above = (aC > aC.rolling(200).mean()).values
rel5 = aC.pct_change(5).sub(spy.pct_change(5), axis=0).values
near20 = (aC >= aC.rolling(20).max() * 0.98).values
r1 = aC.pct_change().values
ok = M.values & np.isfinite(atrp) & (atrp > 0)
SETUPS = {
    "momentum (trend + near 20d high)": (above & near20 & ok, rel5),
    "down day (trend + red day)": (above & (r1 < 0) & ok, -r1),
    "dip10 (live dip signal)": (above & (rel5 <= -0.10) & ok, -rel5),
}
KS, HOLDS, LIM = [0.5, 1.0, 1.5], [1, 2, 3], 0.5
Ro, Rh, Rl, Rc = RO[tick].values, RH[tick].values, RL[tick].values, RC[tick].values
i0, i1 = int(np.searchsorted(dates.values, np.datetime64(START))), int(np.searchsorted(dates.values, np.datetime64(END)))

BAD = set(); ERRS = []
def fetch_bars(q):
    for a in range(6):
        try:
            req = urllib.request.Request("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(q),
                                         headers={"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC})
            js = json.load(urllib.request.urlopen(req, timeout=60)); time.sleep(0.32); return js   # stay under 200 requests/min
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 422):
                body = e.read().decode("utf-8", "ignore")[:200]
                if len(ERRS) < 20: ERRS.append(f"{e.code} {q['symbols'][:60]} {body}"); print("bad request", e.code, q["symbols"][:60], body, flush=True)
                return None
            time.sleep(3 * (a + 1))
        except Exception:
            time.sleep(3 * (a + 1))
    return None
def bars(day, syms):
    syms = [x for x in syms if x not in BAD]; out = {}
    def run(group):
        q = {"symbols": ",".join(group), "timeframe": "1Min", "start": f"{day}T08:00:00Z", "end": f"{day}T23:59:00Z",
             "feed": "sip", "adjustment": "raw", "limit": "10000"}
        while True:
            js = fetch_bars(q)
            if js is None: return False
            for s, bl in (js.get("bars") or {}).items():
                for b in bl:
                    t = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY); mn = t.hour * 60 + t.minute
                    if 570 <= mn < 960: out.setdefault(s, []).append((b["o"], b["h"], b["l"], b["c"]))
            if not js.get("next_page_token"): return True
            q["page_token"] = js["next_page_token"]
    if syms and not run(syms):          # a bad symbol spoils the whole request: retry one by one and remember bad ones
        for x in syms:
            if x not in out and not run([x]): BAD.add(x)
    return out
def later_days(j, t, ent, tg, hold):
    """Days 2..hold on daily raw bars. Returns exit price."""
    for h in range(1, hold):
        d = t + h
        if d >= len(dates) or not np.isfinite(Rc[d, j]): return Rc[d - 1, j]
        if Ro[d, j] >= tg: return Ro[d, j]
        if Rh[d, j] >= tg: return tg
    return Rc[t + hold - 1, j]

RES = {}; stats = {"days": 0, "requests_days": 0, "missing": 0, "mismatch": 0}
for t in range(i0, min(i1, len(dates) - 4)):
    e = t + 1; day = str(dates[e].date()); want = {}
    for name, (S, R) in SETUPS.items():
        c = np.where(S[t])[0]
        if len(c): want[name] = list(c[np.argsort(-R[t, c])][:10])
    js = sorted({j for v in want.values() for j in v})
    syms = [tick[j] for j in js if not re.search(r"-\d{6}$", tick[j])]
    if not syms: continue
    mb = bars(day, syms); stats["requests_days"] += 1
    for name, cand in want.items():
        for j in cand:
            s = tick[j]; b = mb.get(s)
            if not b: stats["missing"] += 1; continue
            if not np.isfinite(Ro[e, j]) or abs(b[0][0] / Ro[e, j] - 1) > 0.03: stats["mismatch"] += 1; continue
            a = atrp[t, j]; lim = Rc[t, j] * (1 - LIM * a); opn = Ro[e, j]
            # minute replay: fill bar, then target only in later bars
            fill, fi = None, None
            for i, (o, h, l, c) in enumerate(b):
                if i == 0 and o <= lim: fill, fi = o, i; break          # opened below the limit: filled at the open
                if l <= lim * 0.999: fill, fi = lim, i; break           # traded through the limit during the day: filled at the limit
            daily_fill = Rl[e, j] <= lim * 0.999
            for k in KS:
                for hold in HOLDS:
                    key = f"{name} | target {k} ATR | hold {hold}d"
                    r = RES.setdefault(key, {"signals": 0, "minute": [], "v2_daily": [], "v3_daily": []})
                    r["signals"] += 1
                    if daily_fill:
                        ent = min(opn, lim); tg = ent * (1 + k * a)
                        ex2 = tg if Rh[e, j] >= tg else (Rc[e, j] if hold == 1 else later_days(j, e, ent, tg, hold))
                        r["v2_daily"].append(ex2 / ent - 1)
                        ex3 = Rc[e, j] if hold == 1 else later_days(j, e, ent, tg, hold)
                        r["v3_daily"].append(ex3 / ent - 1)
                    if fill is not None:
                        tg = fill * (1 + k * a); ex = None
                        for (o, h, l, c) in b[fi + 1:]:
                            if h >= tg: ex = tg; break
                        if ex is None: ex = b[-1][3] if hold == 1 else later_days(j, e, fill, tg, hold)
                        r["minute"].append(ex / fill - 1)
    stats["days"] += 1
    if stats["days"] % 100 == 0: print(day, stats, flush=True)

yrs = (dates[min(i1, len(dates) - 1)] - dates[i0]).days / 365.25
def summ(v, sig):
    v = np.array(v)
    if not len(v): return {"trades": 0}
    o = {"trades": int(len(v)), "fill_rate": round(100 * len(v) / sig, 1), "trades_per_yr": round(len(v) / yrs),
         "win_gross": round(100 * float((v > 0).mean()), 1), "avg_gross": round(100 * float(v.mean()), 3)}
    for cost in (0.0005, 0.0015):
        n = v - 2 * cost; o[f"avg_net_{cost * 100:g}%"] = round(100 * float(n.mean()), 3)
        # rough yearly growth if each trade is 10% of the account (10 slots, slot limits ignored)
        o[f"approx_yearly_{cost * 100:g}%"] = round(100 * float(np.exp(min(len(n) / yrs, 2520) * np.log1p(0.1 * n.mean())) - 1), 1)
    return o
OUT = {"bad_symbols": sorted(BAD), "request_errors": ERRS, "built": time.strftime("%Y-%m-%d"), "period": f"{dates[i0].date()} to {dates[min(i1, len(dates) - 1)].date()}", "stats": stats,
       "note": "minute = replayed on 1-min bars (truth); v2_daily = old test (assumed low before high, inflated); v3_daily = strict daily rule", "results": {}}
for key, r in RES.items():
    OUT["results"][key] = {m: summ(r[m], r["signals"]) for m in ("minute", "v2_daily", "v3_daily")}
    print(key, json.dumps(OUT["results"][key]["minute"]), "| v2", OUT["results"][key]["v2_daily"].get("avg_gross"), "| v3", OUT["results"][key]["v3_daily"].get("avg_gross"), flush=True)
os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/atr_minute.json", "w"), indent=1)
print(json.dumps(stats))
