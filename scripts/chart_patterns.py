"""Classic chart patterns, tested honestly (Nov 15 2026). Research only, not financial advice.
Patterns (daily closes, detected only with data known at the close of the signal day; buy at that close):
  1 '52w-high breakout + volume'  first close above the prior 52-week high after >= 20 days without one, volume >= 1.5x its 50-day avg
                                   (George & Hwang 2004; O'Neil)
  2 'bull flag'                   10-day pole up >= 20%, then 3/5/8-day flag holding within 10% of the top, then a close above the flag
  3 'high tight flag'             price up >= 90% in 40 days, flag of 5/10/15 days holding within 25% of the top, then breakout (Bulkowski)
  4 'tight-base breakout (VCP)'   uptrend (close > 50d > 200d avg), last 20 days in a <= 10% range with calmer moves than usual,
                                   close above the base on >= 1.5x volume (Minervini / Darvas box)
  5 'inverse head & shoulders'    low-high-LOWER low-high-low (shoulders within 5%, neckline within 5%), close above the neckline
  6 'double bottom'               two lows within 3%, 15-90 days apart, peak between >= 10% higher, close above that peak
  7 'head & shoulders top' (bearish) mirror of 5, close below the neckline -> should be followed by WEAK returns
Measured: return after 5/20/60 trading days minus the average eligible stock over the same days ("vs avg stock") and minus SPY,
after round-trip costs by liquidity. t-stats average events per day first (events on the same day aren't independent).
Plus a simple 10-slot bot per pattern (hold 20 days, idle money in SPY when SPY > 100-day avg), compared with the same bot
buying RANDOM eligible stocks (the fair baseline: small stocks can beat or trail SPY for reasons unrelated to patterns).
UNIVERSE=us_all: all US common stocks incl. delisted (Alpaca daily, R2 cache daily/us_all_adj_all.json.gz, 2016-2026), price >= $5,
  >= $5M/day traded, split into size groups by dollar volume rank (large 1-500, mid 501-1500, small 1501-3000, micro 3000+).
UNIVERSE=sp500: point-in-time S&P 500 members 1999-2026.
DRY=random: random-walk prices (patterns must show NO edge); DRY=planted: same, plus +6% added over the 20 days after every
bull-flag signal (must be found)."""
import os, sys, json, time, urllib.request
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

U, DRY = os.environ.get("UNIVERSE", "sp500"), os.environ.get("DRY", "")
OUT = os.environ.get("OUT", f"data/chart_patterns_{U}.json" if not DRY else f"/tmp/chart_patterns_{DRY}.json")
LIMIT = int(os.environ.get("LIMIT", "0"))
t_load = time.time()
if DRY:
    rng = np.random.default_rng(11); D, N = 2600, 600
    dates = pd.bdate_range("2016-01-04", periods=D)
    R = rng.standard_t(4, (D, N)) * 0.02 / np.sqrt(2) + 0.0003
    jumps = rng.random((D, N)) < 0.004; R[jumps] += rng.normal(0.08, 0.06, jumps.sum())     # occasional big moves so patterns appear
    C = 20 * np.exp(np.cumsum(R, axis=0)); V = rng.lognormal(13, 0.5, (D, N)) * (1 + 2 * jumps)
    SP = 200 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, D))); MEMB = np.ones((D, N), bool); tick = [f"S{i}" for i in range(N)]
    START, HALVES = "2017-01-01", (("2017-2020", "2017-01-01", "2021-01-01"), ("2021-2026", "2021-01-01", "2100-01-01"))
elif U == "us_all":
    import r2cache
    cache = r2cache.load("daily/us_all_adj_all.json.gz")
    if not cache: raise SystemExit("R2 cache daily/us_all_adj_all.json.gz not found (run dip-universe.yml once to build it)")
    rows = cache["rows"]; del cache
    if "SPY" not in rows: raise SystemExit("SPY missing in cache")
    dates = pd.DatetimeIndex(sorted(rows["SPY"])); ds = [d.strftime("%Y-%m-%d") for d in dates]
    tick = sorted(s for s in rows if s != "SPY" and len(rows[s]) >= 250)
    if LIMIT: tick = tick[:LIMIT]
    C = np.full((len(ds), len(tick)), np.nan, np.float32); V = np.full_like(C, np.nan); di = {d: i for i, d in enumerate(ds)}
    for j, s in enumerate(tick):
        for d, v in rows[s].items():
            i = di.get(d)
            if i is not None: C[i, j], V[i, j] = v[0], v[1]
    C, V = C.astype(float), V.astype(float)
    SP = np.array([rows["SPY"][d][0] for d in ds]); del rows
    MEMB = ~np.isnan(C); START = "2016-06-01"
    HALVES = (("2016-2020", "2016-01-01", "2021-01-01"), ("2021-2026", "2021-01-01", "2100-01-01"))
