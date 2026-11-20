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
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-06-01"]; px["aopen"] = px.open * px.adj_close / px.close
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOLM, AO = P("adj_close"), P("close"), P("volume"), P("aopen"); del px
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
def make_sig(dip=0.10, ma=200):
    return (M & (RAW[tick] >= 5) & (vr <= 2.0) & (Cs > Cs.rolling(ma).mean()) & (ex5 <= -dip)).values
S_C, S_M5, S_RK = Cs.values, Cs.rolling(5).mean().values, ex5.values
S_O = AO[tick].values
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
YO = {}; YL = {}
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); c = pd.Series(50 * np.exp(np.cumsum(rng.normal(0.0003, 0.013, D))), index=dates)
        YO[sym] = c * np.exp(rng.normal(0, 0.004, D)); return c
    err = None
    for a in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            q = j["indicators"]["quote"][0]; adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            ix = pd.to_datetime([time.strftime("%Y-%m-%d", time.gmtime(t)) for t in j["timestamp"]])
            df = pd.DataFrame({"a": adj, "c": q["close"], "o": q["open"], "l": q.get("low") or q["close"]}, index=ix); df = df[~df.index.duplicated()].sort_index()
            s = df.a.dropna(); o = (df.o * df.a / df.c).where((df.o > 0) & (df.c > 0)); YO[sym] = o; YL[sym] = (df.l * df.a / df.c).where((df.l > 0) & (df.c > 0))
            time.sleep(0.4); return s
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("Yahoo failed", sym, err, flush=True); return None
E = {s: x for s in ETFS if (x := yahoo(s)) is not None}
print("ETFs loaded", len(E), flush=True)
if len(E) < 25: raise SystemExit("too few ETFs")
Ce_raw = pd.DataFrame(E).reindex(dates); Ce = Ce_raw.ffill(); EN = list(Ce.columns); EI = {s: i for i, s in enumerate(EN)}
okE = Ce_raw.notna() & Ce_raw.notna().shift(-1, fill_value=False)
E_SIG = (okE & (Ce > Ce.rolling(200).mean()) & (Ce / Ce.shift(5) - 1 <= -0.05)).values
E_RK, E_C, E_M5 = (Ce / Ce.shift(5) - 1).values, Ce.values, Ce.rolling(5).mean().values
E_O = pd.DataFrame({s: YO.get(s, pd.Series(dtype=float)) for s in EN}).reindex(dates).values
E_L = pd.DataFrame({s: YL.get(s, pd.Series(dtype=float)) for s in EN}).reindex(dates).values   # daily lows (adjusted); NaN in DRY
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
_irx = yahoo("^IRX")                                                 # 3-month T-bill yield (%), what a cash sweep roughly earns
TBILL_R = np.zeros(D) if _irx is None else np.r_[0, (_irx.reindex(_irx.index.union(dates)).ffill(limit=10).reindex(dates) / 100 / 252).fillna(0).values[:-1]]
TBILL_R = np.clip(TBILL_R, 0, 0.08 / 252) if not DRY else np.full(D, 0.02 / 252)
BOND_OK = np.r_[False, (bond_lvl > bond_lvl.rolling(100, min_periods=100).mean()).fillna(False).values[:-1]]

# ---------------- Clear Leader daily returns (what the live bot parks in when SPY > 100-day avg)
CLR = spyr.copy(); CL_HELD = {}; CL_POS = np.array(["SPY"] * D, dtype=object)   # which ETF Clear Leader holds each day
if not DRY:
    g = {"__name__": "cl"}; exec(open("scripts/clear_leader_long.py").read(), g)
    rows = g["run"](crash=False)[0]; posm = {r["m"]: r["pos"] for r in rows}; mret = {r["m"]: r["r"] for r in rows}
    DAILY = {}
    for etf, alts in g["ASSETS"].items():
        r = pd.Series(np.nan, index=dates)
        for s_ in [etf] + alts:
            x = yahoo(s_)
            if x is not None: r = r.fillna(x.pct_change().reindex(dates))
        DAILY[etf] = r.values
    mon = dates.strftime("%Y-%m")
    for m in sorted(set(mon)):
        ix = np.where(mon == m)[0]
        if m not in posm: continue
        d = DAILY[posm[m]][ix]; CL_HELD[posm[m]] = CL_HELD.get(posm[m], 0) + 1; CL_POS[ix] = posm[m]
        CLR[ix] = d if np.isfinite(d).all() else (1 + mret[m]) ** (1 / len(ix)) - 1
    print("Clear Leader months held:", CL_HELD, flush=True)

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

