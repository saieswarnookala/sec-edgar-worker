"""Short interest as a filter on the dip bot (Nov 15 2026). Research only, not financial advice.
Question: when an S&P 500 stock triggers the live dip rule, does it bounce differently if short sellers hold a lot of it
(days to cover = shares short / average daily volume) or have been adding to their bets?
Data: FINRA consolidated short interest files (free, twice a month, exchange-listed + OTC), available from ~mid-2019:
https://cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv (YYYYMMDD = settlement date). A report counts only
12 calendar days after its settlement date (FINRA publishes ~8 business days later), so there is no look-ahead.
Dip rule = live paper-dip.mjs (10% vs SPY in 5 days, above 200-day avg, price >= $5, volume <= 2x); also bot 6 tuned (8%/150-day/hold 7).
Cache: each file parsed once into R2 (finra/si/<date>.json.gz) + index of settlement dates found (finra/si_index.json.gz).
Modes (env DRY): unset = real data; 'random' = random days-to-cover (should show NO edge); 'planted' = high days-to-cover on the
best bounces (MUST show an edge)."""
import os, sys, json, time, io, urllib.request, urllib.error
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r2cache

DRY = os.environ.get("DRY", "")
OUT = os.environ.get("OUT", "data/short_dips.json" if not DRY else f"/tmp/short_dips_{DRY}.json")
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
FIRST = os.environ.get("FIRST_MONTH", "2017-01")     # earlier months are probed but FINRA returns 403 before ~2019
LAG = 12                                              # calendar days from settlement to publicly available

# ---------------- prices + dip signals
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "2015-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOL = P("adj_close"), P("close"), P("volume"); del px
tick = [t for t in ALLT if t != "SPY"]; TI = {t: i for i, t in enumerate(tick)}; D, J = len(dates), len(tick)
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
valid = A[tick].notna(); HASPX = valid.values
M &= valid & valid.shift(-1, fill_value=False)
Cs = A[tick].ffill(); spy = A["SPY"].ffill()
ex5 = (Cs / Cs.shift(5) - 1).sub(spy / spy.shift(5) - 1, axis=0)
vr = VOL[tick].rolling(5).mean() / VOL[tick].shift(5).rolling(50).mean()
base_ok = M & (RAW[tick] >= 5) & (vr <= 2.0)
SIG = {(d, k): (base_ok & (Cs > Cs.rolling(k).mean()) & (ex5 <= -d)).values for d, k in ((0.10, 200), (0.08, 150))}
C, M5, RK, SP = Cs.values, Cs.rolling(5).mean().values, ex5.values, spy.values
dn = dates.values

def trade(t, j, hold=5, cost=0.001):
    for k in range(1, hold + 1):
        u = t + k
        if u >= D: return None
        if C[u, j] > M5[u, j] or k == hold: return C[u, j] / C[t, j] - 1 - cost, SP[u] / SP[t] - 1

# ---------------- FINRA short interest
def get(url, tries=4):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 sentinel-research"}), timeout=90) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404): return None
            print("http", e.code, url, flush=True)
        except Exception as e: print("err", str(e)[:100], url, flush=True)
        time.sleep(4 * 2 ** a)
    return None

def parse(b):
    df = pd.read_csv(io.BytesIO(b), sep="|", dtype=str, quotechar='"')
    df.columns = [c.strip().strip('"') for c in df.columns]
    need = {"symbolCode", "currentShortPositionQuantity", "averageDailyVolumeQuantity"}
    if need - set(df.columns): raise SystemExit(f"FINRA columns changed: missing {need - set(df.columns)}; have {list(df.columns)}")
    dtc_col = next((c for c in df.columns if c.lower().startswith("daystocover")), None)
    sh = pd.to_numeric(df.currentShortPositionQuantity, errors="coerce"); adv = pd.to_numeric(df.averageDailyVolumeQuantity, errors="coerce")
    prev = pd.to_numeric(df.get("previousShortPositionQuantity"), errors="coerce") if "previousShortPositionQuantity" in df.columns else pd.Series(np.nan, index=df.index)
    dtc = pd.to_numeric(df[dtc_col], errors="coerce") if dtc_col else sh / adv.where(adv > 0)
    ok = df.symbolCode.notna() & sh.notna()
    return {"sym": df.symbolCode[ok].str.strip().tolist(), "short": sh[ok].tolist(), "prev": prev[ok].fillna(-1).tolist(), "dtc": dtc[ok].fillna(-1).round(2).tolist()}

def candidates(y, m):
    """Settlement dates are the 15th and last day of the month, moved back to a business day."""
    out = []
    for anchor in (pd.Timestamp(y, m, 15), pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)):
        out.append([(anchor - pd.Timedelta(days=k)).strftime("%Y%m%d") for k in range(0, 6) if (anchor - pd.Timedelta(days=k)).weekday() < 5])
    return out