else:
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
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
    C = A[tick].values; V = (VV[tick] * RAWC[tick] / A[tick]).values
    SP = A["SPY"].ffill().values; MEMB = Mdf.values & ~np.isnan(C); START = "1999-06-01"
    HALVES = (("1999-2012", "1999-01-01", "2013-01-01"), ("2013-2026", "2013-01-01", "2100-01-01"))
D, N = C.shape; dn = dates.values; t0 = int(np.searchsorted(dn, np.datetime64(START)))
print(U, DRY or "real", "days", D, "stocks", N, str(dn[0])[:10], str(dn[-1])[:10], f"load {time.time() - t_load:.0f}s", flush=True)

# ---------------- helpers
F = lambda x: pd.DataFrame(x)
Cf = F(C).ffill(limit=5).values
sh = lambda x, k: np.vstack([np.full((k, x.shape[1]), np.nan), x[:-k]]) if k > 0 else x
rmax = lambda x, k: F(x).rolling(k, min_periods=int(k * 0.9)).max().values
rmin = lambda x, k: F(x).rolling(k, min_periods=int(k * 0.9)).min().values
rmean = lambda x, k: F(x).rolling(k, min_periods=int(k * 0.75)).mean().values
with np.errstate(all="ignore"):
    dvol = rmean(C * V, 20)
    rnk = F(np.where((C >= 5) & MEMB, dvol, np.nan)).rank(axis=1, ascending=False).values
    if U == "us_all" and not DRY: ELIG = MEMB & (C >= 5) & (dvol >= 5e6)
    else: ELIG = MEMB & (C >= 5)
    size = np.where(rnk <= 500, 0, np.where(rnk <= 1500, 1, np.where(rnk <= 3000, 2, 3)))
    cost = np.where(dvol >= 1e8, 0.0005, np.where(dvol >= 2e7, 0.0010, 0.0020))       # per side
    V50 = sh(rmean(V, 50), 1); MA50, MA200 = rmean(C, 50), rmean(C, 200)
    r1 = C / sh(C, 1) - 1
    vol10, vol50 = F(r1).rolling(10).std().values, F(r1).rolling(50).std().values
SIZE_NAMES = ["large (top 500)", "mid (501-1500)", "small (1501-3000)", "micro (3000+)"]

# ---------------- pattern detectors -> boolean (D, N)
def first_in(sig, gap=20):
    """keep only the first signal per stock within `gap` days (no double counting of one setup)"""
    out = np.zeros_like(sig); last = np.full(sig.shape[1], -10 ** 9)
    for t in np.flatnonzero(sig.any(axis=1)):
        js = np.flatnonzero(sig[t]); ok = js[t - last[js] > gap]; out[t, ok] = True; last[ok] = t
    return out
with np.errstate(all="ignore"):
    P = {}
    hi252 = sh(rmax(C, 252), 1); hi_old = sh(rmax(C, 232), 21)        # prior 52w high, and the part older than 20 days
    P["52w-high breakout + volume"] = (C > hi252) & (hi_old >= hi252 * 0.999) & (V >= 1.5 * V50)
    bf = np.zeros((D, N), bool)
    for L in (3, 5, 8):
        top = sh(C, L + 1); pole = top / sh(C, L + 11) - 1
        fmax, fmin = sh(rmax(C, L), 1), sh(rmin(C, L), 1)
        bf |= (pole >= 0.20) & (fmax <= top * 1.02) & (fmin >= top * 0.90) & (C > np.fmax(fmax, top))
    P["bull flag"] = bf
    htf = np.zeros((D, N), bool)
    for L in (5, 10, 15):
        top = sh(C, L + 1); pole = top / sh(C, L + 41) - 1
        fmax, fmin = sh(rmax(C, L), 1), sh(rmin(C, L), 1)
        htf |= (pole >= 0.90) & (fmax <= top * 1.02) & (fmin >= top * 0.75) & (C > np.fmax(fmax, top))
    P["high tight flag"] = htf
    bmax, bmin = sh(rmax(C, 20), 1), sh(rmin(C, 20), 1)
    P["tight-base breakout (VCP)"] = (sh(C, 1) > sh(MA50, 1)) & (MA50 > MA200) & ((bmax - bmin) / bmax <= 0.10) & (sh(vol10, 1) < 0.7 * sh(vol50, 1)) & (C > bmax) & (V >= 1.5 * V50)

