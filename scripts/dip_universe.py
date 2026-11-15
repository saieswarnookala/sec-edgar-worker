"""Dip bot on a wider universe + small rule changes (Nov 15 2026). Research only, not financial advice.
UNIVERSE=us_all: every US common stock Alpaca has daily bars for (active AND delisted), 2016-2026. Each day stocks are
  sized by 20-day average dollar volume among those priced >= $5: top 500 = "large", 501-1500 = "mid", 1501-3000 = "small".
  (No point-in-time index lists outside the S&P 500, so size comes from trading volume; ETFs/funds removed by name.)
UNIVERSE=sp500: point-in-time S&P 500 members 1999-2026 (incl. companies that later left or failed).
Base rule = the live dip bot: 5-day return >= 10% worse than SPY, above the 200-day average, volume over the drop <= 2x
normal, price >= $5, at least $5M traded a day; biggest drop first; buy at the close; sell when the close is back above
the 5-day average (after >= 1 day) or after 5 days. 10 slots x 10%. Idle money in SPY when SPY is above its 100-day
average, else cash. Cost per side by liquidity: >= $100M/day 0.05%, $20-100M 0.10%, below 0.20%.
Then one change at a time: trend average 100/150/250/none, dip 8/12/15%, lookback 3/7/10 days, volume cap 1.5/3/none,
sell average 3/10 days, max hold 3/7/10, slots 15/20 (smaller each)."""
import os, json, time, urllib.request, urllib.parse, urllib.error, re
import numpy as np, pandas as pd

U = os.environ.get("UNIVERSE", "us_all"); LIMIT = int(os.environ.get("LIMIT", "0"))
OUT = f"data/dip_universe_{U}{'_smoke' if LIMIT else ''}.json"