def load_si():
    idx = r2cache.load("finra/si_index.json.gz") or {"found": [], "checked_periods": []}
    found, checked = set(idx["found"]), set(idx["checked_periods"])
    last = pd.Timestamp.today() - pd.Timedelta(days=LAG)
    reports, fetched = {}, 0
    for per in pd.period_range(FIRST, last.strftime("%Y-%m"), freq="M"):
        for half, cands in zip(("a", "b"), candidates(per.year, per.month)):
            key = f"{per}{half}"; hit = next((d for d in cands if d in found), None)
            if hit is None and key in checked: continue                       # probed before, not on FINRA
            if hit is None:
                if pd.Timestamp(cands[-1]) > last: continue
                for d in cands:
                    b = get(f"https://cdn.finra.org/equity/otcmarket/biweekly/shrt{d}.csv"); time.sleep(0.5)
                    if b and len(b) > 10000: hit = d; r = parse(b); r2cache.save(f"finra/si/{d}.json.gz", r); reports[d] = r; found.add(d); fetched += 1; break
                checked.add(key)
                if hit is None: continue
            if hit not in reports:
                r = r2cache.load(f"finra/si/{hit}.json.gz")
                if r is None:
                    b = get(f"https://cdn.finra.org/equity/otcmarket/biweekly/shrt{hit}.csv"); time.sleep(0.5)
                    if not b: continue
                    r = parse(b); r2cache.save(f"finra/si/{hit}.json.gz", r); fetched += 1
                reports[hit] = r
    r2cache.save("finra/si_index.json.gz", {"found": sorted(found), "checked_periods": sorted(checked)})
    print(f"short interest reports: {len(reports)} ({fetched} downloaded), first {min(reports) if reports else None}, last {max(reports) if reports else None}", flush=True)
    return reports

def to_matrix(reports):
    """DTC and change-in-short matrices on the trading calendar, each report active from settlement + LAG days."""
    DTC = np.full((D, J), np.nan); CHG = np.full((D, J), np.nan); mapped = tot = 0
    for d in sorted(reports):
        e = int(np.searchsorted(dn, np.datetime64(pd.Timestamp(d) + pd.Timedelta(days=LAG))))
        if e >= D: continue
        r = reports[d]; tot += len(r["sym"])
        for s, sh, pv, dtc in zip(r["sym"], r["short"], r["prev"], r["dtc"]):
            j = TI.get(s.replace(".", "-").replace("/", "-"))
            if j is None or not HASPX[e, j]: continue
            mapped += 1; DTC[e, j] = dtc if dtc >= 0 else np.nan; CHG[e, j] = sh / pv - 1 if pv > 0 else np.nan
    print(f"rows mapped to S&P price tickers: {mapped} of {tot}", flush=True)
    return pd.DataFrame(DTC).ffill(limit=15).values, pd.DataFrame(CHG).ffill(limit=15).values    # a report stays valid ~3 weeks

# ---------------- per-signal trades
if DRY: t0 = int(np.searchsorted(dn, np.datetime64("2019-07-01")))
reports = None if DRY else load_si()
if not DRY:
    DTC, CHG = to_matrix(reports)
    first_avail = int(np.argmax(~np.isnan(DTC).all(axis=1))); t0 = first_avail
print("analysis starts", str(dn[t0])[:10], flush=True)
rows = []
for sigk, hold in (((0.10, 200), 5), ((0.08, 150), 7)):
    for t in range(t0, D):
        for j in np.flatnonzero(SIG[sigk][t]):
            x = trade(t, j, hold)
            if x: rows.append((f"{sigk[0]:.2f}/{sigk[1]}", t, j, x[0], x[0] - x[1]))
X = pd.DataFrame(rows, columns=["rule", "t", "j", "ret", "exc"])
if DRY:
    rng = np.random.default_rng(3); DTC = np.full((D, J), np.nan); CHG = np.full((D, J), np.nan)
    X["dtc"] = rng.gamma(2, 1.5, len(X)); X["chg"] = rng.normal(0, 0.15, len(X))
    if DRY == "planted":
        hi = X.ret >= X.ret.quantile(0.8); X.loc[hi, "dtc"] = X.loc[hi, "dtc"] + 4
else:
    X["dtc"] = [DTC[t, j] for t, j in zip(X.t, X.j)]; X["chg"] = [CHG[t, j] for t, j in zip(X.t, X.j)]
X["late"] = [dn[t] >= np.datetime64("2023-01-01") for t in X.t]
print("dip trades", len(X), "| with short data", f"{X.dtc.notna().mean():.0%}", flush=True)

def stats(g, base=None):
    if len(g) < 2: return {"n": int(len(g))}
    o = {"n": int(len(g)), "avg_trade_pct": round(g.ret.mean() * 100, 2), "win_pct": round((g.ret > 0).mean() * 100, 1), "avg_vs_spy_pct": round(g.exc.mean() * 100, 2)}
    if base is not None and len(base) > 1:
        o["diff_vs_rest_pct"] = round((g.ret.mean() - base.ret.mean()) * 100, 2)
        o["t_stat"] = round((g.ret.mean() - base.ret.mean()) / np.sqrt(g.ret.var() / len(g) + base.ret.var() / len(base)), 2)
    return o
