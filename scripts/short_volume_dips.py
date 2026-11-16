"""Short VOLUME as a dip filter (Nov 15 2026). Research only, not financial advice.
Bot 8 uses FINRA short INTEREST (days to cover), which is free only from Dec 2017. FINRA's free DAILY short-sale volume files
(off-exchange TRF trades: FNSQshvol = Nasdaq TRF, FNYXshvol = NYSE TRF, FNQCshvol = Nasdaq TRF Chicago) go back to Aug 2009.
Short volume ratio (SVR) = short shares / total shares traded that day. Signal: SVR during the dip (the 4 days before the buy day,
because a day's file comes out after the close) minus the stock's own normal SVR (the 60 days before that) = "short selling jump".
STAGE=check  -> 2018-2026 only: does SVR agree with days-to-cover (same stocks flagged? same weak bounces?)
STAGE=full   -> 2009-2026: trade-level results by half + bot simulation.
Cache: one R2 object per finished month, finra/shvol/<YYYYMM>.json.gz, only S&P-history symbols.
DRY=random|planted: fake SVR jumps (random must show nothing, planted must be found)."""
import os, sys, json, time, urllib.request, urllib.error, threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r2cache

DRY, STAGE = os.environ.get("DRY", ""), os.environ.get("STAGE", "check")
FIRST = os.environ.get("FIRST_MONTH", "2018-01" if STAGE == "check" else "2009-08")
OUT = os.environ.get("OUT", f"data/short_volume_{STAGE}.json" if not DRY else f"/tmp/short_volume_{DRY}.json")
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
LAG = 12

for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "2008-06-01"]
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
SIG = (base_ok & (Cs > Cs.rolling(200).mean()) & (ex5 <= -0.10)).values
C, M5, RK, SP = Cs.values, Cs.rolling(5).mean().values, ex5.values, spy.values
dn = dates.values; DI = {str(d)[:10].replace("-", ""): i for i, d in enumerate(dn)}
# FINRA symbol -> price tickers (suffixed '-YYYYMM' = older company that used the symbol; pick the one with a price that day)
BASE = {}
for t in tick:
    b = t.rsplit("-", 1)[0] if t[-7:-6] == "-" and t[-6:].isdigit() else t
    BASE.setdefault(b.replace("-", "."), []).append(TI[t])
def jmap(sym, i):
    for j in BASE.get(sym.replace("/", "."), []):
        if HASPX[i, j]: return j
    return None

# ---------------- download FINRA daily short volume (S&P symbols only), month by month
def get(url):
    for a in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 sentinel-research"}), timeout=60) as r: return r.read().decode("latin1")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404): return None
            time.sleep(3 * 2 ** a)
        except Exception: time.sleep(3 * 2 ** a)
    return None
lock = threading.Lock(); last = [0.0]; BAD = []
def polite_get(url):
    with lock:                                   # <= ~6 requests/second across all threads
        w = last[0] + 0.17 - time.time()
        if w > 0: time.sleep(w)
        last[0] = time.time()
    return get(url)
def day_rows(d):
    out = {}
    for pre in ("FNSQshvol", "FNYXshvol", "FNQCshvol"):
        txt = polite_get(f"https://cdn.finra.org/equity/regsho/daily/{pre}{d}.txt")
        if not txt: continue
        lines = txt.splitlines(); h = lines[0].split("|") if lines else []
        if "Symbol" in h and "ShortVolume" in h and "TotalVolume" in h: iS, iV, iT = h.index("Symbol"), h.index("ShortVolume"), h.index("TotalVolume"); body = lines[1:]
        elif len(h) in (5, 6) and h[0].isdigit() and len(h[0]) == 8:     # some old files have no header row: known layouts
            iS, iV, iT = 1, 2, (3 if len(h) == 5 else 4); body = lines
            BAD.append(f"{pre}{d} no header ({len(h)} cols)")
        else:
            BAD.append(f"{pre}{d} unknown layout {h[:6]}"); continue
        for ln in body:
            f = ln.split("|")
            if len(f) <= iT: continue
            s = f[iS].replace("/", ".")
            if s not in BASE: continue
            try: sv, tv = float(f[iV]), float(f[iT])
            except ValueError: continue
            o = out.setdefault(s, [0.0, 0.0]); o[0] += sv; o[1] += tv
    return out
def load_month(per):
    key = f"finra/shvol/{per.strftime('%Y%m')}.json.gz"
    days = [k for k in DI if k[:6] == per.strftime("%Y%m")]
    finished = per.end_time < pd.Timestamp.today() - pd.Timedelta(days=3)
    if finished:
        c = r2cache.load(key)
        if c is not None: return c, 0
    with ThreadPoolExecutor(4) as ex: res = dict(zip(days, ex.map(day_rows, days)))
    res = {d: v for d, v in res.items() if v}
    if finished and res: r2cache.save(key, res)
    return res, len(days)