# pivot-based patterns (inverse H&S, double bottom, H&S top): a pivot at day p is confirmed only at p+5
W = 5
def pivots(c):
    s = pd.Series(c); lo = s.rolling(2 * W + 1, center=True).min(); hi = s.rolling(2 * W + 1, center=True).max()
    pts = [(p, "L", c[p]) for p in np.flatnonzero((s == lo).values)] + [(p, "H", c[p]) for p in np.flatnonzero((s == hi).values)]
    pts.sort(); out = []
    for p in pts:                                   # alternate L/H, keep the more extreme of repeats
        if out and out[-1][1] == p[1]:
            if (p[1] == "L" and p[2] < out[-1][2]) or (p[1] == "H" and p[2] > out[-1][2]): out[-1] = p
        else: out.append(p)
    return out
IHS, DB, HS = np.zeros((D, N), bool), np.zeros((D, N), bool), np.zeros((D, N), bool)
near = lambda a, b, tol: abs(a - b) / ((a + b) / 2) <= tol
t_piv = time.time()
for j in range(N):
    c = Cf[:, j]
    if np.isnan(c).mean() > 0.9: continue
    pv = [p for p in pivots(np.nan_to_num(c, nan=-1.0)) if p[2] > 0]
    for k in range(len(pv)):
        # double bottom: L1 H L2
        if k >= 2 and pv[k][1] == "L":
            (a, _, l1), (b, _, h), (e, _, l2) = pv[k - 2], pv[k - 1], pv[k]
            if near(l1, l2, 0.03) and 15 <= e - a <= 90 and h >= 1.10 * max(l1, l2):
                for t in range(e + W, min(e + W + 30, D)):
                    if c[t] > h: DB[t, j] = True; break
                    if c[t] < min(l1, l2) * 0.97: break
        if k >= 4:
            (p1, k1, a1), (p2, _, a2), (p3, _, a3), (p4, _, a4), (p5, _, a5) = pv[k - 4:k + 1]
            if p5 - p1 > 120: continue
            if k1 == "L" and a3 < min(a1, a5) * 0.97 and near(a1, a5, 0.05) and near(a2, a4, 0.05):          # inverse H&S
                neck = max(a2, a4)
                for t in range(p5 + W, min(p5 + W + 30, D)):
                    if c[t] > neck: IHS[t, j] = True; break
                    if c[t] < a3: break
            if k1 == "H" and a3 > max(a1, a5) * 1.03 and near(a1, a5, 0.05) and near(a2, a4, 0.05):          # H&S top
                neck = min(a2, a4)
                for t in range(p5 + W, min(p5 + W + 30, D)):
                    if c[t] < neck: HS[t, j] = True; break
                    if c[t] > a3: break
P["inverse head & shoulders"] = IHS; P["double bottom"] = DB; P["head & shoulders top (bearish)"] = HS
print(f"pivot patterns {time.time() - t_piv:.0f}s", flush=True)
for k in P: P[k] = first_in(P[k] & ELIG & (np.arange(D)[:, None] >= t0))

# ---------------- planted check: add +6% over the 20 days after each bull flag, then recompute nothing but returns
if DRY == "planted":
    for t, j in zip(*np.nonzero(P["bull flag"])):
        k = min(20, D - 1 - t); C[t + 1:t + 1 + k, j] *= 1 + 0.06 * np.arange(1, k + 1) / 20
        C[t + 1 + k:, j] *= 1.06
    Cf = F(C).ffill(limit=5).values

# ---------------- forward returns vs the average eligible stock and vs SPY
H = (5, 20, 60)
FWD, BENCH = {}, {}
with np.errstate(all="ignore"):
    for h in H:
        fr = np.vstack([Cf[h:], np.full((h, N), np.nan)]) / Cf - 1
        FWD[h] = fr; BENCH[h] = np.nanmean(np.where(ELIG, fr, np.nan), axis=1)
        BENCH[f"spy{h}"] = np.r_[SP[h:] / SP[:-h] - 1, np.full(h, np.nan)]

def evstats(ts, js, mask_extra=None):
    out = {"events": int(len(ts))}
    if len(ts) == 0: return out
    for h in H:
        x = FWD[h][ts, js] - 2 * cost[ts, js]; b = BENCH[h][ts]; s = BENCH[f"spy{h}"][ts]
        ok = np.isfinite(x) & np.isfinite(b)
        if ok.sum() < 5: continue
        ex = pd.Series(x[ok] - b[ok]).groupby(ts[ok]).mean()            # one number per day
        out[f"{h}d"] = {"avg_pct": round(float(np.mean(x[ok])) * 100, 2), "vs_avg_stock_pct": round(float(np.mean(x[ok] - b[ok])) * 100, 2),
                        "vs_spy_pct": round(float(np.nanmean(x[ok] - s[ok])) * 100, 2), "win_vs_avg_pct": round(float(np.mean(x[ok] > b[ok])) * 100, 1),
                        "t_stat_days": round(float(ex.mean() / (ex.std() / np.sqrt(len(ex)))) if len(ex) > 2 and ex.std() > 0 else 0.0, 2)}
    return out