if U == "us_all":
    H = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
    RATE = float(os.environ.get("RATE_PER_MIN", "150")); _last = [0.0]
    def get(url):
        for i in range(10):
            w = 60.0 / RATE - (time.time() - _last[0])
            if w > 0: time.sleep(w)
            _last[0] = time.time()
            try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    ra = e.headers.get("Retry-After"); time.sleep(float(ra) if ra and ra.replace(".", "").isdigit() else min(120, 15 * (i + 1))); continue
                if e.code in (400, 403, 404, 422): print("HTTP", e.code, e.read()[:200], flush=True); return None
                time.sleep(5 * (i + 1))
            except Exception: time.sleep(3 * (i + 1))
        return None
    FUNDWORDS = re.compile(r"\b(ETF|ETN|FUND|TRUST|SHARES|PROSHARES|DIREXION|ISHARES|SPDR|INVESCO|VANGUARD|WISDOMTREE|GLOBAL X|ULTRA|LEVERAGED|INVERSE|BULL|BEAR|2X|3X|NOTES?|WARRANTS?|UNITS?|RIGHTS?|PREFERRED|DEPOSITARY)\b", re.I)
    assets = {}
    for st in ("active", "inactive"):
        for a in get("https://paper-api.alpaca.markets/v2/assets?" + urllib.parse.urlencode({"status": st, "asset_class": "us_equity"})) or []:
            s = a["symbol"]
            if a.get("exchange") in ("NYSE", "NASDAQ", "AMEX", "ARCA", "BATS") and re.fullmatch(r"[A-Z]{1,5}", s) and not FUNDWORDS.search(a.get("name") or ""):
                assets[s] = st
    SPCHECK = os.environ.get("SP_CHECK") == "1"
    if SPCHECK:
        mf = "/tmp/membership_intervals.parquet"
        if not os.path.exists(mf): urllib.request.urlretrieve("https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/membership_intervals.parquet", mf)
        memi = pd.read_parquet(mf); memi["start"] = pd.to_datetime(memi.start); memi["end"] = pd.to_datetime(memi.end)
        memi = memi[(memi.end.isna()) | (memi.end >= "2016-01-01")]
        assets = {k: v for k, v in assets.items() if k in set(memi.ticker)}
        OUT = "data/dip_universe_us_all_spcheck.json"
    syms = sorted(assets)
    if LIMIT: syms = [s for s in syms if s in ("SPY",)] + syms[:LIMIT]
    if "SPY" not in syms: syms = ["SPY"] + syms
    print("assets kept", len(syms), "inactive", sum(v == "inactive" for v in assets.values()), flush=True)
    end = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
    # Cached in Cloudflare R2 (scripts/r2cache.py): reuse saved daily bars and download only recent days. Prices adjusted
    # for dividends/splits change after each payout, so any stock whose overlapping closes differ is re-downloaded in full.
    import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import r2cache
    KEY = "daily/us_all_adj_all.json.gz"
    cache = r2cache.load(KEY) or {}
    allrows = {s_: {d: tuple(v) for d, v in dd.items()} for s_, dd in cache.get("rows", {}).items()}
    def fetch(batch, start, into):
        p = {"symbols": ",".join(batch), "timeframe": "1Day", "start": start, "end": end, "adjustment": "all", "feed": "sip", "limit": "10000"}
        while True:
            js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p))
            if js is None:
                if len(batch) > 1: h = len(batch) // 2; fetch(batch[:h], start, into); fetch(batch[h:], start, into)
                return
            for s_, bl in (js.get("bars") or {}).items():
                d = into.setdefault(s_, {})
                for b in bl: d[b["t"][:10]] = (b["c"], b["v"])
            if not js.get("next_page_token"): return
            p["page_token"] = js["next_page_token"]
    have = [s_ for s_ in syms if s_ in allrows and allrows[s_]]
    full = [s_ for s_ in syms if s_ not in allrows or not allrows[s_]]
    changed = False
    if have:
        last = max(max(allrows[s_]) for s_ in have)
        start = (pd.Timestamp(last) - pd.Timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z")
        recent = {}
        for i in range(0, len(have), 100): fetch(have[i:i + 100], start, recent)
        for s_ in have:
            nd = recent.get(s_, {}); od = allrows[s_]
            common = [d for d in nd if d in od]
            if any(abs(nd[d][0] / od[d][0] - 1) > 0.003 for d in common if od[d][0]): full.append(s_)      # adjusted history changed
            elif nd: changed |= any(d not in od for d in nd); od.update(nd)
        print("r2cache: cached", len(have), "stocks; re-downloading", len(full), "(new or price history changed)", flush=True)
    if full:
        fresh = {}
        for i in range(0, len(full), 100):
            fetch(full[i:i + 100], "2015-01-01", fresh)
            if i % 1000 == 0: print("fetched", i, "of", len(full), flush=True)
        allrows.update(fresh); changed = True
    if changed: r2cache.save(KEY, {"adjustment": "all", "saved": end, "rows": {s_: {d: list(v) for d, v in dd.items()} for s_, dd in allrows.items()}})
    rows = {s_: allrows[s_] for s_ in syms if s_ in allrows and allrows[s_]}
    print("symbols with data", len(rows), "of", len(syms), flush=True)
    if "SPY" not in rows: raise SystemExit("SPY has no data")
    if len(rows) < 0.5 * len(syms): raise SystemExit(f"only {len(rows)} of {len(syms)} symbols returned data, stopping")
    dates = pd.DatetimeIndex(sorted(rows["SPY"])); ds = [d.strftime("%Y-%m-%d") for d in dates]
    tick = [s for s in rows if s != "SPY" and len(rows[s]) >= 250]
    C = np.array([[rows[s].get(d, (np.nan, np.nan))[0] for s in tick] for d in ds], dtype=np.float32).astype(float)
    V = np.array([[rows[s].get(d, (np.nan, np.nan))[1] for s in tick] for d in ds], dtype=np.float32).astype(float)
    SP = np.array([rows["SPY"][d][0] for d in ds]); del rows
    MEMB = ~np.isnan(C); START = "2016-01-01"
    if SPCHECK:
        mm = np.zeros_like(MEMB)
        for _, m in memi.iterrows():
            if m.ticker in tick:
                j = tick.index(m.ticker); a = dates.searchsorted(m.start); b = dates.searchsorted(m.end) if pd.notna(m.end) else len(dates)
                mm[a:b, j] = True
        MEMB &= mm
    HALVES = (("2016-2020", "2016-01-01", "2021-01-01"), ("2021-2026", "2021-01-01", "2100-01-01"))
else:
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f):
            for i in range(6):
                try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
                except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-06-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
    dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
    Pv = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
    A, RAWC, VV = Pv("adj_close"), Pv("close"), Pv("volume"); del px
    tick = [t for t in ALLT if t != "SPY"]
    Mdf = pd.DataFrame(False, index=dates, columns=tick)
    for _, m in mem.iterrows():
        if m.ticker in Mdf.columns:
            e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
            Mdf.loc[(Mdf.index >= m.start) & (Mdf.index < e), m.ticker] = True
    C = A[tick].values; V = (VV[tick] * RAWC[tick] / A[tick]).values   # share volume, split-consistent with adjusted price
    SP = A["SPY"].ffill().values; MEMB = Mdf.values & ~np.isnan(C); START = "1999-01-01"
    HALVES = (("1999-2012", "1999-01-01", "2013-01-01"), ("2013-2026", "2013-01-01", "2100-01-01"))
