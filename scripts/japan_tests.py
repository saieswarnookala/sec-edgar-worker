"""Japan tests (Nov 18 2026), after looking at Bengal Asset Management (Japan long/short hedge fund). Research only, not financial advice.
A) Clear Leader v2.0 with Japan added to its pool: EWJ (Japan, yen not hedged, 1996+) and/or DXJ (yen hedged, 2006+;
   before that the Nikkei 225 price index in yen stands in = roughly 'hedged'). Same rules as scripts/clear_leader_long.py.
B) ETF dips on Japan: EWJ / DXJ 5-day drop >= 5%, above 200-day, buy at close, sell back above 5-day avg (max 10 days), vs SPY same days.
C) The dip bot on Japanese stocks: today's Nikkei 225 members (Yahoo XXXX.T) - NOTE: today's list = survivorship bias (losers that
   left the index are missing), so every result is also compared with a RANDOM-pick bot on the same stocks (same slots/exits).
   Rules = US bot: 5-day return >= 10% worse than the Nikkei, above 200-day, volume <= 2x, 10 slots x 10%, sell when close > 5-day avg
   (after >= 1 day) or 5 days; idle money in a Nikkei ETF (1321.T) when the Nikkei > 100-day avg, else cash.
   Ideal = buy at the signal close, 0.10%/side; realistic = next open, 0.20%/side. Returns in yen (a US investor could hedge the yen).
   Only trade-able from the US through a few ADRs (TM, SONY, MUFG, SMFG, MFG, HMC, NMR, IX...), so C is a 'does the idea work there' check.
DRY=1: fake prices (no network) for B and C to test the code; random data must show no edge."""
import os, re, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
DRY = os.environ.get("DRY", ""); OUT = "data/japan_tests.json" if not DRY else "/tmp/japan_tests_dry.json"
UA = {"User-Agent": "Mozilla/5.0"}
def ydf(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); d = pd.bdate_range("2000-01-03", "2026-11-13")
        c = 1000 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, len(d)))); o = c * np.exp(rng.normal(0, 0.005, len(d)))
        return pd.DataFrame({"o": o, "c": c, "a": c, "v": rng.integers(1e5, 1e6, len(d)).astype(float)}, index=d)
    err = None
    for a in range(5):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))["chart"]["result"][0]
            q = j["indicators"]["quote"][0]; adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            idx = pd.to_datetime([time.strftime("%Y-%m-%d", time.gmtime(t + 9 * 3600)) for t in j["timestamp"]])   # Tokyo date
            df = pd.DataFrame({"o": q["open"], "c": q["close"], "a": adj, "v": q.get("volume")}, index=idx)
            df = df[(df.c > 0)].dropna(subset=["c", "a"]); df = df[~df.index.duplicated(keep="last")].sort_index()
            time.sleep(0.35); return df
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("Yahoo failed", sym, str(err)[:100], flush=True); return None
RES = {}

# ---------------- A) Clear Leader + Japan
if not DRY:
    src = open("scripts/clear_leader_long.py").read()
    src = src.replace('os.makedirs("data", exist_ok=True); json.dump(res, open("data/clear_leader_long.json", "w"), indent=1)', "")
    A = {}
    for name, extra in [("Clear Leader as now", ""), ("+ Japan EWJ", '"EWJ": [], '), ("+ Japan hedged DXJ", '"DXJ": ["^N225"], '), ("+ EWJ and DXJ", '"EWJ": [], "DXJ": ["^N225"], ')]:
        g = {"__name__": "cl"}; exec(src.replace('"GLD": ["GC=F"], ', '"GLD": ["GC=F"], ' + extra), g)
        v = g["res"]["variants"]["clear_leader"]
        A[name] = {"full": v["full"], "dotcom_1998_2002": v["p1998_2002_dotcom"], "2003_2007": v["p2003_2007"], "2008_2009": v["p2008_2009"], "2010_now": v["p2010_now"],
                   "months_held": v["months_held"], "trades": v["trades"]}
        f = v["full"]["strategy"]; print(f"A {name:22s} {f['cagr']}%/yr worst {-f['maxDD']}% | 2010+ {v['p2010_now']['strategy']['cagr']}% | held {v['months_held']}", flush=True)
    RES["A_clear_leader_with_japan"] = A

