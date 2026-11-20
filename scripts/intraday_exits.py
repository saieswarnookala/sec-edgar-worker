"""Checking during the day (Nov 19 2026): sell when a dip bounces intraday, profit targets, lock-ins, and buying dips during the
day instead of only at 3:45 pm. Research only, not financial advice.
Replays 2016-2026 on Alpaca SIP 5-minute bars (9:30-16:00 ET) for every stock/ETF near a signal and every held position.
Base = the live bot: decide with the 15:45 price, fill at the 15:45-15:50 bar's close; 0.05% per side (also 0.10%).
Exit variants (a stock must have been held at least 1 trading day; the normal 3:45 check always runs too):
  CHECK n   - every n minutes (5/15/30): sell as soon as the price is above the 5-day average (4 prior closes + current price)
  TARGET x  - every 5 minutes: sell as soon as the price is x% above the buy price (2/3/5%)
  LOCK      - every 5 minutes: once above the 5-day average, sell if it falls back below it, or y% below the day's high since (1/2%)
Entry variant: INTRADAY BUY - every 15 minutes from 10:00, buy a stock/ETF the moment it meets the dip rules (else wait for 3:45).
A stock sold during the day frees its slot for that day's 3:45 buys. Idle money (Clear Leader / IEF / cash) uses daily closes.
Prices: 5-minute raw bars scaled to the adjusted daily series with the stock's own move to its last bar of the day; minute data
more than 3% away from the S&P data's raw close is treated as bad and that day uses the daily close (counted).
Bars cached in R2 (alpaca/m5day/<YYYY-MM>.json.gz). DRY=1: fake intraday paths (no network): a code test only - fake paths pinned to the real close are NOT a fair null test
(an intraday rule can 'see' noise around a known close); the real-data check is the PLACEBO version (sell at a random time)."""
import os, sys, json, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
import r2cache
DRY = S.DRY; OUT = os.environ.get("OUT_FILE") or ("data/intraday_exits.json" if not DRY else "/tmp/intraday_exits_dry.json")
ET, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
tr0 = max(S.t0, int(np.searchsorted(S.dn, np.datetime64(os.environ.get("START", "2016-01-04"))))); D, dn = S.D, S.dn; ds = [str(d)[:10] for d in dn]
def asym(t):
    b = t.rsplit("-", 1)[0] if len(t) > 7 and t[-7] == "-" and t[-6:].isdigit() else t
    return b.replace("-", ".")
ex5c = np.nan_to_num(S.ex5.values, nan=1)
# stocks that were dips at ANY time of the day: close-based gap <= -6%, or the day's LOW at least 8% below 5 days ago vs SPY
_lo = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "low", "close", "adj_close"]); _lo["date"] = pd.to_datetime(_lo.date)
_lo = _lo[_lo.ticker.isin(S.tick) & (_lo.date >= S.dates[0])]; _lo["alow"] = _lo.low * _lo.adj_close / _lo.close
LOWA = _lo.pivot_table(index="date", columns="ticker", values="alow").reindex(index=S.dates, columns=S.tick).values; del _lo
spy5r = np.r_[np.full(5, np.nan), S.SP[5:] / S.SP[:-5] - 1]
lowgap = np.nan_to_num(LOWA / np.vstack([np.full((5, S.S_C.shape[1]), np.nan), S.S_C[:-5]]) - 1 - spy5r[:, None], nan=1)
NEAR = S.M.values & ((ex5c <= -0.06) | (lowgap <= -0.08)) & (np.nan_to_num(S.RAW[S.tick].values, nan=0) >= 4)
E5 = np.nan_to_num(S.E_C / np.vstack([np.full((5, S.E_C.shape[1]), np.nan), S.E_C[:-5]]) - 1, nan=1)
NEARE = E5 <= -0.03
need = {t: {"SPY"} for t in range(tr0, D)}
for t, j in zip(*np.nonzero(NEAR[tr0:])):
    for k in range(t + tr0, min(t + tr0 + 8, D)): need[k].add(S.tick[j])
for t, j in zip(*np.nonzero(NEARE[tr0:])):
    for k in range(t + tr0, min(t + tr0 + 13, D)): need[k].add("ETF:" + S.EN[j])
print("days", D - tr0, "| symbol-days", sum(len(v) for v in need.values()), flush=True)
H = {"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""), "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", "")}
RATE = float(os.environ.get("RATE_PER_MIN", "150")); _last = [0.0]; CALLS = [0]
def get(url):
    for i in range(10):
        w = 60.0 / RATE - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.time(); CALLS[0] += 1
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120))
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(min(120, 15 * (i + 1))); continue
            if e.code in (400, 403, 404, 422): print("HTTP", e.code, e.read()[:200], flush=True); return None
            time.sleep(5 * (i + 1))
        except Exception: time.sleep(3 * (i + 1))
    return None
