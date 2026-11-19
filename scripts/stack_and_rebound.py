"""Stack test + crash-rebound sleeve (Nov 18 2026). Research only, not financial advice.
Base = today's Robinhood bot: point-in-time S&P 500, price >= $5, above 200-day avg, 5-day return >= 10% worse than SPY, volume over
the drop <= 2x; 10 slots x 10%, buy at the close, sell when close > 5-day avg (after >= 1 day) or after 5 days. Idle money: SPY
(stand-in for Clear Leader) when SPY > its 100-day avg (yesterday), else cash. Costs 0.05%/side stocks, 0.02% ETFs, 0.05% parking switches.
Add-ons, alone and stacked:
  ETF   = bot 5: 29 index/sector/country ETFs down 5%+ in 5 days and above their 200-day fill free slots (max hold 10 days)
  BOND  = bot 9: on cash days hold IEF (VFITX before 2002) if it is above its own 100-day avg
  VOL   = vol bot: buy size 10% x (0.5 .. 1.5) by where SPY's 20-day volatility ranks in the last year (jumpy = bigger)
  SHORT = bot 8: skip dips with FINRA days-to-cover >= 5 (data only from 2018; before that nothing is skipped)
  REBOUND (new) = after SPY fell 15%+ from its high and then closes back above its 100-day avg, idle money goes for 63 trading days
            into the 3 sector ETFs that fell most from SPY's high to its bottom (instead of SPY/Clear Leader).
Checks: every add-on switched off must equal the base exactly; DRY=1 fake ETF/bond data, no short data (code test)."""
import os, sys, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DRY = os.environ.get("DRY", ""); OUT = "data/stack_and_rebound.json" if not DRY else "/tmp/stack_dry.json"
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOLM = P("adj_close"), P("close"), P("volume"); del px
tick = [t for t in ALLT if t != "SPY"]; D, J = len(dates), len(tick); TI = {t: j for j, t in enumerate(tick)}
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
valid = A[tick].notna(); M &= valid & valid.shift(-1, fill_value=False)
Cs = A[tick].ffill(); spy = A["SPY"].ffill()
ex5 = (Cs / Cs.shift(5) - 1).sub(spy / spy.shift(5) - 1, axis=0)
vr = VOLM[tick].rolling(5).mean() / VOLM[tick].shift(5).rolling(50).mean()
SIG = (M & (RAW[tick] >= 5) & (vr <= 2.0) & (Cs > Cs.rolling(200).mean()) & (ex5 <= -0.10)).values
S_C, S_M5, S_RK = Cs.values, Cs.rolling(5).mean().values, ex5.values
SP = spy.values; spyr = np.r_[0, SP[1:] / SP[:-1] - 1]
dn = dates.values; t0 = int(np.searchsorted(dn, np.datetime64("1999-01-04")))
park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]
# vol scale (decided on yesterday's data)
vol20 = spy.pct_change().rolling(20).std()
rank = vol20.rolling(252, min_periods=200).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
VSCALE = np.r_[1.0, (0.5 + rank.fillna(0.5)).values[:-1]]