# ---------------- B) Japan ETF dips
def etf_dips(df, spy):
    c = df.a; ma200 = c.rolling(200).mean(); ma5 = c.rolling(5).mean(); r5 = c / c.shift(5) - 1
    s = spy.a.reindex(c.index).ffill(); out = []; i = 200; n = len(c)
    while i < n - 1:
        if r5.iloc[i] <= -0.05 and c.iloc[i] > ma200.iloc[i]:
            for k in range(1, 11):
                e = min(i + k, n - 1)
                if c.iloc[e] > ma5.iloc[e] or k == 10: break
            r = c.iloc[e] / c.iloc[i] - 1 - 0.0004; rs = s.iloc[e] / s.iloc[i] - 1
            out.append((str(c.index[i])[:10], r, rs)); i = e + 1
        else: i += 1
    if not out: return {"trades": 0}
    x = np.array([[a, b] for _, a, b in out])
    half = lambda a, b: [t for t in out if a <= t[0] < b]
    st = lambda T: {"trades": len(T), "avg_pct": round(float(np.mean([t[1] for t in T])) * 100, 2), "vs_spy_pct": round(float(np.mean([t[1] - t[2] for t in T])) * 100, 2), "win_pct": round(float(np.mean([t[1] > 0 for t in T])) * 100)} if T else {"trades": 0}
    return {"all": st(out), "before_2013": st(half("0", "2013")), "2013_on": st(half("2013", "9"))}
spyd = ydf("SPY"); B = {}
for s in ("EWJ", "DXJ", "SPY", "EFA"):
    d = ydf(s)
    if d is not None: B[s] = etf_dips(d, spyd); print("B", s, json.dumps(B[s]), flush=True)
RES["B_japan_etf_dips"] = B

# ---------------- C) dip bot on Nikkei 225 stocks
def members():
    if DRY: return [str(1000 + 7 * i) for i in range(225)]
    codes = set()
    for u in ("https://indexes.nikkei.co.jp/en/nkave/index/component?idx=nk225", "https://en.wikipedia.org/wiki/Nikkei_225"):
        try:
            h = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read().decode("utf-8", "ignore")
            found = set(re.findall(r">\s*(\d{3}[0-9A-Z])\s*<", h)) if "nikkei.co.jp" in u else set(re.findall(r"(?:TYO|TSE)\s*:?\s*(?:<[^>]+>\s*)*(\d{3}[0-9A-Z])", h))
            print("members from", u, len(found), flush=True)
            if 200 <= len(found) <= 260: return sorted(found)
            codes |= found
        except Exception as e: print("members fail", u, str(e)[:100], flush=True)
    if not 200 <= len(codes) <= 300: raise SystemExit(f"could not get the Nikkei 225 list ({len(codes)} codes)")
    return sorted(codes)
CODES = members()
idx = ydf("^N225"); etf = ydf("1321.T")
if idx is None or etf is None: raise SystemExit("no Nikkei data")
days = idx.index[idx.index >= "1999-01-01"]
O, Cc, Aa, V = {}, {}, {}, {}
for code in CODES:
    d = ydf(code + ".T")
    if d is None or len(d) < 300: continue
    d = d.reindex(days)
    f = d.a / d.c; O[code], Cc[code], Aa[code], V[code] = d.o * f, d.c, d.a, d.v