D, N = C.shape; dn = dates.values
print(U, "days", D, "stocks", N, dates[0].date(), dates[-1].date(), flush=True)
Cf = pd.DataFrame(C).ffill().values
with np.errstate(all="ignore"):
    dvol = pd.DataFrame(C * V).rolling(20, min_periods=15).mean().values
    elig = MEMB & (C >= 5) & (dvol >= 5e6)
    rnk = pd.DataFrame(np.where((C >= 5) & MEMB, dvol, np.nan)).rank(axis=1, ascending=False).values
    size = np.where(rnk <= 500, 0, np.where(rnk <= 1500, 1, np.where(rnk <= 3000, 2, 3)))
    cost = np.where(dvol >= 1e8, 0.0005, np.where(dvol >= 2e7, 0.0010, 0.0020))
    spyr = np.r_[0, SP[1:] / SP[:-1] - 1]
    park_on = np.r_[False, (pd.Series(SP) > pd.Series(SP).rolling(100).mean()).values[:-1]]
    MA = {k: pd.DataFrame(C).rolling(k, min_periods=int(k * 0.75)).mean().values for k in (3, 5, 10, 100, 150, 200, 250)}
    RET = {k: C / np.vstack([np.full((k, N), np.nan), C[:-k]]) - 1 for k in (3, 5, 7, 10)}
    SPR = {k: SP / np.r_[np.full(k, np.nan), SP[:-k]] - 1 for k in (3, 5, 7, 10)}
    VR = {k: pd.DataFrame(V).rolling(k).mean().values / pd.DataFrame(V).shift(k).rolling(50).mean().values for k in (3, 5, 7, 10)}

def signal(trend=200, dip=0.10, look=5, vcap=2.0, sizes=(0, 1)):
    ex = RET[look] - SPR[look][:, None]
    s = elig & (ex <= -dip) & np.isin(size, sizes)
    if trend: s &= C > MA[trend]
    if vcap: s &= VR[look] <= vcap
    return s, ex

t0 = int(np.searchsorted(dn, np.datetime64(START)))
def sim(sig, rk, exit_ma=5, max_hold=5, slots=10, w=0.10):
    pos, eq, curve, trades = [], 1.0, np.ones(D), []
    for t in range(t0, D):
        r = 0.0
        for p in pos: r += w * (Cf[t, p[0]] / Cf[t - 1, p[0]] - 1)
        if park_on[t]: r += (1 - w * len(pos)) * spyr[t]
        eq *= 1 + r; keep = []
        for p in pos:
            j, d0, px0, c = p; age = t - d0
            gone = np.isnan(C[t, j])
            if age >= 1 and (gone or Cf[t, j] > MA[exit_ma][t, j] or age >= max_hold):
                eq *= 1 - w * 2 * c; trades.append((d0, Cf[t, j] / px0 - 1 - 2 * c))
            else: keep.append(p)
        pos = keep
        free = slots - len(pos)
        if free > 0:
            held = {p[0] for p in pos}
            cand = [j for j in np.flatnonzero(sig[t]) if j not in held]
            cand.sort(key=lambda j: rk[t, j])
            for j in cand[:free]: pos.append((j, t, C[t, j], cost[t, j]))
        curve[t] = eq
    res = {}
    for name, a, b in (("full", START, "2100-01-01"),) + HALVES:
        idx = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
        c = curve[idx] / curve[idx[0]]; yrs = len(idx) / 252; s = SP[idx] / SP[idx[0]]
        tr = [x[1] for x in trades if a <= str(dn[x[0]])[:10] < b]
        res[name] = {"per_year_pct": round((c[-1] ** (1 / yrs) - 1) * 100, 1), "worst_drop_pct": round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1),
                     "spy_per_year_pct": round((s[-1] ** (1 / yrs) - 1) * 100, 1), "trades_per_month": round(len(tr) / (yrs * 12), 1),
                     "win_pct": round(float(np.mean([x > 0 for x in tr])) * 100, 1) if tr else None,
                     "avg_trade_pct": round(float(np.mean(tr)) * 100, 2) if tr else None}
    return res