# ---------------- ETFs + bond
ETFS = ["SPY", "QQQ", "IWM", "DIA", "MDY", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC",
        "EFA", "EEM", "EWJ", "EWG", "EWU", "EWC", "EWA", "EWZ", "EWH", "EWT", "EWY", "INDA", "FXI"]
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); return pd.Series(50 * np.exp(np.cumsum(rng.normal(0.0003, 0.013, D))), index=dates)
    err = None
    for a in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or j["indicators"]["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime([time.strftime("%Y-%m-%d", time.gmtime(t)) for t in j["timestamp"]])).dropna()
            time.sleep(0.4); return s[~s.index.duplicated()].sort_index()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("Yahoo failed", sym, err, flush=True); return None
E = {s: x for s in ETFS if (x := yahoo(s)) is not None}
print("ETFs loaded", len(E), flush=True)
if len(E) < 25: raise SystemExit("too few ETFs")
Ce_raw = pd.DataFrame(E).reindex(dates); Ce = Ce_raw.ffill(); EN = list(Ce.columns); EI = {s: i for i, s in enumerate(EN)}
okE = Ce_raw.notna() & Ce_raw.notna().shift(-1, fill_value=False)
E_SIG = (okE & (Ce > Ce.rolling(200).mean()) & (Ce / Ce.shift(5) - 1 <= -0.05)).values
E_RK, E_C, E_M5 = (Ce / Ce.shift(5) - 1).values, Ce.values, Ce.rolling(5).mean().values
Er = np.nan_to_num(np.vstack([np.zeros(len(EN)), E_C[1:] / E_C[:-1] - 1]))
def chain(*syms):
    r = pd.Series(np.nan, index=dates)
    for s in syms:
        x = yahoo(s)
        if x is None: continue
        lv = x.reindex(x.index.union(dates)).ffill(limit=5).reindex(dates); r = r.where(r.notna(), lv.pct_change(fill_method=None))
    return r
bond_r = chain("IEF", "VFITX"); bond_lvl = (1 + bond_r.fillna(0)).cumprod().where(bond_r.notna().cumsum() > 0)
BOND_R = bond_r.fillna(0).values
BOND_OK = np.r_[False, (bond_lvl > bond_lvl.rolling(100, min_periods=100).mean()).fillna(False).values[:-1]]

# ---------------- short interest (bot 8) from the R2 cache built by short_dips.py
DTC = np.full((D, J), np.nan); SHORT_FROM = None
if not DRY:
    try:
        import r2cache
        idx = r2cache.load("finra/si_index.json.gz") or {"found": []}
        for d in sorted(idx["found"]):
            e = int(np.searchsorted(dn, np.datetime64(pd.Timestamp(d) + pd.Timedelta(days=12))))
            if e >= D: continue
            r = r2cache.load(f"finra/si/{d}.json.gz")
            if not r: continue
            for s, dtc in zip(r["sym"], r["dtc"]):
                j = TI.get(s.replace(".", "-").replace("/", "-"))
                if j is not None and dtc is not None and dtc >= 0: DTC[e, j] = dtc
        DTC = pd.DataFrame(DTC).ffill(limit=15).values
        have = np.isfinite(DTC).any(axis=1); SHORT_FROM = str(dn[int(np.argmax(have))])[:10] if have.any() else None
        print("short interest reports:", len(idx["found"]), "active from", SHORT_FROM, flush=True)
    except Exception as e: print("short data not available:", str(e)[:200], flush=True)

# ---------------- rebound events: SPY >= X below its high, then first close back above the 100-day avg
def rebound_events(drop=0.15):
    ev, peak, peak_t, low, low_t, armed = [], SP[0], 0, None, None, False
    above = np.r_[False, (spy > spy.rolling(100).mean()).values[1:]]
    for t in range(1, D):
        if SP[t] >= peak: peak, peak_t, low, low_t, armed = SP[t], t, None, None, False; continue
        if low is None or SP[t] < low: low, low_t = SP[t], t
        if low / peak - 1 <= -drop: armed = True
        if armed and above[t] and not above[t - 1] and t > low_t:
            ev.append((t + 1, peak_t, low_t)); armed = False; peak, peak_t = SP[t], t; low = None     # new cycle needs a new 15% drop
    return [(a, p, l) for a, p, l in ev if a < D]
def rebound_picks(p, l, n=3):
    secs = [s for s in SECTORS if s in EI and np.isfinite(E_C[p, EI[s]]) and np.isfinite(E_C[l, EI[s]])]
    return sorted(secs, key=lambda s: E_C[l, EI[s]] / E_C[p, EI[s]] - 1)[:n]

def sim(etf=False, bond=False, vol=False, short=False, rebound=None, cs=0.0005, ce=0.0002, cp=0.0005):
    REB = {}
    if rebound:
        for a, p, l in rebound_events(rebound["drop"]):
            picks = rebound_picks(p, l, rebound["n"])
            if not picks: continue                                   # sector ETFs had no data yet (before 1999)
            for t in range(a, min(a + rebound["days"], D)): REB[t] = picks
    pos, eq, curve, trades, held_park = [], 1.0, np.ones(D), [], "CASH"
    for t in range(t0, D):
        used = sum(p["w"] for p in pos); idle = max(0.0, 1 - used)
        want = (("REB:" + ",".join(REB[t])) if t in REB and park_on[t] else "SPY") if park_on[t] else ("IEF" if bond and BOND_OK[t] else "CASH")
        if want != held_park: eq *= 1 - idle * cp * ((held_park != "CASH") + (want != "CASH")); held_park = want
        r = 0.0
        for p in pos:
            Cx = S_C if p["k"] == "S" else E_C
            r += p["w"] * (Cx[t, p["j"]] / Cx[t - 1, p["j"]] - 1)
        if held_park == "SPY": r += idle * spyr[t]
        elif held_park == "IEF": r += idle * BOND_R[t]
        elif held_park.startswith("REB:"):
            ss = held_park[4:].split(","); r += idle * float(np.mean([Er[t, EI[s]] for s in ss]))
        eq *= 1 + r; keep = []
        for p in pos:
            Cx, Mx = (S_C, S_M5) if p["k"] == "S" else (E_C, E_M5)
            age = t - p["d"]; mh = 5 if p["k"] == "S" else 10
            if age >= 1 and (Cx[t, p["j"]] > Mx[t, p["j"]] or age >= mh):
                c = cs if p["k"] == "S" else ce; eq *= 1 - p["w"] * c; trades.append((p["d"], p["k"], Cx[t, p["j"]] / p["px"] - 1 - 2 * c))
            else: keep.append(p)
        pos = keep; held = {(p["k"], p["j"]) for p in pos}
        w = 0.10 * (VSCALE[t] if vol else 1.0)
        free = 10 - len(pos)
        c = [j for j in np.flatnonzero(SIG[t]) if ("S", j) not in held and not (short and np.isfinite(DTC[t, j]) and DTC[t, j] >= 5)]
        c.sort(key=lambda j: S_RK[t, j])
        for j in c[:max(0, free)]:
            room = 1 - sum(p["w"] for p in pos)
            if room < 0.02: break
            ww = min(w, room); pos.append({"k": "S", "j": j, "d": t, "px": S_C[t, j], "w": ww}); eq *= 1 - ww * cs
        free = 10 - len(pos)
        if etf and free > 0:
            ce_ = [j for j in np.flatnonzero(E_SIG[t]) if ("E", j) not in held and np.isfinite(E_C[t, j])]; ce_.sort(key=lambda j: E_RK[t, j])
            for j in ce_[:free]:
                room = 1 - sum(p["w"] for p in pos)
                if room < 0.02: break
                ww = min(w, room); pos.append({"k": "E", "j": j, "d": t, "px": E_C[t, j], "w": ww}); eq *= 1 - ww * ce
        curve[t] = eq
    return curve, trades
PER = [("1999-2026", "1999-01-01", "2100"), ("1999-2012", "1999-01-01", "2013-01-01"), ("2013-2026", "2013-01-01", "2100"), ("2018-2026 (short data)", "2018-01-02", "2100"),
       ("dot-com 2000-02", "2000-03-24", "2002-10-10"), ("2008 crash", "2007-10-09", "2009-03-10"), ("2020 covid", "2020-02-19", "2020-03-24"), ("2022 bear", "2022-01-03", "2022-10-13"),
       ("2009 rebound", "2009-03-10", "2010-03-10"), ("2020 rebound", "2020-03-24", "2021-03-24")]
def summ(curve, trades):
    out = {}
    for name, a, b in PER:
        ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b if b != "2100" else "2100-01-01")) & (np.arange(D) >= t0))
        if len(ix) < 15: continue
        cv = curve[ix] / curve[max(ix[0] - 1, t0)]; y = len(ix) / 252
        out[name] = ({"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1)} if y > 3 else {"return_pct": round((cv[-1] - 1) * 100, 1)}) | {"worst_drop_pct": round(float((cv / np.maximum.accumulate(np.r_[1, cv])[1:] - 1).min()) * 100, 1)}
    yrs = (D - t0) / 252
    out["trades_per_month"] = round(len(trades) / (yrs * 12), 1); out["avg_trade_pct"] = round(float(np.mean([x[2] for x in trades])) * 100, 2) if trades else None
    return out
V = [("today's bot", {}), ("+ ETF dips (bot 5)", dict(etf=True)), ("+ bonds (bot 9)", dict(bond=True)), ("+ vol sizing", dict(vol=True)), ("+ short filter (bot 8)", dict(short=True)),
     ("ETF + bonds", dict(etf=True, bond=True)), ("ETF + bonds + vol", dict(etf=True, bond=True, vol=True)), ("ETF + bonds + short", dict(etf=True, bond=True, short=True)),
     ("ALL four", dict(etf=True, bond=True, vol=True, short=True))]
for drop in (0.15, 0.20):
    for n in (2, 3):
        for days in (63, 126):
            V.append((f"+ rebound: after {int(drop*100)}% drop, worst {n} sectors, {days} days", dict(rebound=dict(drop=drop, n=n, days=days))))
V += [("ALL four + rebound 15%/3/63", dict(etf=True, bond=True, vol=True, short=True, rebound=dict(drop=0.15, n=3, days=63))),
      ("STRESS today's bot (3x costs)", dict(cs=0.0015, ce=0.0006, cp=0.0015)), ("STRESS ETF + bonds (3x costs)", dict(etf=True, bond=True, cs=0.0015, ce=0.0006, cp=0.0015)),
      ("STRESS ALL four (3x costs)", dict(etf=True, bond=True, vol=True, short=True, cs=0.0015, ce=0.0006, cp=0.0015))]
RES = {}
for name, kw in V:
    RES[name] = summ(*sim(**kw)); a = RES[name]; g = lambda p, f="per_year_pct": a.get(p, {}).get(f)
    print(f"{name:58s} {g('1999-2026')}%/yr worst {g('1999-2026','worst_drop_pct')} | 99-12 {g('1999-2012')} 13-26 {g('2013-2026')} 18-26 {g('2018-2026 (short data)')} | dotcom {g('dot-com 2000-02','return_pct')} 08 {g('2008 crash','return_pct')} cov {g('2020 covid','return_pct')} 22 {g('2022 bear','return_pct')} | reb09 {g('2009 rebound','return_pct')} reb20 {g('2020 rebound','return_pct')} | {a['trades_per_month']}/mo", flush=True)
base = RES["today's bot"]
for name, kw in [("check: rebound that never triggers", dict(rebound=dict(drop=0.99, n=3, days=63))), ("check: vol scale fixed at 1", {})]:
    assert summ(*sim(**kw))["1999-2026"] == base["1999-2026"], name
print("checks ok: add-ons switched off = base", flush=True)
EV = [{"starts": str(dn[a])[:10], "spy_high": str(dn[p])[:10], "spy_bottom": str(dn[l])[:10], "spy_drop_pct": round((SP[l] / SP[p] - 1) * 100, 1),
       "sectors_15pct_3": rebound_picks(p, l, 3),
       "sectors_next_63d_pct": round(float(np.mean([E_C[min(a + 63, D - 1), EI[s]] / E_C[a - 1, EI[s]] - 1 for s in rebound_picks(p, l, 3)])) * 100, 1) if rebound_picks(p, l, 3) else None,
       "spy_next_63d_pct": round((SP[min(a + 63, D - 1)] / SP[a - 1] - 1) * 100, 1)} for a, p, l in rebound_events(0.15) if dn[a] >= dn[t0]]
for e in EV: print("REBOUND", json.dumps(e), flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "short_data_from": SHORT_FROM, "rebound_events": EV, "results": RES},
          open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