SV = np.full((D, J), np.nan); TV = np.full((D, J), np.nan)
if not DRY:
    fetched = 0; t_start = time.time()
    for per in pd.period_range(FIRST, dates[-1].strftime("%Y-%m"), freq="M"):
        res, n = load_month(per); fetched += n
        for d, rows in res.items():
            i = DI.get(d)
            if i is None: continue
            for s, (sv, tv) in rows.items():
                j = jmap(s, i)
                if j is not None and tv > 0: SV[i, j] = sv; TV[i, j] = tv
        if per.month == 1 or n: print(per, "days with data", len(res), "| downloaded days", n, f"| {time.time() - t_start:.0f}s", flush=True)
    print("files without a header row / unreadable:", len(BAD), BAD[:8], flush=True)
    if sum("unknown" in b for b in BAD) > 50: raise SystemExit("too many unreadable FINRA files: " + str(BAD[:10]))
    print("days fetched from FINRA", fetched, "| stock-days with short volume", int(np.isfinite(SV).sum()), flush=True)

# features: SVR over days t-4..t-1 vs SVR over t-64..t-5 (only data published before the 3:45 pm buy)
def roll(x, n): return pd.DataFrame(x).rolling(n, min_periods=int(n * 0.6)).sum().values
S4, T4, S60, T60 = roll(SV, 4), roll(TV, 4), roll(SV, 60), roll(TV, 60)
with np.errstate(invalid="ignore", divide="ignore"):
    LVL = np.vstack([np.full((1, J), np.nan), (S4 / T4)[:-1]]); BASEL = np.vstack([np.full((5, J), np.nan), (S60 / T60)[:-5]])
JUMP = LVL - BASEL

def trade(t, j, hold=5, cost=0.001):
    for k in range(1, hold + 1):
        u = t + k
        if u >= D: return None
        if C[u, j] > M5[u, j] or k == hold: return C[u, j] / C[t, j] - 1 - cost, SP[u] / SP[t] - 1
t0 = int(np.searchsorted(dn, np.datetime64(pd.Timestamp(FIRST + "-01") + pd.Timedelta(days=100))))
rows = []
for t in range(t0, D):
    for j in np.flatnonzero(SIG[t]):
        x = trade(t, j)
        if x: rows.append((t, j, x[0], x[0] - x[1], LVL[t, j], JUMP[t, j]))
X = pd.DataFrame(rows, columns=["t", "j", "ret", "exc", "lvl", "jump"])
if DRY:
    rng = np.random.default_rng(5); X["lvl"] = rng.normal(0.45, 0.08, len(X)); X["jump"] = rng.normal(0, 0.06, len(X))
    if DRY == "planted": lo = X.ret <= X.ret.quantile(0.2); X.loc[lo, "jump"] += 0.12          # heavy shorting before the worst trades
X["year"] = [int(str(dn[t])[:4]) for t in X.t]
print("dip trades", len(X), "| with short volume", f"{X.jump.notna().mean():.0%}", flush=True)

def stats(g, rest=None):
    if len(g) < 2: return {"n": int(len(g))}
    o = {"n": int(len(g)), "avg_trade_pct": round(g.ret.mean() * 100, 2), "win_pct": round((g.ret > 0).mean() * 100, 1)}
    if rest is not None and len(rest) > 1:
        o["diff_vs_rest_pct"] = round((g.ret.mean() - rest.ret.mean()) * 100, 2)
        o["t_stat"] = round((g.ret.mean() - rest.ret.mean()) / np.sqrt(g.ret.var() / len(g) + rest.ret.var() / len(rest)), 2)
    return o
Xv = X[X.jump.notna()]
def groups(R):
    q80, q20, l80 = R.jump.quantile(0.8), R.jump.quantile(0.2), R.lvl.quantile(0.8)
    return [("all dips", R.jump.notna()), ("short selling jumped 10+ points", R.jump >= 0.10), (f"biggest jump 20% (>= {q80 * 100:+.1f} pts)", R.jump >= q80),
            (f"short selling fell most 20% (<= {q20 * 100:+.1f} pts)", R.jump <= q20), (f"highest short ratio 20% (>= {l80:.0%})", R.lvl >= l80)]
res = {"check" if STAGE == "check" else "full": {}}
periods = [("2018-2026", "2018", "2100")] if STAGE == "check" else [("2009-2026", "2009", "2100"), ("2009-2017", "2009", "2018"), ("2018-2026", "2018", "2100")]
for name, a, b in periods:
    R = Xv[(Xv.year >= int(a)) & (Xv.year < int(b))]; out = {}
    for g, f in groups(R):
        out[g] = stats(R[f], R[~f] if not f.all() else None); s = out[g]
        print(f"{name} {g:42s} n={s['n']:5d} avg {s.get('avg_trade_pct')}% win {s.get('win_pct')} diff {s.get('diff_vs_rest_pct', '')} t {s.get('t_stat', '')}", flush=True)
    res[list(res)[0]][name] = out