def counts(sig):
    m = pd.Series(sig[t0:].sum(1), index=dates[t0:]).resample("ME").sum()
    u = pd.DataFrame(sig[t0:], index=dates[t0:]).resample("ME").max().sum(1)
    return {"signals_per_month_avg": round(float(m.mean()), 1), "median": float(m.median()), "busiest_month": int(m.max()), "quietest_month": int(m.min()),
            "different_stocks_per_month_avg": round(float(u.mean()), 1), "months_with_zero": int((m == 0).sum())}

out = {"note": __doc__, "universe": U, "period": f"{dates[t0].date()} to {dates[-1].date()}", "stocks": N}
UNIS = {"large": (0,), "mid": (1,), "small": (2,), "large+mid": (0, 1), "large+mid+small": (0, 1, 2)} if U == "us_all" else {"S&P 500 members": (0, 1, 2, 3)}
if U == "us_all" and os.environ.get("SP_CHECK") == "1": UNIS = {"S&P 500 members (Alpaca data)": (0, 1, 2, 3)}
out["universes"] = {}
for un, sz in UNIS.items():
    s, ex = signal(sizes=sz); out["universes"][un] = {"counts": counts(s), "bot": sim(s, ex)}
    print("UNIVERSE", un, out["universes"][un]["counts"], out["universes"][un]["bot"]["full"], flush=True)
base_sizes = (0, 1) if U == "us_all" and os.environ.get("SP_CHECK") != "1" else (0, 1, 2, 3)
if os.environ.get("SP_CHECK") == "1": VARS_ONLY_BASE = True
VARS = [("base (live bot rules)", {}, {})] + \
       [(f"trend: {k}-day avg", {"trend": k}, {}) for k in (100, 150, 250)] + [("trend: none", {"trend": 0}, {})] + \
       [(f"dip: {int(d * 100)}%", {"dip": d}, {}) for d in (0.08, 0.12, 0.15)] + \
       [(f"lookback: {k} days", {"look": k}, {}) for k in (3, 7, 10)] + \
       [(f"volume cap: {v}x", {"vcap": v}, {}) for v in (1.5, 3.0)] + [("volume cap: none", {"vcap": 0}, {})] + \
       [(f"sell above {k}-day avg", {}, {"exit_ma": k}) for k in (3, 10)] + \
       [(f"max hold {k} days", {}, {"max_hold": k}) for k in (3, 7, 10)] + \
       [("15 slots x 6.7%", {}, {"slots": 15, "w": 1 / 15}), ("20 slots x 5%", {}, {"slots": 20, "w": 0.05})]
out["variants_universe"] = "large+mid" if U == "us_all" else "S&P 500 members"
out["variants"] = {}
for name, sk, mk in (VARS[:1] if os.environ.get("SP_CHECK") == "1" else VARS):
    s, ex = signal(**{"sizes": base_sizes, **sk}); r = sim(s, ex, **mk); r["counts"] = counts(s)
    out["variants"][name] = r
    print("VAR", name, "|", r["full"], "|", {h[0]: r[h[0]]["per_year_pct"] for h in HALVES}, "| sig/mo", r["counts"]["signals_per_month_avg"], flush=True)
json.dump(out, open(OUT, "w"), indent=1)