# ---------------- earnings drift (8-K Item 2.02 reaction day, stock minus SPY), stored on the reaction day
RXC = np.full((D, J), np.nan)
try:
    _SEC = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sec_events_sic.json")))["tickers"]
    _ds = np.array([str(d)[:10] for d in dn]); _Mv = M.values
    for j, tk in enumerate(tick):
        for d, mi in (_SEC.get(tk) or {}).get("events", []):
            k = int(np.searchsorted(_ds, d))
            if k < D and _ds[k] == d and mi >= 570: k += 1
            if k < 1 or k >= D or not _Mv[k, j]: continue
            c0, c1 = S_C[k, j], S_C[k - 1, j]
            if c0 > 0 and c1 > 0: RXC[k, j] = c0 / c1 - 1 - (SP[k] / SP[k - 1] - 1)
except Exception as e: print("no earnings events:", e, flush=True)
def sim(etf=False, bond=False, vol=False, short=False, rebound=None, cs=0.0005, ce=0.0002, cp=0.0005, fill="close", park="spy", sig=None, mhs=5, grp=None, cap=None, drift=0, drift_mode="reserve", dth=0.05, dhold=60, cash_interest=False):
    SIGX = SIG if sig is None else sig
    PR = CLR if park == "cl" else spyr
    REB = {}
    if rebound:
        for a, p, l in rebound_events(rebound["drop"]):
            picks = rebound_picks(p, l, rebound["n"])
            if not picks: continue                                   # sector ETFs had no data yet (before 1999)
            for t in range(a, min(a + rebound["days"], D)): REB[t] = picks
    pos, eq, curve, trades, held_park = [], 1.0, np.ones(D), [], "CASH"
    LIM = 10 - (drift if drift_mode == "reserve" else 0)
    def buy(t, cand_s, cand_e, at_open, w, cand_d=()):
        nonlocal eq
        held = {(p["k"], p["j"]) for p in pos}
        for j in cand_d:                                             # drift first, in its own slots
            if sum(1 for q in pos if q["k"] == "D") >= drift: break
            if ("D", j) in held or ("S", j) in held: continue
            bp = S_O[t, j] if at_open else S_C[t, j]
            if not (np.isfinite(bp) and bp > 0 and np.isfinite(S_C[t, j])): continue
            room = 1 - sum(p["w"] for p in pos)
            if room < 0.02: break
            ww = min(w, room); pos.append({"k": "D", "j": j, "d": t, "px": bp, "w": ww, "open": at_open}); eq *= 1 - ww * cs; held.add(("D", j))
        for k, cands, Ca, Oa, cost in (("S", cand_s, S_C, S_O, cs), ("E", cand_e, E_C, E_O, ce)):
            for j in cands:
                if sum(1 for q in pos if q["k"] != "D") >= LIM: return
                if cap and k == "S" and grp[j] is not None and sum(1 for q in pos if q["k"] == "S" and grp[q["j"]] == grp[j]) >= cap: continue
                if (k, j) in held: continue
                bp = Oa[t, j] if at_open else Ca[t, j]
                if not (np.isfinite(bp) and bp > 0 and np.isfinite(Ca[t, j])): continue
                room = 1 - sum(p["w"] for p in pos)
                if room < 0.02: return
                ww = min(w, room); pos.append({"k": k, "j": j, "d": t, "px": bp, "w": ww, "open": at_open}); eq *= 1 - ww * cost; held.add((k, j))
    def cands(t):
        c = [j for j in np.flatnonzero(SIGX[t]) if not (short and np.isfinite(DTC[t, j]) and DTC[t, j] >= 5)]; c.sort(key=lambda j: S_RK[t, j])
        e = sorted([j for j in np.flatnonzero(E_SIG[t]) if np.isfinite(E_C[t, j])], key=lambda j: E_RK[t, j]) if etf else []
        d = sorted(np.flatnonzero(np.nan_to_num(RXC[t], nan=-1) >= dth), key=lambda j: -RXC[t, j]) if drift else []
        return c, e, d
    for t in range(t0, D):
        if fill == "open":                                        # yesterday's signals, bought at today's open
            cs_, ce_, cd_ = cands(t - 1); buy(t, cs_, ce_, True, 0.10 * (VSCALE[t - 1] if vol else 1.0), cd_)
        used = sum(p["w"] for p in pos); idle = max(0.0, 1 - used)
        want = (("REB:" + ",".join(REB[t])) if t in REB and park_on[t] else "SPY") if park_on[t] else ("IEF" if bond and BOND_OK[t] else "CASH")
        if want != held_park: eq *= 1 - idle * cp * ((held_park != "CASH") + (want != "CASH")); held_park = want
        r = 0.0
        for p in pos:
            Cx = E_C if p["k"] == "E" else S_C
            prev = p["px"] if (p["open"] and p["d"] == t) else Cx[t - 1, p["j"]]
            r += p["w"] * (Cx[t, p["j"]] / prev - 1)
        if held_park == "SPY": r += idle * PR[t]
        elif held_park == "IEF": r += idle * BOND_R[t]
        elif held_park == "CASH" and cash_interest: r += idle * TBILL_R[t]
        elif held_park.startswith("REB:"):
            ss = held_park[4:].split(","); r += idle * float(np.mean([Er[t, EI[s]] for s in ss]))
        eq *= 1 + r; keep = []
        for p in pos:
            Cx, Mx = (E_C, E_M5) if p["k"] == "E" else (S_C, S_M5)
            age = t - p["d"] + (1 if p["open"] else 0); mh = {"S": mhs, "E": 10, "D": dhold}[p["k"]]
            out = (age >= mh or not np.isfinite(Cx[t, p["j"]])) if p["k"] == "D" else (age >= 1 and (Cx[t, p["j"]] > Mx[t, p["j"]] or age >= mh))
            if out:
                c = ce if p["k"] == "E" else cs; eq *= 1 - p["w"] * c; trades.append((p["d"], p["k"], Cx[t, p["j"]] / p["px"] - 1 - 2 * c))
            else: keep.append(p)
        pos = keep
        if fill == "close":
            cs_, ce_, cd_ = cands(t); buy(t, cs_, ce_, False, 0.10 * (VSCALE[t] if vol else 1.0), cd_)
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
COMBOS = [("today's bot", {}), ("+ ETF dips (bot 5)", dict(etf=True)), ("+ bonds (bot 9)", dict(bond=True)), ("+ vol sizing", dict(vol=True)), ("+ short filter (bot 8)", dict(short=True)),
          ("ETF + bonds", dict(etf=True, bond=True)), ("ETF + bonds + short", dict(etf=True, bond=True, short=True)), ("ETF + bonds + vol", dict(etf=True, bond=True, vol=True)),
          ("ALL four", dict(etf=True, bond=True, vol=True, short=True))]
