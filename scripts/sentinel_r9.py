"""Sentinel research round 9 (Nov 28 2026): five ways to improve the dip bot. Research only, not financial advice.
Engine: scripts/stack_and_rebound.py = dip bot v3.0 (point-in-time S&P 500, 1999-2026), live-like (buy at the close, low costs) and
realistic (yesterday's signal bought at today's open, 0.15%/0.05% costs). GROUP (env) picks the test:
  park   - "rally mode": when spare cash sits in stocks (Clear Leader/SPY) vs bonds: SPY trend filter 20/50/100/200 days, faster re-entry, always/never
  picks  - better dip picks: prior strength filters (12-month momentum, near 52-week high, low volatility), strength-based sizing
  brake  - market brake: skip or half-size new stock dips when SPY < 200-day, SPY volatility high, few stocks above 200-day, SPY deep below its high
  earn   - earnings/news filter: skip dips with an SEC 8-K earnings release (item 2.02, item 12 before Aug 2004) in the 5-day dip window,
           stock-alone vs sector-wide dips (SEC industry peers), 1999-2026
  engine - second engine: trend-following ETF engines (time-series momentum, dual momentum, Clear Leader) and mixes with the dip bot
Luck check: every filter is compared with 6 random filters that skip the same share of signals (placebo).
Output: data/r9_<group>.json (+ data/r9_series.csv.gz for engine). DRY=1: fake data."""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
G = os.environ.get("GROUP", "park")
import stack_and_rebound as S
OUT = f"data/r9_{G}.json" if not S.DRY else f"/tmp/r9_{G}_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003, etf=True, bond=True)
REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005, etf=True, bond=True)
dn, t0, tick = S.dn, S.t0, S.tick
Cs, spy, M = S.Cs, S.spy, S.M
T_START = time.time()

def sharpe(curve):
    c = pd.Series(curve[t0:], index=S.dates[t0:]); m = c.resample("ME").last().pct_change().dropna()
    return round(float(m.mean() / m.std() * np.sqrt(12)), 2) if m.std() > 0 else None
def run(kw=LIVE, **extra):
    c, tr = S.sim(**{**kw, **extra}); s = S.summ(c, tr); rs = np.array([x[2] for x in tr]) if tr else np.zeros(1)
    keep = ("1999-2026", "1999-2012", "2013-2026", "dot-com 2000-02", "2008 crash", "2020 covid", "2022 bear", "2009 rebound", "2020 rebound")
    out = {k: s[k] for k in keep if k in s}
    out.update({"sharpe": sharpe(c), "trades": len(tr), "win_pct": round(float((rs > 0).mean()) * 100, 1), "avg_trade_pct": round(float(rs.mean()) * 100, 2)})
    return out, c
def cagr(row): return row["1999-2026"]["per_year_pct"]
RES = {"note": __doc__, "group": G}
def log(name, row): print(f"{name:70s} {cagr(row):6.1f}%  worst {row['1999-2026']['worst_drop_pct']:6.1f}%  sharpe {row['sharpe']}  trades {row['trades']}  ({int(time.time()-T_START)}s)", flush=True)

def with_placebo(name, sig=None, wmul=None, k=6, seed=1):
    """run a signal filter live + realistic, plus k random filters skipping the same share of signals (live)"""
    row = {}
    for lab, kw in (("live", LIVE), ("realistic", REAL)):
        r, _ = run(kw, sig=sig, wmul=wmul); row[lab] = r; log(f"{name} [{lab}]", r)
    if sig is not None:
        base_n = S.SIG[t0:].sum(); kept = sig[t0:].sum(); q = 1 - kept / max(base_n, 1); row["signals_kept_pct"] = round(float(kept / base_n) * 100, 1)
        if 0.01 < q < 0.99:
            rng = np.random.default_rng(seed); pl = []
            for i in range(k):
                rs = S.SIG & (rng.random(S.SIG.shape) >= q); r, _ = run(LIVE, sig=rs); pl.append(cagr(r))
            row["placebo_live_cagr"] = sorted(pl); row["beats_placebos"] = f"{sum(cagr(row['live']) > x for x in pl)}/{k}"
            print(f"   placebo (random skip {q:.0%}): {sorted(pl)}  -> beats {row['beats_placebos']}", flush=True)
    return row