res = {}
for rule, R in X[X.dtc.notna()].groupby("rule"):
    q80 = R.dtc.quantile(0.8); q20 = R.dtc.quantile(0.2)
    G = [("all dips with short data", R.dtc >= 0), ("days to cover < 2", R.dtc < 2), ("days to cover 2-5", (R.dtc >= 2) & (R.dtc < 5)),
         ("days to cover >= 5", R.dtc >= 5), (f"most shorted 20% (dtc >= {q80:.1f})", R.dtc >= q80), (f"least shorted 20% (dtc <= {q20:.1f})", R.dtc <= q20),
         ("shorts added 20%+ last report", R.chg >= 0.20), ("shorts cut 10%+ last report", R.chg <= -0.10)]
    res[rule] = {}
    for name, f in G:
        res[rule][name] = {"all": stats(R[f], R[~f] if not f.all() else None), "2019-2022": stats(R[f & ~R.late], R[~f & ~R.late]), "2023-2026": stats(R[f & R.late], R[~f & R.late])}
        a = res[rule][name]
        print(f"{rule} {name:36s} n={a['all']['n']:5d} avg {a['all'].get('avg_trade_pct')}% win {a['all'].get('win_pct')} diff {a['all'].get('diff_vs_rest_pct', '')} t {a['all'].get('t_stat', '')} | early {a['2019-2022'].get('avg_trade_pct')} late {a['2023-2026'].get('avg_trade_pct')}", flush=True)

# ---------------- portfolio (real data only)
PORT = {}
if not DRY:
    spyr = np.r_[0, SP[1:] / SP[:-1] - 1]; park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]
    def sim(mode="base", sigk=(0.10, 200), hold=5, slots=10, w=0.10, cost=0.0005, cut=5.0):
        sg = SIG[sigk]; pos, eq, curve, trades = [], 1.0, np.ones(D), []
        for t in range(t0, D):
            r = sum(w * (C[t, p[0]] / C[t - 1, p[0]] - 1) for p in pos)
            if park_on[t]: r += (1 - w * len(pos)) * spyr[t]
            eq *= 1 + r; keep = []
            for p in pos:
                age = t - p[1]
                if age >= 1 and (C[t, p[0]] > M5[t, p[0]] or age >= hold): eq *= 1 - w * 2 * cost; trades.append((p[1], C[t, p[0]] / p[2] - 1 - 2 * cost))
                else: keep.append(p)
            pos = keep; held = {p[0] for p in pos}; free = slots - len(pos)
            if free > 0:
                c = [j for j in np.flatnonzero(sg[t]) if j not in held]
                dt = lambda j: DTC[t, j] if DTC[t, j] == DTC[t, j] else 2.0
                if mode == "skip high dtc": c = [j for j in c if dt(j) < cut]
                if mode == "only high dtc": c = [j for j in c if dt(j) >= cut]
                if mode == "high dtc first": c.sort(key=lambda j: (-dt(j), RK[t, j]))
                elif mode == "low dtc first": c.sort(key=lambda j: (dt(j), RK[t, j]))
                else: c.sort(key=lambda j: RK[t, j])
                for j in c[:free]: pos.append((j, t, C[t, j]))
            curve[t] = eq
        out = {}
        for name, a, b in (("all", str(dn[t0])[:10], "2100-01-01"), ("2019-2022", str(dn[t0])[:10], "2023-01-01"), ("2023-2026", "2023-01-01", "2100-01-01")):
            idx = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
            cv = curve[idx] / curve[idx[0]]; y = len(idx) / 252; s = SP[idx] / SP[idx[0]]; tr = [x[1] for x in trades if a <= str(dn[x[0]])[:10] < b]
            out[name] = {"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
                         "spy_pct": round((s[-1] ** (1 / y) - 1) * 100, 1), "trades_per_month": round(len(tr) / (y * 12), 1), "avg_trade_pct": round(float(np.mean(tr)) * 100, 2) if tr else None}
        return out
    for tag, kw0 in (("today", {}), ("bot6", {"sigk": (0.08, 150), "hold": 7})):
        for name, kw in (("rules as now", {}), ("skip days-to-cover >= 5", {"mode": "skip high dtc"}), ("skip days-to-cover >= 3", {"mode": "skip high dtc", "cut": 3.0}),
                         ("most shorted first", {"mode": "high dtc first"}), ("least shorted first", {"mode": "low dtc first"}), ("only days-to-cover >= 3", {"mode": "only high dtc", "cut": 3.0})):
            a = PORT[f"{tag} | {name}"] = sim(**kw0, **kw)
            print(f"PORTFOLIO {tag} | {name:28s} {a['all']['per_year_pct']}%/yr worst {a['all']['worst_drop_pct']} (SPY {a['all']['spy_pct']}) | early {a['2019-2022']['per_year_pct']} late {a['2023-2026']['per_year_pct']} | tr/mo {a['all']['trades_per_month']} avg {a['all']['avg_trade_pct']}", flush=True)

json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "start": str(dn[t0])[:10],
           "reports": sorted(reports) if reports else None, "dip_trades": int(len(X)), "groups": res, "portfolio": PORT}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