IDEAL, REAL = dict(fill="close", park="cl"), dict(fill="open", park="cl", cs=0.0015, ce=0.0005)
if __name__ == "__main__":
    V = [(f"IDEAL | {n}", {**kw, **IDEAL}) for n, kw in COMBOS] + [(f"REALISTIC | {n}", {**kw, **REAL}) for n, kw in COMBOS]
    V += [("SPY-parked ideal | today's bot", {}), ("SPY-parked ideal | ETF + bonds", dict(etf=True, bond=True))]
    for drop in (0.15, 0.20):
        for n in (2, 3):
            for days in (63, 126):
                V.append((f"IDEAL | + rebound: after {int(drop*100)}% drop, worst {n} sectors, {days} days", dict(rebound=dict(drop=drop, n=n, days=days), **IDEAL)))
    V += [("REALISTIC | ETF + bonds + rebound 15%/3/63", dict(etf=True, bond=True, rebound=dict(drop=0.15, n=3, days=63), **REAL)),
          ("STRESS realistic x2 costs | today's bot", dict(fill="open", park="cl", cs=0.003, ce=0.001, cp=0.001)),
          ("STRESS realistic x2 costs | ETF + bonds", dict(etf=True, bond=True, fill="open", park="cl", cs=0.003, ce=0.001, cp=0.001)),
          ("STRESS realistic x2 costs | ETF + bonds + short", dict(etf=True, bond=True, short=True, fill="open", park="cl", cs=0.003, ce=0.001, cp=0.001))]
    RES = {}
    for name, kw in V:
        RES[name] = summ(*sim(**kw)); a = RES[name]; g = lambda p, f="per_year_pct": a.get(p, {}).get(f)
        print(f"{name:58s} {g('1999-2026')}%/yr worst {g('1999-2026','worst_drop_pct')} | 99-12 {g('1999-2012')} 13-26 {g('2013-2026')} 18-26 {g('2018-2026 (short data)')} | dotcom {g('dot-com 2000-02','return_pct')} 08 {g('2008 crash','return_pct')} cov {g('2020 covid','return_pct')} 22 {g('2022 bear','return_pct')} | reb09 {g('2009 rebound','return_pct')} reb20 {g('2020 rebound','return_pct')} | {a['trades_per_month']}/mo", flush=True)
    base = RES["IDEAL | today's bot"]
    for name, kw in [("check: rebound that never triggers", dict(rebound=dict(drop=0.99, n=3, days=63), **IDEAL))]:
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