if G == "park":
    def on_ma(n): return np.r_[False, (spy > spy.rolling(n).mean()).values[:-1]]
    ma20 = spy.rolling(20).mean()
    fast = np.r_[False, ((spy > spy.rolling(100).mean()) | ((spy > ma20) & (ma20 > ma20.shift(5)))).values[:-1]]
    both_down = np.r_[False, ((spy > spy.rolling(100).mean()) | (spy > spy.rolling(50).mean())).values[:-1]]
    V = {"base: SPY > 100-day avg -> Clear Leader, else IEF/cash (live rule)": (S.park_on, {}),
         "SPY > 50-day": (on_ma(50), {}), "SPY > 20-day": (on_ma(20), {}), "SPY > 200-day": (on_ma(200), {}),
         "fast re-entry: > 100-day OR (> 20-day and 20-day rising)": (fast, {}), "stocks unless below BOTH 50- and 100-day": (both_down, {}),
         "always stocks (Clear Leader), never bonds": (np.ones(S.D, bool), {}), "never stocks (IEF/cash only)": (np.zeros(S.D, bool), {}),
         "SPY instead of Clear Leader (100-day rule)": (S.park_on, {"park": "spy"}), "SPY instead of Clear Leader, 50-day rule": (on_ma(50), {"park": "spy"})}
    orig = S.park_on.copy(); RES["variants"] = {}
    for name, (po, ex) in V.items():
        S.park_on = po; row = {}
        for lab, kw in (("live", LIVE), ("realistic", REAL)):
            r, _ = run({**kw, **ex}); row[lab] = r; log(f"{name} [{lab}]", r)
        row["days_in_stocks_pct"] = round(float(po[t0:].mean()) * 100, 1); RES["variants"][name] = row
    S.park_on = orig

if G == "picks":
    mom12 = (Cs.shift(5) / Cs.shift(257) - 1)                                     # 12-month return measured before the 5-day dip
    memv = M.values
    mr = mom12.where(M).rank(axis=1, pct=True).values                             # rank among current S&P 500 members
    near = (Cs.shift(5) >= 0.85 * Cs.rolling(252).max().shift(5)).values           # was within 15% of its 52-week high before the dip
    vol60 = Cs.pct_change().rolling(60).std().shift(5); vr = vol60.where(M).rank(axis=1, pct=True).values
    base = S.SIG; RES["variants"] = {"base (live rules)": with_placebo("base", None)}
    F = {"12-month return > 0 before the dip": base & (np.nan_to_num(mom12.values, nan=-1) > 0),
         "12-month return in top half of S&P 500": base & (np.nan_to_num(mr, nan=0) > 0.5),
         "within 15% of 52-week high before the dip": base & near,
         "calmer stocks (60-day volatility below median)": base & (np.nan_to_num(vr, nan=1) <= 0.5),
         "jumpier stocks (60-day volatility above median)": base & (np.nan_to_num(vr, nan=0) > 0.5)}
    for name, sg in F.items(): RES["variants"][name] = with_placebo(name, sg)
    w1 = np.where(np.nan_to_num(mr, nan=0.5) >= 2 / 3, 1.5, np.where(np.nan_to_num(mr, nan=0.5) <= 1 / 3, 0.5, 1.0))
    RES["variants"]["size by strength: top third 1.5x, bottom third 0.5x"] = with_placebo("size by strength", None, wmul=w1)
    w2 = np.where(np.nan_to_num(vr, nan=0.5) <= 0.5, 1.5, 0.5)
    RES["variants"]["size by calm: calm 1.5x, jumpy 0.5x"] = with_placebo("size by calm", None, wmul=w2)

if G == "brake":
    s200 = (spy > spy.rolling(200).mean()).values
    v20 = spy.pct_change().rolling(20).std(); vrank = v20.rolling(252, min_periods=200).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True).fillna(0.5).values
    breadth = ((Cs > Cs.rolling(200).mean()) & M).sum(axis=1) / M.sum(axis=1).replace(0, np.nan)
    br = breadth.fillna(0.5).values; dd = (spy / spy.rolling(252).max() - 1).values
    base = S.SIG; RES["variants"] = {"base (live rules)": with_placebo("base", None)}
    row_mask = lambda m: np.repeat(m[:, None], base.shape[1], axis=1)
    for name, m in {"skip when SPY < 200-day": ~s200, "skip when SPY volatility in top 20% of the year": vrank > 0.8,
                    "skip when < 40% of stocks above 200-day": br < 0.4, "skip when SPY > 15% below its 1-year high": dd < -0.15,
                    "skip when SPY > 25% below its 1-year high": dd < -0.25}.items():
        RES["variants"][name] = with_placebo(name, base & ~row_mask(m))
    for name, m in {"half size when SPY < 200-day": ~s200, "half size when SPY volatility in top 20%": vrank > 0.8,
                    "half size when < 40% of stocks above 200-day": br < 0.4}.items():
        RES["variants"][name] = with_placebo(name, None, wmul=np.where(row_mask(m), 0.5, 1.0))
    RES["variants"]["double size when SPY < 200-day (opposite test)"] = with_placebo("double size when SPY < 200-day", None, wmul=np.where(row_mask(~s200), 2.0, 1.0))