year = np.array([int(str(d)[:4]) for d in dn])
RES = {}
for name, sig in P.items():
    ts, js = np.nonzero(sig); r = {"all": evstats(ts, js)}
    for hn, a, b in HALVES:
        m = (dn[ts] >= np.datetime64(a)) & (dn[ts] < np.datetime64(b)); r[hn] = evstats(ts[m], js[m])
    if U == "us_all" or DRY:
        for si, sn in enumerate(SIZE_NAMES):
            m = size[ts, js] == si; r[sn] = evstats(ts[m], js[m])
    r["per_year"] = round(len(ts) / max(1e-9, (D - t0) / 252), 1)
    RES[name] = r; a = r["all"]
    line = " | ".join(f"{h}d {a[f'{h}d']['vs_avg_stock_pct']:+.2f}% (t {a[f'{h}d']['t_stat_days']:+.1f})" for h in H if f"{h}d" in a)
    halves = " | ".join(f"{hn} 20d {r[hn].get('20d', {}).get('vs_avg_stock_pct', 'na')}" for hn, _, _ in HALVES)
    print(f"{name:32s} n={a['events']:6d} ({r['per_year']}/yr) vs avg stock after costs: {line} || {halves}", flush=True)
    if U == "us_all" or DRY:
        print("    by size (20d vs avg stock):", " | ".join(f"{sn.split()[0]} n={r[sn]['events']} {r[sn].get('20d', {}).get('vs_avg_stock_pct', 'na')}" for sn in SIZE_NAMES), flush=True)

# ---------------- simple bot per pattern: 10 slots x 10%, hold 20 days, idle money in SPY when SPY > 100-day avg
spyr = np.r_[0, SP[1:] / SP[:-1] - 1]; park_on = np.r_[False, (pd.Series(SP) > pd.Series(SP).rolling(100).mean()).values[:-1]]
def sim(sig, hold=20, slots=10, w=0.10):
    pos, eq, curve, ntr = [], 1.0, np.ones(D), 0
    for t in range(t0, D):
        r = sum(w * (Cf[t, j] / Cf[t - 1, j] - 1) for j, _ in pos if np.isfinite(Cf[t, j]) and np.isfinite(Cf[t - 1, j]))
        if park_on[t]: r += (1 - w * len(pos)) * spyr[t]
        eq *= 1 + r; keep = []
        for j, e in pos:
            if t - e >= hold or not np.isfinite(Cf[t, j]): eq *= 1 - w * cost[e, j]; ntr += 1
            else: keep.append((j, e))
        pos = keep; held = {j for j, _ in pos}
        for j in np.flatnonzero(sig[t]):
            if len(pos) >= slots: break
            if j not in held: pos.append((j, t)); eq *= 1 - w * cost[t, j]
        curve[t] = eq
    out = {}
    for hn, a, b in (("all", START, "2100-01-01"),) + HALVES:
        ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
        if len(ix) < 60: continue
        cv = curve[ix] / curve[ix[0]]; y = len(ix) / 252
        out[hn] = {"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
                   "spy_pct": round(((SP[ix[-1]] / SP[ix[0]]) ** (1 / y) - 1) * 100, 1)}
    out["trades"] = ntr
    return out
BOT = {}
# fair baseline: same bot buying RANDOM eligible stocks (~3 picks a day), 3 seeds -> what any stock-picking bot in this universe earns
rb = []
for seed in (1, 2, 3):
    g = np.random.default_rng(seed); RS = (g.random((D, N)) < 3.0 / max(1, np.nanmean(ELIG.sum(axis=1)))) & ELIG
    rb.append(sim(RS))
BOT["RANDOM picks (baseline)"] = {k: {kk: round(float(np.mean([r[k][kk] for r in rb])), 1) for kk in rb[0][k]} for k in rb[0] if k != "trades"}
b = BOT["RANDOM picks (baseline)"]
print(f"BOT {'RANDOM picks (baseline)':32s} {b['all']['per_year_pct']}%/yr (SPY {b['all']['spy_pct']}%) worst {b['all']['worst_drop_pct']}% | " + " | ".join(f"{hn} {b[hn]['per_year_pct']}%" for hn, _, _ in HALVES if hn in b), flush=True)
for name, sig in P.items():
    if "bearish" in name: continue
    BOT[name] = b = sim(sig)
    print(f"BOT {name:32s} {b['all']['per_year_pct']}%/yr (SPY {b['all']['spy_pct']}%) worst {b['all']['worst_drop_pct']}% | " + " | ".join(f"{hn} {b[hn]['per_year_pct']}% vs SPY {b[hn]['spy_pct']}%" for hn, _, _ in HALVES if hn in b), flush=True)

json.dump({"note": __doc__, "universe": U, "dry": DRY or None, "built": str(pd.Timestamp.today().date()), "start": START,
           "stocks": N, "patterns": RES, "bot_hold20": BOT}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