def mins(t): return t.hour * 60 + t.minute
def fetch_day(day, syms):
    a = datetime.fromisoformat(day + "T09:30:00").replace(tzinfo=ET).astimezone(UTC); b = datetime.fromisoformat(day + "T16:00:00").replace(tzinfo=ET).astimezone(UTC)
    out, syms = {}, sorted(syms)
    for i in range(0, len(syms), 100):
        p = {"symbols": ",".join(syms[i:i + 100]), "timeframe": "5Min", "start": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": b.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "adjustment": "raw", "feed": "sip", "limit": "10000"}; tok = None
        while True:
            if tok: p["page_token"] = tok
            js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p))
            if not js: break
            for s, bars in (js.get("bars") or {}).items():
                for x in bars:
                    m = mins(datetime.fromisoformat(x["t"].replace("Z", "+00:00")).astimezone(ET))
                    if 570 <= m < 960: out.setdefault(s, [None] * 78)[(m - 570) // 5] = round(x["c"], 4)
            tok = js.get("next_page_token")
            if not tok: break
    return out
# FETCH_VOL=1: download-only job - 5-minute VOLUME for the same stock-days into R2 (alpaca/m5vol/<YYYY-MM>), for a fair
# intraday volume filter later (only the volume known at that time of day). Shares the Alpaca limit with other jobs: run slower.
if os.environ.get("FETCH_VOL") == "1":
    def fetch_vol(day, syms):
        a = datetime.fromisoformat(day + "T09:30:00").replace(tzinfo=ET).astimezone(UTC); b = datetime.fromisoformat(day + "T16:00:00").replace(tzinfo=ET).astimezone(UTC)
        out, syms = {}, sorted(syms)
        for i in range(0, len(syms), 100):
            p = {"symbols": ",".join(syms[i:i + 100]), "timeframe": "5Min", "start": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": b.strftime("%Y-%m-%dT%H:%M:%SZ"), "adjustment": "raw", "feed": "sip", "limit": "10000"}; tok = None
            while True:
                if tok: p["page_token"] = tok
                js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p))
                if not js: break
                for s_, bars in (js.get("bars") or {}).items():
                    for x in bars:
                        m = mins(datetime.fromisoformat(x["t"].replace("Z", "+00:00")).astimezone(ET))
                        if 570 <= m < 960: out.setdefault(s_, [0] * 78)[(m - 570) // 5] = int(x.get("v") or 0)
                tok = js.get("next_page_token")
                if not tok: break
        return out
    fetched = 0
    for mo in sorted({d[:7] for d in ds[tr0:]}):
        cache = r2cache.load(f"alpaca/m5vol/{mo}.json.gz") or {}; changed = False
        for t in [t for t in range(tr0, D) if ds[t][:7] == mo]:
            day = ds[t]; have = cache.get(day, {}); none = set(have.get("_none", []))
            want = {asym(x) for x in need[t] if not x.startswith("ETF:")}
            miss = [x for x in want if x not in have and x not in none]
            if miss:
                got = fetch_vol(day, miss); fetched += 1; have.update(got); have["_none"] = sorted(none | {x for x in miss if x not in got}); cache[day] = have; changed = True
        if changed: r2cache.save(f"alpaca/m5vol/{mo}.json.gz", cache)
        print(mo, "volume days fetched", fetched, "calls", CALLS[0], flush=True)
    print("volume download done", flush=True); raise SystemExit(0)
BARS = {}
if DRY:
    rng = np.random.default_rng(9)
    for t in range(tr0, D):
        BARS[ds[t]] = {}
        for s in need[t]:
            w = np.cumsum(rng.normal(0, 0.003, 78)); bridge = w - np.arange(1, 79) / 78 * w[-1]          # pinned to the close at 16:00
            BARS[ds[t]][s.replace("ETF:", "")] = (100 * np.exp(bridge)).astype(np.float32)
else:
    fetched = 0
    for mo in sorted({d[:7] for d in ds[tr0:]}):
        cache = r2cache.load(f"alpaca/m5day/{mo}.json.gz") or {}; changed = False
        for t in [t for t in range(tr0, D) if ds[t][:7] == mo]:
            day = ds[t]; have = cache.get(day, {}); none = set(have.get("_none", []))
            want = {asym(s) if not s.startswith("ETF:") else s[4:] for s in need[t]}
            miss = [s for s in want if s not in have and s not in none]
            if miss:
                got = fetch_day(day, miss); fetched += 1; have.update(got); have["_none"] = sorted(none | {s for s in miss if s not in got}); cache[day] = have; changed = True
            BARS[day] = {k: np.array([np.nan if v is None else v for v in arr], dtype=np.float32) for k, arr in have.items() if k != "_none" and isinstance(arr, list) and len(arr) == 78}
        if changed: r2cache.save(f"alpaca/m5day/{mo}.json.gz", cache)
        print(mo, "days fetched", fetched, "calls", CALLS[0], flush=True)
# ---------------- prices on the adjusted scale: px(t, key, minute) = price at that clock time; fill = close of the next 5-min bar
RAWC = S.RAW[S.tick].values; BAD = [0, 0]; SER = {}
def series(t, key, adj_close, raw_close):
    k = (t, key)
    if k in SER: return SER[k]
    BAD[1] += 1
    bars = BARS.get(ds[t], {}).get(key)
    if bars is None or not np.isfinite(adj_close): BAD[0] += 1; SER[k] = None; return None
    ok = np.isfinite(bars)
    if ok.sum() < 10: BAD[0] += 1; SER[k] = None; return None
    m = (575 + 5 * np.flatnonzero(ok)).astype(np.int32); c = bars[ok].astype(np.float64); last = c[-1]   # m = bar END minute
    if not DRY and raw_close is not None and np.isfinite(raw_close) and raw_close > 0 and abs(last / raw_close - 1) > 0.03: BAD[0] += 1; SER[k] = None; return None
    c = c * adj_close / last
    SER[k] = (m, c); return SER[k]
def px_at(t, kind, j, minute, fill=False):
    adj = (S.S_C if kind != "E" else S.E_C)[t, j]
    s = series(t, asym(S.tick[j]) if kind != "E" else S.EN[j], adj, RAWC[t, j] if kind != "E" else None)
    if s is None: return adj if minute >= 945 else None
    m, c = s
    if fill:
        i = np.searchsorted(m, minute + 5)                              # first bar ending at or after minute+5
        return float(c[min(i, len(c) - 1)])
    i = np.searchsorted(m, minute, side="right") - 1
    return float(c[i]) if i >= 0 else None
VOLOK = (np.nan_to_num(S.vr.values, nan=9) <= 2.0) & (np.nan_to_num(RAWC, nan=0) >= 5) & S.M.values
# FAIR_VOL=1: the volume filter uses only what is known at that moment, exactly like the live bot: today's volume so far
# (5-minute bars from R2 alpaca/m5vol) scaled to a full day with the live bot's intraday curve, averaged with the 4 prior days,
# over the 50 days before them. Price/membership checks unchanged.
FAIR = os.environ.get("FAIR_VOL") == "1"
VOL_CURVE = [(570, 0), (600, 0.12), (660, 0.25), (720, 0.35), (780, 0.43), (840, 0.52), (900, 0.64), (930, 0.74), (960, 1)]
def vol_fraction(m):
    if m <= 570: return 0.0
    if m >= 960: return 1.0
    for (m0, f0), (m1, f1) in zip(VOL_CURVE, VOL_CURVE[1:]):
        if m <= m1: return f0 + (f1 - f0) * (m - m0) / (m1 - m0)
    return 1.0
VRAW = S.VOLM[S.tick].values; VB = {}; VSTAT = [0, 0, 0]       # [checked, used today's volume so far, no intraday volume -> full-day filter]
if FAIR and not DRY:
    for mo in sorted({d[:7] for d in ds[tr0:]}):
        c = r2cache.load(f"alpaca/m5vol/{mo}.json.gz") or {}
        for day, h in c.items(): VB[day] = {k: np.array(v, dtype=np.float64) for k, v in h.items() if k != "_none" and isinstance(v, list) and len(v) == 78}
    print("fair volume: days with 5-minute volume", len(VB), flush=True)
def vol_ok(t, j, T):
    if not FAIR: return bool(VOLOK[t, j])
    if not ((np.nan_to_num(RAWC[t, j], nan=0) >= 5) and S.M.values[t, j]): return False
    VSTAT[0] += 1
    v = VB.get(ds[t], {}).get(asym(S.tick[j]))
    if v is None: VSTAT[2] += 1; return bool(VOLOK[t, j])
    so_far = v[: max(0, (T - 570) // 5)].sum(); fr = vol_fraction(T)
    if fr < 0.2 or so_far <= 0: return bool(np.nan_to_num(S.vr.values[t, j], nan=9) <= 2.0) if T >= 945 else True   # too early to judge: live skips the filter
    VSTAT[1] += 1
    prior = VRAW[t - 54:t, j]
    if len(prior) < 54 or not np.isfinite(prior).all(): return True
    base = prior[:50].mean(); recent = (prior[-4:].sum() + so_far / fr) / 5
    return base <= 0 or recent / base <= 2.0
def run(exit_mode="base", n=15, x=0.03, y=0.01, intraday_buy=False, bn=15, seed=1, no_rebuy=False, etf=False, bond=False, cs=0.0005, ce=0.0002, cp=0.0005):
    cash, pos, curve, held_park, trades = 1.0, [], np.ones(D), "CASH", []
    prng = np.random.default_rng(seed)
    early_sells = [0]; early_buys = [0]
    for t in range(tr0, D):
        want = "SPY" if S.park_on[t] else ("IEF" if bond and S.BOND_OK[t] else "CASH")
        if want != held_park: cash *= 1 - cp * ((held_park != "CASH") + (want != "CASH")); held_park = want
        cash *= 1 + (S.CLR[t] if held_park == "SPY" else (S.BOND_R[t] if held_park == "IEF" else 0.0))
        for p in pos: p["ref"] = (S.S_C if p["k"] != "E" else S.E_C)[t - 1, p["j"]]; p["armed"] = False; p["hi"] = 0.0
        sold_today = set()
        checks = list(range(575, 945, 5)) if exit_mode in ("target", "lock", "placebo") or (exit_mode == "check" and n == 5) else \
                 (list(range(570 + n, 945, n)) if exit_mode == "check" else [])
        buy_checks = list(range(600, 945, bn)) if intraday_buy else []
        times = sorted(set(checks) | set(buy_checks) | {945})
        spy5_ref = S.SP[t - 5]
        for T in times:
            final = T == 945
            # exits
            keep = []
            for p in pos:
                Cx = S.S_C if p["k"] != "E" else S.E_C; j = p["j"]; age = t - p["d"]; mh = 5 if p["k"] == "S" else 10
                now = px_at(t, p["k"], j, T)
                if now is None or age < 1: keep.append(p); continue
                m5 = np.mean(np.r_[Cx[t - 4:t, j], now]); out = False
                if final: out = now > m5 or age >= mh
                elif T in checks:
                    if exit_mode == "check": out = now > m5
                    elif exit_mode == "target": out = now >= p["px"] * (1 + x)
                    elif exit_mode == "placebo": out = prng.random() < 1 / 74 * 1.3     # sells at a random time of day, about as often as 'check'
                    elif exit_mode == "lock":
                        if now > m5: p["armed"] = True
                        if p["armed"]:
                            p["hi"] = max(p["hi"], now); out = now < m5 or now < p["hi"] * (1 - y)
                if out:
                    f = px_at(t, p["k"], j, T, fill=True)
                    f = f if f is not None and np.isfinite(f) else Cx[t, j]
                    c = cs if p["k"] != "E" else ce
                    cash += p["v"] * (f / p["ref"]) * (1 - c); trades.append(f / p["px"] - 1 - 2 * c)
                    if not final: early_sells[0] += 1
                    sold_today.add((p["k"], j))
                else: keep.append(p)
            pos = keep
            # entries (3:45 always; intraday every 15 minutes if on)
            if final or T in buy_checks:
                spys = series(t, "SPY", S.SP[t], S.RAW["SPY"].values[t]); spx = (float(spys[1][np.searchsorted(spys[0], T, side='right') - 1]) if spys is not None and np.searchsorted(spys[0], T, side='right') > 0 else (S.SP[t] if final else None))
                if spx is None: continue
                spy5 = spx / spy5_ref - 1; held = {(p["k"], p["j"]) for p in pos} | (sold_today if no_rebuy else set())
                eq_now = cash + sum(p["v"] for p in pos)
                cand = []
                for j in np.flatnonzero(NEAR[t] & (S.M.values[t] if FAIR else VOLOK[t])):
                    if FAIR and not vol_ok(t, j, T): continue
                    if ("S", j) in held: continue
                    now = px_at(t, "S", j, T)
                    if now is None: continue
                    g5 = now / S.S_C[t - 5, j] - 1 - spy5
                    if g5 <= -0.10 and now > np.mean(np.r_[S.S_C[t - 199:t, j], now]): cand.append((g5, "S", j))
                cand.sort(key=lambda z: z[0])
                ce_ = []
                if etf:
                    for j in np.flatnonzero(NEARE[t]):
                        if ("E", j) in held: continue
                        now = px_at(t, "E", j, T)
                        if now is not None and now / S.E_C[t - 5, j] - 1 <= -0.05 and now > np.mean(np.r_[S.E_C[t - 199:t, j], now]): ce_.append((now / S.E_C[t - 5, j] - 1, "E", j))
                    ce_.sort(key=lambda z: z[0])
                for _, k, j in cand + ce_:
                    if len(pos) >= 10: break
                    f = px_at(t, k, j, T, fill=True)
                    if f is None or not np.isfinite(f) or f <= 0: continue
                    a = min(0.10 * eq_now, cash); c = cs if k == "S" else ce
                    if a < 0.02 * eq_now: break
                    cash -= a; pos.append({"k": k, "j": j, "d": t, "px": f, "v": a * (1 - c), "ref": f, "armed": False, "hi": 0.0}); held.add((k, j))
                    if not final: early_buys[0] += 1
        for p in pos:                                                    # mark to the close
            Cx = S.S_C if p["k"] != "E" else S.E_C; p["v"] *= Cx[t, p["j"]] / p["ref"]; p["ref"] = Cx[t, p["j"]]
        curve[t] = cash + sum(p["v"] for p in pos)
    ix = np.arange(tr0, D); cv = curve[ix] / curve[tr0 - 1]; y_ = len(ix) / 252
    o = {"per_year_pct": round((cv[-1] ** (1 / y_) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
         "trades_per_month": round(len(trades) / (y_ * 12), 1), "avg_trade_pct": round(float(np.mean(trades)) * 100, 2) if trades else None,
         "win_pct": round(float(np.mean(np.array(trades) > 0)) * 100) if trades else None,
         "sold_during_day_per_month": round(early_sells[0] / (y_ * 12), 1), "bought_during_day_per_month": round(early_buys[0] / (y_ * 12), 1)}
    for name, a_, b_ in (("2016-2020", "2016-01-01", "2021-01-01"), ("2021-2026", "2021-01-01", "2100-01-01")):
        jj = np.flatnonzero((dn[ix] >= np.datetime64(a_)) & (dn[ix] < np.datetime64(b_)))
        c2 = cv[jj] / (cv[jj[0] - 1] if jj[0] > 0 else 1); o[name] = round((c2[-1] ** (252 / len(jj)) - 1) * 100, 1)
    return o
V = []
for bot, kw in (("Robinhood rules", {}), ("v3.0", dict(etf=True, bond=True))):
    V += [(f"{bot} | base: 3:45 only", dict(**kw)), (f"{bot} | base, 0.10% per side", dict(cs=0.001, ce=0.0004, **kw)),
          (f"{bot} | PLACEBO: sell at a random time of day", dict(exit_mode="placebo", **kw))]
    for bn in (15, 30, 60): V.append((f"{bot} | buy dips during the day, every {bn} min", dict(intraday_buy=True, bn=bn, **kw)))
    V.append((f"{bot} | buy during the day (15 min), 0.10% per side", dict(intraday_buy=True, bn=15, cs=0.001, ce=0.0004, **kw)))
    for x in (0.05, 0.07, 0.10): V.append((f"{bot} | profit target +{int(x*100)}%", dict(exit_mode="target", x=x, **kw)))
    for x in (0.05, 0.07): V.append((f"{bot} | buy during the day (15 min) + target +{int(x*100)}%", dict(intraday_buy=True, bn=15, exit_mode="target", x=x, **kw)))
    V.append((f"{bot} | buy during the day (15 min) + target +5%, 0.10% per side", dict(intraday_buy=True, bn=15, exit_mode="target", x=0.05, cs=0.001, ce=0.0004, **kw)))
RES = {}
for name, kw in V:
    RES[name] = run(**kw); a = RES[name]
    print(f"{name:62s} {a['per_year_pct']}%/yr worst {a['worst_drop_pct']}% | 16-20 {a['2016-2020']} 21-26 {a['2021-2026']} | {a['trades_per_month']}/mo avg {a['avg_trade_pct']}% win {a['win_pct']}% | early sells {a['sold_during_day_per_month']}/mo buys {a['bought_during_day_per_month']}/mo", flush=True)
print(f"5-minute series: {BAD[1]} looked up, {BAD[0]} fell back to the daily close", flush=True)
if FAIR: print(f"fair volume filter: {VSTAT[0]} checks, {VSTAT[1]} used today's volume so far, {VSTAT[2]} had no 5-minute volume (full-day filter)", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "period_start": ds[tr0], "fallbacks": BAD, "fair_volume": FAIR, "fair_volume_stats": VSTAT, "alpaca_calls": CALLS[0], "results": RES},
          open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