if G == "earn":
    ITEMS = json.load(open("data/sec_8k_items.json"))["tickers"] if os.path.exists("data/sec_8k_items.json") and not S.DRY else {}
    SIC = {t: (v.get("sic") or "")[:2] for t, v in json.load(open("data/sec_events_sic.json"))["tickers"].items()} if os.path.exists("data/sec_events_sic.json") and not S.DRY else {}
    dstr = np.array([str(x)[:10] for x in dn]); idx_of = {d: i for i, d in enumerate(dstr)}
    earn = np.zeros(S.SIG.shape, bool); has8k = np.zeros(len(tick), bool)
    for j, tk in enumerate(tick):
        ev = ITEMS.get(tk)                                   # old reused tickers carry a suffix (e.g. DELL-201310): never mapped to today's company
        if not ev: continue
        has8k[j] = True
        for d, mins, it in ev:
            its = set((it or "").split(","))
            if not ({"2.02", "12"} & its): continue
            i = int(np.searchsorted(dstr, d))
            if i >= len(dstr): continue
            if dstr[i] == d and mins is not None and mins > 15 * 60 + 45: i += 1       # filed after the 3:45 pm decision -> counts from the next day
            earn[i:i + 5, j] = True                                                  # inside the 5-day dip window that ends on day i..i+4
    RES["coverage"] = {"tickers_with_8k": int(has8k.sum()), "tickers": len(tick), "signals_with_8k_data_pct": round(float(S.SIG[t0:][:, has8k].sum() / S.SIG[t0:].sum()) * 100, 1)}
    print("coverage", RES["coverage"], flush=True)
    r5 = np.vstack([np.full((5, len(tick)), np.nan), S.S_C[5:] / S.S_C[:-5] - 1])
    grp = {}
    for j, t_ in enumerate(tick): grp.setdefault(SIC.get(t_, ""), []).append(j)
    peer = np.full(S.SIG.shape, np.nan)
    for t, j in zip(*np.nonzero(S.SIG)):
        g = [x for x in grp.get(SIC.get(tick[j], ""), []) if x != j and M.values[t, x] and np.isfinite(r5[t, x])] if SIC.get(tick[j]) else []
        if len(g) >= 3: peer[t, j] = np.median(r5[t, g])
    base = S.SIG; RES["variants"] = {"base (live rules)": with_placebo("base", None)}
    # per-trade view: how do earnings dips bounce vs the rest (live, all years)
    log_ = []; S.sim(**LIVE, log=log_)
    def st(x):
        x = np.array(x) * 100
        return {"n": len(x), "avg_pct": round(float(x.mean()), 2), "win_pct": round(float((x > 0).mean() * 100), 1), "t": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2)} if len(x) > 5 else {"n": len(x)}
    stocks = [(j, a, r) for k, j, a, b, usd, r in log_ if k == "S"]
    for nm, mask in (("earnings 8-K in dip window", earn), ("sector-wide dip (peers down 5%+)", np.nan_to_num(peer, nan=0) <= -0.05), ("stock alone (peers > -2%)", np.nan_to_num(peer, nan=-1) > -0.02)):
        RES.setdefault("per_trade", {})[nm] = {"with": st([r for j, a, r in stocks if mask[a, j]]), "without": st([r for j, a, r in stocks if not mask[a, j]]),
            "with 1999-2012": st([r for j, a, r in stocks if mask[a, j] and dn[a] < np.datetime64("2013-01-01")]), "with 2013-2026": st([r for j, a, r in stocks if mask[a, j] and dn[a] >= np.datetime64("2013-01-01")])}
    print(json.dumps(RES["per_trade"]), flush=True)
    for name, sg in {"skip dips with an earnings release in the window": base & ~earn,
                     "skip stock-alone dips (peers > -2%)": base & ~(np.nan_to_num(peer, nan=-1) > -0.02),
                     "only sector-wide dips (peers down 3%+)": base & (np.nan_to_num(peer, nan=0) <= -0.03),
                     "skip earnings dips that are stock-alone": base & ~(earn & (np.nan_to_num(peer, nan=-1) > -0.02))}.items():
        RES["variants"][name] = with_placebo(name, sg)