# ---------------- agreement with days-to-cover (2018+): same stocks? same weak bounces?
agree = {}
if not DRY:
    idx = r2cache.load("finra/si_index.json.gz")
    if idx:
        DTC = np.full((D, J), np.nan)
        for d in idx["found"]:
            r = r2cache.load(f"finra/si/{d}.json.gz"); e = int(np.searchsorted(dn, np.datetime64(pd.Timestamp(d) + pd.Timedelta(days=LAG))))
            if r is None or e >= D: continue
            for s, x in zip(r["sym"], r["dtc"]):
                j = jmap(s, e)
                if j is not None and x >= 0: DTC[e, j] = x
        DTC = pd.DataFrame(DTC).ffill(limit=15).values
        X["dtc"] = [DTC[t, j] for t, j in zip(X.t, X.j)]
        B = X[X.dtc.notna() & X.jump.notna()]
        if len(B) > 50:
            agree = {"dips_with_both": int(len(B)),
                     "rank_corr_dtc_vs_short_ratio": round(float(B.dtc.rank().corr(B.lvl.rank())), 3),
                     "rank_corr_dtc_vs_jump": round(float(B.dtc.rank().corr(B.jump.rank())), 3),
                     "heavily_shorted_dtc5": stats(B[B.dtc >= 5], B[B.dtc < 5]),
                     "big_jump_10pts": stats(B[B.jump >= 0.10], B[B.jump < 0.10]),
                     "both_flags": stats(B[(B.dtc >= 5) & (B.jump >= 0.10)]),
                     "share_of_dtc5_dips_also_jump10": round(float((B[B.dtc >= 5].jump >= 0.10).mean()), 3)}
            cs = []      # whole-market check: on each report date, do stocks with high days-to-cover also have high short ratios?
            for i in range(0, D, 21):
                a, b2 = DTC[i], LVL[i]; ok = np.isfinite(a) & np.isfinite(b2)
                if ok.sum() > 100: cs.append(pd.Series(a[ok]).rank().corr(pd.Series(b2[ok]).rank()))
            agree["all_stocks_monthly_rank_corr_dtc_vs_short_ratio"] = round(float(np.mean(cs)), 3) if cs else None
            print("AGREEMENT", json.dumps(agree), flush=True)

# ---------------- portfolio
PORT = {}
if not DRY:
    spyr = np.r_[0, SP[1:] / SP[:-1] - 1]; park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]
    def sim(cut=None, by="jump", cost=0.0005):
        F = JUMP if by == "jump" else LVL
        pos, eq, curve, trades = [], 1.0, np.ones(D), []
        for t in range(t0, D):
            r = sum(0.1 * (C[t, p[0]] / C[t - 1, p[0]] - 1) for p in pos)
            if park_on[t]: r += (1 - 0.1 * len(pos)) * spyr[t]
            eq *= 1 + r; keep = []
            for p in pos:
                age = t - p[1]
                if age >= 1 and (C[t, p[0]] > M5[t, p[0]] or age >= 5): eq *= 1 - 0.1 * 2 * cost; trades.append((p[1], C[t, p[0]] / p[2] - 1 - 2 * cost))
                else: keep.append(p)
            pos = keep; held = {p[0] for p in pos}; free = 10 - len(pos)
            if free > 0:
                c = [j for j in np.flatnonzero(SIG[t]) if j not in held and (cut is None or not (F[t, j] >= cut))]
                c.sort(key=lambda j: RK[t, j])
                for j in c[:free]: pos.append((j, t, C[t, j]))
            curve[t] = eq
        out = {}
        for name, a, b in periods:
            ix = np.flatnonzero((dn >= np.datetime64(f"{a}-01-01")) & (dn < np.datetime64(f"{b}-01-01")) & (np.arange(D) >= t0))
            if len(ix) < 30: continue
            cv = curve[ix] / curve[ix[0]]; y = len(ix) / 252; tr = [x[1] for x in trades if a <= str(dn[x[0]])[:4] < b]
            out[name] = {"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
                         "spy_pct": round(((SP[ix[-1]] / SP[ix[0]]) ** (1 / y) - 1) * 100, 1), "trades_per_month": round(len(tr) / (y * 12), 1), "avg_trade_pct": round(float(np.mean(tr)) * 100, 2) if tr else None}
        return out
    for name, kw in (("rules as now", {}), ("skip short-selling jump >= 10 pts", {"cut": 0.10}), ("skip short-selling jump >= 15 pts", {"cut": 0.15}), ("skip short ratio >= 60%", {"cut": 0.60, "by": "lvl"})):
        PORT[name] = a = sim(**kw)
        print("PORTFOLIO", f"{name:36s}", " | ".join(f"{k}: {v['per_year_pct']}%/yr worst {v['worst_drop_pct']} tr/mo {v['trades_per_month']}" for k, v in a.items()), flush=True)

json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "stage": STAGE, "dry": DRY or None, "first_month": FIRST,
           "dip_trades": int(len(X)), "groups": res, "agreement_with_days_to_cover": agree, "portfolio": PORT}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