print("Japan stocks with data:", len(Aa), "of", len(CODES), flush=True)
if len(Aa) < 150: raise SystemExit("too few Japanese stocks loaded")
Adf = pd.DataFrame(Aa).ffill(limit=5); Odf = pd.DataFrame(O); Craw = pd.DataFrame(Cc); Vdf = pd.DataFrame(V)
nk = idx.a.reindex(days).ffill(); pk = etf.a.reindex(days).ffill()
first = Adf.notna().cumsum()
ex5 = (Adf / Adf.shift(5) - 1).sub(nk / nk.shift(5) - 1, axis=0)
vr = Vdf.rolling(5).mean() / Vdf.shift(5).rolling(50).mean()
up200 = Adf > Adf.rolling(200).mean()
SIG = (up200 & (ex5 <= -0.10) & ((vr <= 2.0) | vr.isna()) & (first >= 260)).values
ELIG = (up200 & (first >= 260)).values
C, M5, RK, OP = Adf.values, Adf.rolling(5).mean().values, ex5.values, Odf.values
pkr = np.r_[0, pk.values[1:] / pk.values[:-1] - 1]; pkr = np.nan_to_num(pkr)
park_on = np.r_[False, (nk > nk.rolling(100).mean()).values[:-1]]
D = len(days); dn = days.values; t0 = int(np.searchsorted(dn, np.datetime64("2001-08-01")))   # 1321.T starts 2001-07
def bot(entry="close", cost=0.001, rand=None, park=True):
    rng = np.random.default_rng(rand) if rand is not None else None
    pos, eq, curve, trades = [], 1.0, np.ones(D), []
    for t in range(t0, D):
        r = 0.0
        for j, e, bp in pos:
            c0 = C[t - 1, j]
            if np.isfinite(C[t, j]) and np.isfinite(c0) and c0 > 0: r += 0.10 * (C[t, j] / c0 - 1)
        if park and park_on[t]: r += (1 - 0.10 * len(pos)) * pkr[t]
        eq *= 1 + r; keep = []
        for j, e, bp in pos:
            age = t - e
            if age >= 1 and (C[t, j] > M5[t, j] or age >= 5 or not np.isfinite(C[t, j])): eq *= 1 - 0.10 * cost; trades.append((t, C[t, j] / bp - 1 - 2 * cost))
            else: keep.append((j, e, bp))
        pos = keep; held = {j for j, _, _ in pos}
        if entry == "close": cand = [j for j in np.flatnonzero(SIG[t]) if j not in held]; cand.sort(key=lambda j: RK[t, j])
        else: cand = [j for j in np.flatnonzero(SIG[t - 1]) if j not in held and t - 1 >= t0]; cand.sort(key=lambda j: RK[t - 1, j])
        if rng is not None:                                     # random picks: same number of new buys, from eligible stocks
            pool = [j for j in np.flatnonzero(ELIG[t if entry == "close" else t - 1]) if j not in held]
            cand = list(rng.choice(pool, size=min(len(cand), len(pool)), replace=False)) if pool and cand else []
        for j in cand[:10 - len(pos)]:
            if entry == "close": bp = C[t, j]
            else:
                bp = OP[t, j]
                if not (np.isfinite(bp) and bp > 0): continue
                eq *= 1 + 0.10 * (C[t, j] / bp - 1)                     # today's move after the open
            if not np.isfinite(bp): continue
            pos.append((j, t, bp)); eq *= 1 - 0.10 * cost
        curve[t] = eq
    return curve, trades
def summ(curve, trades):
    o = {}
    for name, a, b in (("2001-2026", "2001-08-01", "2100-01-01"), ("2001-2013", "2001-08-01", "2014-01-01"), ("2014-2026", "2014-01-01", "2100-01-01"), ("2008 crash", "2007-07-01", "2009-03-11"), ("2020 covid", "2020-01-17", "2020-03-19")):
        ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
        if len(ix) < 20: continue
        cv = curve[ix] / curve[max(ix[0] - 1, t0)]; y = len(ix) / 245
        o[name] = ({"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1)} if y > 3 else {"return_pct": round((cv[-1] - 1) * 100, 1)}) | {"worst_drop_pct": round(float((cv / np.maximum.accumulate(np.r_[1, cv])[1:] - 1).min()) * 100, 1)}
    if trades:
        x = np.array([r for _, r in trades]); o["trades"] = len(x); o["avg_trade_pct"] = round(float(x.mean()) * 100, 2); o["win_pct"] = round(float((x > 0).mean()) * 100)
        o["trades_per_month"] = round(len(x) / ((D - t0) / 21), 1)
    return o
C_RES = {}
nkcv = np.ones(D); nkcv[t0:] = pk.values[t0:] / pk.values[t0]
C_RES["Nikkei ETF buy & hold (yen)"] = summ(nkcv, [])
for name, kw in [("dip bot, ideal (buy at close)", dict(entry="close", cost=0.001)), ("dip bot, realistic (next open, 0.2%/side)", dict(entry="open", cost=0.002)),
                 ("dip bot, ideal, idle money in cash always", dict(entry="close", cost=0.001, park=False))]:
    C_RES[name] = summ(*bot(**kw))
    for s in range(5): C_RES[f"{name} - RANDOM picks #{s+1}"] = summ(*bot(**kw, rand=s))
for k, v in C_RES.items():
    a = v.get("2001-2026", {}); print(f"C {k:62s} {a.get('per_year_pct')}%/yr worst {a.get('worst_drop_pct')}% | 01-13 {v.get('2001-2013', {}).get('per_year_pct')} 14-26 {v.get('2014-2026', {}).get('per_year_pct')} | trades {v.get('trades')} avg {v.get('avg_trade_pct')}% win {v.get('win_pct')}% /mo {v.get('trades_per_month')}", flush=True)
jpy = ydf("JPY=X")
RES["C_japan_stock_dip_bot"] = {"stocks_loaded": len(Aa), "list_size": len(CODES), "results": C_RES,
                                "yen_per_dollar_2001_vs_now": [round(float(jpy.c.asof(pd.Timestamp("2001-08-01"))), 1), round(float(jpy.c.iloc[-1]), 1)] if jpy is not None else None}
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, **RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