if G == "engine":
    extra = {s: S.yahoo(s) for s in ["GLD", "TLT", "DBC", "VNQ", "SHY"]}
    px_ = {s: S.E[s] for s in ["SPY", "QQQ", "EFA", "EEM", "IWM"] if s in S.E}; px_.update({k: v for k, v in extra.items() if v is not None})
    lvl = pd.DataFrame(px_).reindex(S.dates).ffill()
    bond_lvl = (1 + pd.Series(S.BOND_R, index=S.dates)).cumprod(); lvl["IEF"] = bond_lvl
    tb = pd.Series(S.TBILL_R, index=S.dates); ret = lvl.pct_change().fillna(0)
    mends = lvl.index.to_series().groupby(lvl.index.to_period("M")).max().values
    def monthly_engine(pick):
        """pick(month_end_date) -> {asset: weight}; held from the next day; 0.05% cost on turnover"""
        w = {}; out = []; me = set(mends)
        for i, d in enumerate(lvl.index):
            r = sum(v * (tb.iat[i] if a == "CASH" else ret[a].iat[i]) for a, v in w.items()) if w else tb.iat[i]
            if d in me:
                nw = pick(d); turn = sum(abs(nw.get(a, 0) - w.get(a, 0)) for a in set(nw) | set(w)); r -= 0.0005 * turn; w = nw
            out.append(r)
        return pd.Series(out, index=lvl.index)
    def sma10(a, d):
        s = lvl[a].loc[:d].resample("ME").last().dropna(); return len(s) >= 10 and s.iloc[-1] > s.iloc[-10:].mean()
    def r12(a, d):
        s = lvl[a].loc[:d].dropna(); return s.iloc[-1] / s.iloc[-253] - 1 if len(s) > 253 else None
    TS = ["SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "VNQ"]
    def tsmom(d):
        avail = [a for a in TS if a in lvl and lvl[a].loc[:d].notna().sum() > 260]
        if not avail: return {"CASH": 1.0}
        w = 1 / len(avail); out = {}
        for a in avail: k = a if sma10(a, d) else "CASH"; out[k] = out.get(k, 0) + w
        return out
    def gem(d):
        s, e, b = r12("SPY", d), r12("EFA", d) if "EFA" in lvl else None, r12("IEF", d)
        tbr = (1 + tb.loc[:d].iloc[-252:]).prod() - 1
        if s is None: return {"CASH": 1.0}
        if s > tbr: return {("EFA" if e is not None and e > s else "SPY"): 1.0}
        return {"IEF": 1.0}
    ENG = {"trend: 8 asset classes, each held when above its 10-month avg": monthly_engine(tsmom), "dual momentum (SPY / EFA / IEF)": monthly_engine(gem),
           "Clear Leader (10 ETFs)": pd.Series(S.CLR, index=S.dates)}
    _, dipc = run(LIVE); DIP = pd.Series(dipc, index=S.dates).pct_change().fillna(0)
    _, dipr = run(REAL); DIPR = pd.Series(dipr, index=S.dates).pct_change().fillna(0)
    def stats(r, a="2005-01-01"):
        r = r.loc[a:]; n = (1 + r).cumprod(); y = (r.index[-1] - r.index[0]).days / 365.25; m = (1 + r).resample("ME").prod() - 1
        def c(x, y_):
            z = r.loc[x:y_]; return round(((1 + z).prod() ** (365.25 / max((z.index[-1] - z.index[0]).days, 1)) - 1) * 100, 1)
        crash = {k: round(((1 + r.loc[x:y_]).prod() - 1) * 100, 1) for k, (x, y_) in {"2008": ("2007-10-09", "2009-03-09"), "2020": ("2020-02-19", "2020-03-23"), "2022": ("2022-01-03", "2022-10-12")}.items()}
        return {"cagr": round((n.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst": round(float((n / n.cummax() - 1).min()) * 100, 1), "sharpe": round(float(m.mean() / m.std() * np.sqrt(12)), 2),
                "2005-2015": c("2005", "2015"), "2016-2026": c("2016", "2026"), **{f"crash {k}": v for k, v in crash.items()}}
    RES["period"] = "2005-2026 (all engines have data)"; RES["dip bot alone (live)"] = stats(DIP); RES["dip bot alone (realistic)"] = stats(DIPR); RES["SPY"] = stats(pd.Series(S.spyr, index=S.dates))
    RES["engines"] = {}
    for en, er in ENG.items():
        row = {"alone": stats(er), "corr_with_dip_monthly": round(float(((1 + DIP.loc["2005":]).resample("ME").prod() - 1).corr((1 + er.loc["2005":]).resample("ME").prod() - 1)), 2)}
        for w in (0.8, 0.7, 0.6, 0.5):
            row[f"dip {int(w*100)} / engine {int(100-w*100)} (live)"] = stats(w * DIP + (1 - w) * er)
            row[f"dip {int(w*100)} / engine {int(100-w*100)} (realistic)"] = stats(w * DIPR + (1 - w) * er)
        RES["engines"][en] = row; print(en, json.dumps(row)[:600], flush=True)
    ser = pd.DataFrame({"dip_live": DIP, "dip_real": DIPR, "spy": S.spyr, **{k.split(":")[0].split(" (")[0]: v for k, v in ENG.items()}}, index=S.dates).loc["1999":]
    if not S.DRY: ser.round(7).to_csv("data/r9_series.csv.gz", compression="gzip")

os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1, default=str)
print("DONE", G, int(time.time() - T_START), "s")
