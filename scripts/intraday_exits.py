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
(an intraday rule can 'see' noise around a known close); the real-data check is the PLACEBO version (sell at a random time).
Nov 19 final-run fixes: (a) idle money is valued at the time of day it is spent or comes back (the parked ETF's own 5-minute
bars; IEF/SPY fallback), not at the close; (b) ETFs that dipped only during the day are included (Yahoo daily lows);
(c) the stock list is a strict superset of every possible intraday dip: day's LOW vs SPY's day HIGH (no SPY-close shortcut);
(d) half-days: the 3:45 decision moves to 15 minutes before the early close; (e) calendar-year returns for every version."""
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
# stocks that could have been dips at ANY time of the day: close-based gap <= -6%, or (day's LOW vs 5 days ago) minus (SPY's day
# HIGH vs 5 days ago) <= -9.5%. Any moment's gap is >= that number, so this cannot miss an intraday -10% dip (0.5% slack for data).
_lo = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "low", "high", "close", "adj_close"]); _lo["date"] = pd.to_datetime(_lo.date)
_lo = _lo[_lo.ticker.isin(S.tick + ["SPY"]) & (_lo.date >= S.dates[0])]; _lo["alow"] = _lo.low * _lo.adj_close / _lo.close; _lo["ahigh"] = _lo.high * _lo.adj_close / _lo.close
LOWA = _lo.pivot_table(index="date", columns="ticker", values="alow").reindex(index=S.dates, columns=S.tick).values
_sh = _lo[_lo.ticker == "SPY"].set_index("date").ahigh.reindex(S.dates).values; del _lo
_sh = np.where(np.isfinite(_sh), _sh, S.SP)
spy5r = np.r_[np.full(5, np.nan), _sh[5:] / S.SP[:-5] - 1]
lowgap = np.nan_to_num(LOWA / np.vstack([np.full((5, S.S_C.shape[1]), np.nan), S.S_C[:-5]]) - 1 - spy5r[:, None], nan=1)
DIP_MIN = float(os.environ.get("DIP_MIN", "0.10"))       # smallest dip size tested (COMBO run: 0.09) -> candidate list widened to match
NEAR = S.M.values & ((ex5c <= -0.06) | (lowgap <= -(DIP_MIN - 0.005))) & (np.nan_to_num(S.RAW[S.tick].values, nan=0) >= 4)
E5 = np.nan_to_num(S.E_C / np.vstack([np.full((5, S.E_C.shape[1]), np.nan), S.E_C[:-5]]) - 1, nan=1)
EL5 = np.nan_to_num(S.E_L / np.vstack([np.full((5, S.E_C.shape[1]), np.nan), S.E_C[:-5]]) - 1, nan=1)   # ETF day's low vs 5 days ago
NEARE = (E5 <= -0.03) | (EL5 <= -0.045)
_old = S.M.values & ((ex5c <= -0.06) | (np.nan_to_num(LOWA / np.vstack([np.full((5, S.S_C.shape[1]), np.nan), S.S_C[:-5]]) - 1 - np.r_[np.full(5, np.nan), S.SP[5:] / S.SP[:-5] - 1][:, None], nan=1) <= -0.08)) & (np.nan_to_num(S.RAW[S.tick].values, nan=0) >= 4)
print("candidate stock-days", int(NEAR[tr0:].sum()), "(old list", int(_old[tr0:].sum()), "| new ones not in the old list", int((NEAR & ~_old)[tr0:].sum()), ")", "| ETF-days", int(NEARE[tr0:].sum()), "(of which only by the day's low:", int(((EL5 <= -0.045) & (E5 > -0.03))[tr0:].sum()), ")", flush=True)
need = {t: {"SPY"} for t in range(tr0, D)}
for t, j in zip(*np.nonzero(NEAR[tr0:])):
    for k in range(t + tr0, min(t + tr0 + 8, D)): need[k].add(S.tick[j])
for t, j in zip(*np.nonzero(NEARE[tr0:])):
    for k in range(t + tr0, min(t + tr0 + 13, D)): need[k].add("ETF:" + S.EN[j])
for t in range(tr0, D): need[t] |= {"ETF:" + (S.CL_POS[t] if S.park_on[t] else "IEF")} - {"ETF:SPY"}     # the parked ETF, for time-of-day value
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
                    if 570 <= m < 960: out.setdefault(s, [None] * 78)[(m - 570) // 5] = round(x["c"], 4); VOUT.setdefault(s, [0] * 78)[(m - 570) // 5] = int(x.get("v") or 0)
            tok = js.get("next_page_token")
            if not tok: break
    return out
VOUT = {}
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
        cache = r2cache.load(f"alpaca/m5day/{mo}.json.gz") or {}; changed = False; vnew = {}
        for t in [t for t in range(tr0, D) if ds[t][:7] == mo]:
            day = ds[t]; have = cache.get(day, {}); none = set(have.get("_none", []))
            want = {asym(s) if not s.startswith("ETF:") else s[4:] for s in need[t]}
            miss = [s for s in want if s not in have and s not in none]
            if miss:
                VOUT.clear(); got = fetch_day(day, miss); fetched += 1; have.update(got); have["_none"] = sorted(none | {s for s in miss if s not in got}); cache[day] = have; changed = True
                if VOUT: vnew[day] = dict(VOUT)
            BARS[day] = {k: np.array([np.nan if v is None else v for v in arr], dtype=np.float32) for k, arr in have.items() if k != "_none" and isinstance(arr, list) and len(arr) == 78}
        if changed: r2cache.save(f"alpaca/m5day/{mo}.json.gz", cache)
        if vnew:
            vc = r2cache.load(f"alpaca/m5vol/{mo}.json.gz") or {}
            for day, h in vnew.items(): vc.setdefault(day, {}).update(h)
            r2cache.save(f"alpaca/m5vol/{mo}.json.gz", vc)
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
FINC = {}
def fin_of(t):
    """the 3:45 decision minute: 15 minutes before the day's last SPY bar ends (half-days close at 13:00)"""
    if t in FINC: return FINC[t]
    b = BARS.get(ds[t], {}).get("SPY"); f = 945
    if b is not None and np.isfinite(b).sum() >= 10:
        end = 575 + 5 * int(np.flatnonzero(np.isfinite(b))[-1])
        if end <= 900: f = end - 15
    FINC[t] = f; return f
def ratio_at(t, sym, T):
    """price at clock time T / the day's last 5-minute close, from raw bars (None if missing or odd)"""
    b = BARS.get(ds[t], {}).get(sym)
    if b is None: return None
    ok = np.flatnonzero(np.isfinite(b))
    if len(ok) < 10: return None
    m = 575 + 5 * ok; i = np.searchsorted(m, T, side="right") - 1
    if i < 0: return None
    r = float(b[ok[i]] / b[ok[-1]]); return r if 0.85 < r < 1.15 else None
PSTAT = [0, 0, 0]   # parking value lookups: own ETF bars, SPY bars as stand-in, straight line
def park_f(t, held, T):
    """value at clock time T of 1 dollar parked at yesterday's close (equals 1 + the day's return at the decision time's close)"""
    if held == "CASH": return 1.0
    r = S.CLR[t] if held == "SPY" else S.BOND_R[t]
    if T >= 960: return 1 + r
    sym = (S.CL_POS[t] if held == "SPY" else "IEF")
    q = ratio_at(t, sym, T)
    if q is not None: PSTAT[0] += 1; return (1 + r) * q
    if held == "SPY" and (q := ratio_at(t, "SPY", T)) is not None: PSTAT[1] += 1; return (1 + r) * q
    PSTAT[2] += 1; return 1 + r * max(0, T - 570) / 390
def px_at(t, kind, j, minute, fill=False):
    adj = (S.S_C if kind != "E" else S.E_C)[t, j]
    s = series(t, asym(S.tick[j]) if kind != "E" else S.EN[j], adj, RAWC[t, j] if kind != "E" else None)
    if s is None: return adj if minute >= fin_of(t) else None
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
def vol_ratio(t, j, T):
    """5-day volume / prior 50-day volume as known at minute T (FAIR) or for the full day; None = not known yet (live skips the filter)."""
    full = float(np.nan_to_num(S.vr.values[t, j], nan=9))
    if not FAIR: return full
    v = VB.get(ds[t], {}).get(asym(S.tick[j]))
    if v is None: VSTAT[2] += 1; return full
    so_far = v[: max(0, (T - 570) // 5)].sum(); fr = vol_fraction(T)
    if fr < 0.2 or so_far <= 0: return full if T >= fin_of(t) else None
    VSTAT[1] += 1
    prior = VRAW[t - 54:t, j]
    if len(prior) < 54 or not np.isfinite(prior).all(): return None
    base = prior[:50].mean(); recent = (prior[-4:].sum() + so_far / fr) / 5
    return 0.0 if base <= 0 else recent / base
def vol_ok(t, j, T, cut=2.0):
    if not FAIR: return bool(VOLOK[t, j]) and np.nan_to_num(S.vr.values[t, j], nan=9) <= cut
    if not ((np.nan_to_num(RAWC[t, j], nan=0) >= 5) and S.M.values[t, j]): return False
    VSTAT[0] += 1; r = vol_ratio(t, j, T)
    return r is None or r <= cut
def run(exit_mode="base", n=15, x=0.03, y=0.01, intraday_buy=False, bn=15, seed=1, no_rebuy=False, etf=False, bond=False, cs=0.0005, ce=0.0002, cp=0.0005, same_day=False, sd_x=None, sd_cap=None, dip=0.10, slots=10, w=0.10, drift=0, dth=0.05, dhold=60, mhs=5, vcut=2.0, vhalf=None, xn=None, fin_off=0, wmul=None, skip=None, sect=None, sect_lag=None, smul=1.5, wfin_only=False, tlog=None):
    """wmul/skip/sect (Nov 28, v3.3): per stock-day size multiplier (12-month strength), skip mask (earnings 8-K window), sector-wide
    dip mask (close-based for the 3:45 step; sect_lag = previous-close version for buys during the day, no look-ahead) -> x smul."""
    cash, pos, curve, held_park, trades = 1.0, [], np.ones(D), "CASH", []
    prng = np.random.default_rng(seed)
    early_sells = [0]; early_buys = [0]; DT = []          # DT = days with a same-day sell (day trade)
    for t in range(tr0, D):
        want = "SPY" if S.park_on[t] else ("IEF" if bond and S.BOND_OK[t] else "CASH")
        if want != held_park: cash *= 1 - cp * ((held_park != "CASH") + (want != "CASH")); held_park = want
        cu = cash; FIN = fin_of(t) - fin_off            # cu = idle money in 'yesterday's close' units; worth cu * park_f(t, held_park, T) at time T
        for p in pos: p["ref"] = (S.S_C if p["k"] != "E" else S.E_C)[t - 1, p["j"]]; p["armed"] = False; p["hi"] = 0.0
        sold_today = set()
        checks = list(range(600, FIN, xn)) if (xn and exit_mode in ("target", "trail")) else \
                 list(range(575, FIN, 5)) if exit_mode in ("target", "lock", "placebo", "trail") or (exit_mode == "check" and n == 5) else \
                 (list(range(570 + n, FIN, n)) if exit_mode == "check" else [])
        buy_checks = list(range(600, FIN, bn)) if intraday_buy else []
        times = sorted(set(checks) | set(buy_checks) | {FIN})
        spy5_ref = S.SP[t - 5]
        for T in times:
            final = T == FIN; pf = park_f(t, held_park, T)
            # exits
            keep = []
            for p in pos:
                Cx = S.S_C if p["k"] != "E" else S.E_C; j = p["j"]; age = t - p["d"]; mh = mhs if p["k"] == "S" else 10
                if p["k"] == "D":
                    if not (final and age >= dhold): keep.append(p); continue
                    f = S.S_C[t, j]; f = f if np.isfinite(f) else p["ref"]
                    cu += p["v"] * (f / p["ref"]) * (1 - cs) / pf; trades.append(f / p["px"] - 1 - 2 * cs); continue
                now = px_at(t, p["k"], j, T)
                sd = age < 1 and same_day and exit_mode == "target" and not final and T in checks and p["d"] == t
                if sd and sd_cap is not None and sum(1 for d_ in DT if d_ > t - 5) >= sd_cap: sd = False
                if now is None or (age < 1 and not sd): keep.append(p); continue
                m5 = np.mean(np.r_[Cx[t - 4:t, j], now]); out = False
                if final: out = now > m5 or age >= mh
                elif T in checks:
                    if exit_mode == "check": out = now > m5
                    elif exit_mode == "target": out = p["k"] != "D" and now >= p["px"] * (1 + (sd_x if age < 1 and sd_x is not None else x))
                    elif exit_mode == "trail":           # Nov 24: arm at +x over the buy price, then sell once it is y below the highest check price (kept across days)
                        if p["k"] != "D" and now >= p["px"] * (1 + x): p["t_arm"] = True
                        if p.get("t_arm"): p["t_hi"] = max(p.get("t_hi", 0.0), now); out = now <= p["t_hi"] * (1 - y)
                    elif exit_mode == "placebo": out = prng.random() < 1 / 74 * 1.3     # sells at a random time of day, about as often as 'check'
                    elif exit_mode == "lock":
                        if now > m5: p["armed"] = True
                        if p["armed"]:
                            p["hi"] = max(p["hi"], now); out = now < m5 or now < p["hi"] * (1 - y)
                if out:
                    f = px_at(t, p["k"], j, T, fill=True)
                    f = f if f is not None and np.isfinite(f) else Cx[t, j]
                    c = cs if p["k"] != "E" else ce
                    cu += p["v"] * (f / p["ref"]) * (1 - c) / pf; trades.append(f / p["px"] - 1 - 2 * c)
                    if tlog is not None and "a0" in p:
                        d0 = p["d"]; Ox = S.S_O if p["k"] != "E" else S.E_O
                        tlog.append((p["k"], int(j), int(d0), int(t), float(p["a0"]), float(p["e0"]), float(trades[-1]), float(p["px"]), float(Cx[d0, j]), float(Ox[d0 + 1, j]) if d0 + 1 < D else np.nan, float(f), float(Cx[t, j]), bool(p["fin"]), bool(final)))
                    if not final: early_sells[0] += 1
                    if age < 1: DT.append(t)
                    sold_today.add((p["k"], j))
                else: keep.append(p)
            pos = keep
            # entries (3:45 always; intraday every 15 minutes if on)
            if final or T in buy_checks:
                spys = series(t, "SPY", S.SP[t], S.RAW["SPY"].values[t]); spx = (float(spys[1][np.searchsorted(spys[0], T, side='right') - 1]) if spys is not None and np.searchsorted(spys[0], T, side='right') > 0 else (S.SP[t] if final else None))
                if spx is None: continue
                spy5 = spx / spy5_ref - 1; held = {(p["k"], p["j"]) for p in pos} | (sold_today if no_rebuy else set())
                eq_now = cu * pf + sum(p["v"] for p in pos)
                cand = []
                for j in np.flatnonzero(NEAR[t] & (S.M.values[t] if FAIR else VOLOK[t])):
                    if (FAIR or vcut < 2.0) and not vol_ok(t, j, T, vcut): continue
                    if ("S", j) in held or ("D", j) in held: continue
                    now = px_at(t, "S", j, T)
                    if now is None: continue
                    g5 = now / S.S_C[t - 5, j] - 1 - spy5
                    if skip is not None and skip[t, j]: continue
                    if g5 <= -dip and now > np.mean(np.r_[S.S_C[t - 199:t, j], now]): cand.append((g5, "S", j))
                cand.sort(key=lambda z: z[0])
                ce_ = []
                if etf:
                    for j in np.flatnonzero(NEARE[t]):
                        if ("E", j) in held: continue
                        now = px_at(t, "E", j, T)
                        if now is not None and now / S.E_C[t - 5, j] - 1 <= -0.05 and now > np.mean(np.r_[S.E_C[t - 199:t, j], now]): ce_.append((now / S.E_C[t - 5, j] - 1, "E", j))
                    ce_.sort(key=lambda z: z[0])
                for _, k, j in cand + ce_:
                    if sum(1 for q in pos if q["k"] != "D") >= slots: break
                    f = px_at(t, k, j, T, fill=True)
                    if f is None or not np.isfinite(f) or f <= 0: continue
                    hv = vhalf is not None and k == "S" and (lambda r_: r_ is not None and r_ > vhalf)(vol_ratio(t, j, T))   # busy dip: half size
                    mu = 1.0
                    if wmul is not None and k == "S" and (final or not wfin_only):
                        sx = sect if final else sect_lag
                        mu = wmul[t, j] * (smul if sx is not None and sx[t, j] else 1.0)
                    a = min(w * eq_now * (0.5 if hv else 1.0) * mu, cu * pf); c = cs if k == "S" else ce
                    if a < 0.02 * eq_now: break
                    cu -= a / pf; pos.append({"k": k, "j": j, "d": t, "px": f, "v": a * (1 - c), "ref": f, "armed": False, "hi": 0.0, "a0": a, "e0": eq_now, "fin": final}); held.add((k, j))
                    if not final: early_buys[0] += 1
                if final and drift:                                  # earnings drift (v3.1): extra slots, bought at the 3:45 step on the reaction day
                    for j in sorted(np.flatnonzero(np.nan_to_num(S.RXC[t], nan=-1) >= dth), key=lambda j: -S.RXC[t, j]):
                        if sum(1 for q in pos if q["k"] == "D") >= drift: break
                        if ("D", j) in held or ("S", j) in held: continue
                        f = px_at(t, "S", j, T, fill=True)
                        if f is None or not np.isfinite(f) or f <= 0: continue
                        a = min(0.10 * eq_now, cu * pf)
                        if a < 0.02 * eq_now: break
                        cu -= a / pf; pos.append({"k": "D", "j": j, "d": t, "px": f, "v": a * (1 - cs), "ref": f, "armed": False, "hi": 0.0}); held.add(("D", j))
        cash = cu * park_f(t, held_park, 960)
        for p in pos:                                                    # mark to the close
            Cx = S.S_C if p["k"] != "E" else S.E_C; p["v"] *= Cx[t, p["j"]] / p["ref"]; p["ref"] = Cx[t, p["j"]]
        curve[t] = cash + sum(p["v"] for p in pos)
    ix = np.arange(tr0, D); cv = curve[ix] / curve[tr0 - 1]; y_ = len(ix) / 252
    o = {"per_year_pct": round((cv[-1] ** (1 / y_) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
         "trades_per_month": round(len(trades) / (y_ * 12), 1), "avg_trade_pct": round(float(np.mean(trades)) * 100, 2) if trades else None,
         "win_pct": round(float(np.mean(np.array(trades) > 0)) * 100) if trades else None,
         "sold_during_day_per_month": round(early_sells[0] / (y_ * 12), 1), "same_day_sells_per_month": round(len(DT) / (y_ * 12), 2), "bought_during_day_per_month": round(early_buys[0] / (y_ * 12), 1)}
    for name, a_, b_ in (("2016-2020", "2016-01-01", "2021-01-01"), ("2021-2026", "2021-01-01", "2100-01-01")):
        jj = np.flatnonzero((dn[ix] >= np.datetime64(a_)) & (dn[ix] < np.datetime64(b_)))
        if len(jj) == 0: o[name] = None; continue
        c2 = cv[jj] / (cv[jj[0] - 1] if jj[0] > 0 else 1); o[name] = round((c2[-1] ** (252 / len(jj)) - 1) * 100, 1)
    yrs = pd.Series(cv, index=pd.DatetimeIndex(dn[ix])).resample("YE").last(); prev = np.r_[1.0, yrs.values[:-1]]
    o["years"] = {str(k.year): round((v / p_ - 1) * 100, 1) for k, v, p_ in zip(yrs.index, yrs.values, prev)}
    if tlog is not None:
        mo = pd.Series(cv, index=pd.DatetimeIndex(dn[ix])).resample("ME").last(); o["_months"] = {str(k)[:7]: float(v) for k, v in (mo / mo.shift(1).fillna(1.0) - 1).items()}
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
if os.environ.get("SAME_DAY") == "1":                   # Nov 19: same-day selling (margin accounts: no day-trade limit since Jun 4 2026)
    V = []
    for bot, kw in (("Robinhood rules", {}), ("v3.0", dict(etf=True, bond=True))):
        b = dict(intraday_buy=True, bn=15, exit_mode="target", x=0.05, **kw)
        V += [(f"{bot} | v3.2 rules (no same-day sells)", b),
              (f"{bot} | + same-day +5% sells, unlimited", dict(same_day=True, **b)),
              (f"{bot} | + same-day +5% sells, max 3 per 5 days", dict(same_day=True, sd_cap=3, **b)),
              (f"{bot} | + same-day +3% sells, unlimited", dict(same_day=True, sd_x=0.03, **b)),
              (f"{bot} | + same-day +5%, no rebuy same day", dict(same_day=True, no_rebuy=True, **b)),
              (f"{bot} | + same-day +5% sells, 0.10% per side", dict(same_day=True, cs=0.001, ce=0.0004, **b)),
              (f"{bot} | v3.2 rules, 0.10% per side", dict(cs=0.001, ce=0.0004, **b))]
if os.environ.get("COMBO") == "1":                      # Nov 19: v3.1 + v3.2 together, slot count/size, dip size - all on the v3.2 rules
    b = dict(etf=True, bond=True); i32 = dict(intraday_buy=True, bn=15, exit_mode="target", x=0.05, **b)
    V = [("v3.0 | 3:45 only", b), ("v3.1 = v3.0 + 2 drift slots (3:45 only)", dict(drift=2, **b)),
         ("v3.2", i32), ("v3.2 + 2 drift slots", dict(drift=2, **i32)), ("v3.2 + 3 drift slots", dict(drift=3, **i32)),
         ("v3.2 + 2 drift slots, 0.10% per side", dict(drift=2, cs=0.001, ce=0.0004, **i32)), ("v3.2, 0.10% per side", dict(cs=0.001, ce=0.0004, **i32)),
         ("v3.2 | 8 slots x 12.5%", dict(slots=8, w=0.125, **i32)), ("v3.2 | 12 slots x 8.3%", dict(slots=12, w=1 / 12, **i32)),
         ("v3.2 | 15 slots x 6.7%", dict(slots=15, w=1 / 15, **i32)), ("v3.2 | 12 slots x 10% (more invested)", dict(slots=12, w=0.10, **i32)),
         ("v3.2 | dip 9%", dict(dip=0.09, **i32)), ("v3.2 | dip 11%", dict(dip=0.11, **i32)), ("v3.2 | dip 12%", dict(dip=0.12, **i32))]
if os.environ.get("TIMING") == "1":                     # Nov 24: time of the daily final step (buys + 5-day-average sells), 3:15 / 3:30 / 3:45 (today) / 3:55
    V = []
    for bot, kw in (("v3.0 (one daily run)", dict(etf=True, bond=True)), ("v3.2 live-exact", dict(etf=True, bond=True, intraday_buy=True, bn=15, exit_mode="target", x=0.05, xn=15))):
        for off, lbl in ((30, "3:15"), (15, "3:30"), (0, "3:45 (today)"), (-10, "3:55")): V.append((f"{bot} | daily step at {lbl}", dict(fin_off=off, **kw)))
if os.environ.get("WF") == "1":                         # Nov 24: walk-forward grid for v3.2 (live-exact: target checks every 15 min from 10:00)
    V = [(f"v3.2 | dip {int(dp*100)}% | target +{int(x*100)}%", dict(etf=True, bond=True, intraday_buy=True, bn=15, exit_mode="target", x=x, xn=15, dip=dp))
         for dp in (0.08, 0.10, 0.12) for x in (0.03, 0.05, 0.07)]
if os.environ.get("TRAIL") == "1":                      # Nov 24: trailing stop vs fixed +5% target, v3.2 (live: checks every 15 min from 10:00)
    b = dict(etf=True, bond=True); i15 = dict(intraday_buy=True, bn=15, **b); i5 = dict(intraday_buy=True, bn=5, **b)
    V = [("v3.0 (3:45 only)", dict(**b)),
         ("v3.2 live: target +5%, checks every 15 min from 10:00", dict(exit_mode="target", x=0.05, xn=15, **i15)),
         ("v3.2 target +5%, checks every 5 min from 10:00", dict(exit_mode="target", x=0.05, xn=5, **i15)),
         ("v3.2 old replay: target +5%, every 5 min from 9:35", dict(exit_mode="target", x=0.05, **i15))]
    for arm, y in ((0.05, 0.01), (0.05, 0.02), (0.03, 0.01), (0.07, 0.02)):
        for xn in (15, 5):
            V.append((f"v3.2 trailing: arm +{int(arm*100)}%, sell {int(y*100)}% below high, every {xn} min", dict(exit_mode="trail", x=arm, y=y, xn=xn, **i15)))
    V.append(("v3.2 trailing +5% / 1%, every 5 min, buys every 5 min too", dict(exit_mode="trail", x=0.05, y=0.01, xn=5, **i5)))
if os.environ.get("V33") in ("1", "B", "T", "F"):     # Nov 28: v3.3 = v3.2 + strength sizing 1.5x/0.5x + skip earnings dips + sector-wide dips 1.5x
    def v33_parts():
        Cs, Mv = S.Cs, S.M
        mom12 = Cs.shift(5) / Cs.shift(257) - 1; mr = np.nan_to_num(mom12.where(Mv).rank(axis=1, pct=True).values, nan=0.5)
        wm = np.where(mr >= 2 / 3, 1.5, np.where(mr <= 1 / 3, 0.5, 1.0))
        ITEMS = json.load(open("data/sec_8k_items.json"))["tickers"] if os.path.exists("data/sec_8k_items.json") else {}
        SIC = {t: (v.get("sic") or "")[:2] for t, v in json.load(open("data/sec_events_sic.json"))["tickers"].items()} if os.path.exists("data/sec_events_sic.json") else {}
        dstr = np.array(ds); earn = np.zeros(S.S_C.shape, bool)
        for j, tk in enumerate(S.tick):
            for d, mi, it in ITEMS.get(tk) or []:
                if not ({"2.02", "12"} & set((it or "").split(","))): continue
                i = int(np.searchsorted(dstr, d))
                if i >= len(dstr): continue
                if dstr[i] == d and mi is not None and mi > 15 * 60 + 45: i += 1
                earn[i:i + 5, j] = True
        r5 = np.vstack([np.full((5, len(S.tick)), np.nan), S.S_C[5:] / S.S_C[:-5] - 1]); r5l = np.vstack([np.full((1, len(S.tick)), np.nan), r5[:-1]])
        grp = {}
        for j, t_ in enumerate(S.tick):
            if SIC.get(t_): grp.setdefault(SIC[t_], []).append(j)
        gid = {j: np.array([x for x in grp[SIC[t_]] if x != j], dtype=int) for j, t_ in enumerate(S.tick) if SIC.get(t_)}
        sect = np.zeros(S.S_C.shape, bool); sectl = np.zeros(S.S_C.shape, bool); Mm = S.M.values
        for t, j in zip(*np.nonzero(NEAR)):
            if t < tr0 or j not in gid: continue
            g = gid[j]; g = g[Mm[t, g]]
            for arr, out in ((r5, sect), (r5l, sectl)):
                v = arr[t, g]; v = v[np.isfinite(v)]
                if len(v) >= 3 and np.median(v) <= -0.05: out[t, j] = True
        print("v3.3 parts: strong/weak share", round(float((wm[tr0:] == 1.5).mean()), 3), round(float((wm[tr0:] == 0.5).mean()), 3),
              "| earnings-window stock-days", int(earn[tr0:].sum()), "| sector-wide candidate days", int(sect[tr0:].sum()), "(lagged", int(sectl[tr0:].sum()), ")", "| 8-K tickers", len(ITEMS), "SIC", len(SIC), flush=True)
        return wm, earn, sect, sectl
    WM, EARN, SECT, SECTL = v33_parts()
    V32 = dict(etf=True, bond=True, intraday_buy=True, bn=15, exit_mode="target", x=0.05); V30 = dict(etf=True, bond=True)
    B33 = dict(wmul=WM, skip=EARN, sect=SECT, sect_lag=SECTL); C2 = dict(cs=0.001, ce=0.0004)
    def placebo(seed):                                   # same multipliers shuffled across stocks each day + random skips at the same daily rate
        r_ = np.random.default_rng(seed); wmp = r_.permuted(WM, axis=1); rate = EARN[tr0:].mean()
        return dict(wmul=wmp, skip=r_.random(EARN.shape) < rate, sect=r_.permuted(SECT, axis=1), sect_lag=r_.permuted(SECTL, axis=1))
    MODE33 = os.environ.get("V33")
    def wm_of(hi, lo): return np.where(WM == 1.5, hi, np.where(WM == 0.5, lo, 1.0))
    V = [("v3.2", V32), ("v3.3 = v3.2 + strength sizing + skip earnings dips + sector-wide 1.5x", {**V32, **B33}),
         ("v3.2 | 2x costs", {**V32, **C2}), ("v3.3 | 2x costs", {**V32, **B33, **C2}),
         ("v3.2 + strength sizing only", {**V32, "wmul": WM}), ("v3.2 + skip earnings dips only", {**V32, "skip": EARN}),
         ("v3.2 + sector-wide 1.5x only", {**V32, "wmul": np.ones_like(WM), "sect": SECT, "sect_lag": SECTL}),
         ("v3.0 | 3:45 only", V30), ("v3.0 + v3.3 changes | 3:45 only", {**V30, **B33}),
         ("PLACEBO v3.3 shuffled (seed 1)", {**V32, **placebo(1)}), ("PLACEBO v3.3 shuffled (seed 2)", {**V32, **placebo(2)})]
    if MODE33 == "B":   # job 2: gentler strength sizing (all with skip earnings + sector-wide 1.5x)
        E_ = dict(skip=EARN, sect=SECT, sect_lag=SECTL)
        V = [("v3.2", V32), ("v3.3 (1.5x / 0.5x)", {**V32, **B33})]
        for hi, lo in ((1.25, 0.75), (1.5, 0.75), (1.25, 1.0), (1.5, 1.0), (1.0, 0.75), (1.0, 0.5), (1.25, 0.5)):
            V.append((f"v3.3 sizing {hi}x / {lo}x", {**V32, **E_, "wmul": wm_of(hi, lo)}))
        V += [("v3.3 (1.5x / 0.5x), strength only at the 3:45 step", {**V32, **B33, "wfin_only": True}),
              ("v3.3 sizing 1.25x / 0.75x, strength only at the 3:45 step", {**V32, **E_, "wmul": wm_of(1.25, 0.75), "wfin_only": True}),
              ("v3.2 + skip earnings dips + sector-wide 1.5x (no strength)", {**V32, **E_, "wmul": np.ones_like(WM)}),
              ("v3.3 sizing 1.25x / 0.75x | 2x costs", {**V32, **E_, "wmul": wm_of(1.25, 0.75), **C2}), ("v3.3 (1.5x / 0.5x) | 2x costs", {**V32, **B33, **C2})]
    if MODE33 in ("T", "F"):   # job 3 (is 2026 a fluke?) and job 5 (3:45 fills vs close vs next open), from per-trade logs
        SICm = {t_: (v.get("sic") or "")[:2] for t_, v in json.load(open("data/sec_events_sic.json"))["tickers"].items()} if os.path.exists("data/sec_events_sic.json") else {}
        def tl_df(tl):
            X_ = pd.DataFrame(tl, columns=["k", "j", "d0", "t1", "a0", "e0", "ret", "buy", "buy_close", "next_open", "sell", "sell_close", "buy_345", "sell_345"])
            X_["sym"] = [S.tick[j] if k != "E" else S.EN[j] for k, j in zip(X_.k, X_.j)]; X_["date"] = [ds[i] for i in X_.d0]; X_["year"] = X_.date.str[:4]; X_["month"] = X_.date.str[:7]
            X_["pnl_pct"] = X_.a0 / X_.e0 * X_.ret * 100; X_["sector"] = [SICm.get(sy, "") if k == "S" else "ETF" for k, sy in zip(X_.k, X_.sym)]; return X_
        OUTX = {"note": "Nov 28 research. pnl_pct = trade size / account x trade return (percent of the account at entry)."}
        if MODE33 == "T":
            L2, L3 = [], []; R2 = run(**V32, tlog=L2); R3 = run(**{**V32, **B33}, tlog=L3); A_, B_ = tl_df(L2), tl_df(L3)
            OUTX["v3.2"] = {k: v for k, v in R2.items() if k != "_months"}; OUTX["v3.3"] = {k: v for k, v in R3.items() if k != "_months"}
            yrs = sorted(set(R2["years"]))
            OUTX["by year: return v3.2 / v3.3 / gap"] = {y: [R2["years"][y], R3["years"].get(y), round(R3["years"].get(y, 0) - R2["years"][y], 1)] for y in yrs}
            g = lambda y: np.prod([1 + R3["years"][x] / 100 for x in yrs if x != y]) ** (1 / (len(yrs) - 1)) - np.prod([1 + R2["years"][x] / 100 for x in yrs if x != y]) ** (1 / (len(yrs) - 1))
            OUTX["per-year gain if one year is left out"] = {y: round(g(y) * 100, 1) for y in yrs}
            OUTX["2025-2026 by month: v3.2 / v3.3 (%)"] = {m: [round(R2["_months"][m] * 100, 1), round(R3["_months"].get(m, 0) * 100, 1)] for m in sorted(R2["_months"]) if m >= "2025-01"}
            for lab, f_ in (("2026", lambda X: X[X.year == "2026"]), ("2016-2025", lambda X: X[X.year < "2026"])):
                a_, b_ = f_(A_), f_(B_)
                sec = (b_.groupby("sector").pnl_pct.sum() - a_.groupby("sector").pnl_pct.sum().reindex(b_.groupby("sector").pnl_pct.sum().index).fillna(0)).sort_values()
                OUTX[f"{lab}: gap v3.3 - v3.2 by SIC sector (pct points of account)"] = {k: round(float(v), 1) for k, v in sec.items()}
                sy = (b_.groupby("sym").pnl_pct.sum().sub(a_.groupby("sym").pnl_pct.sum(), fill_value=0)).sort_values()
                OUTX[f"{lab}: symbols that helped v3.3 most"] = {k: round(float(v), 1) for k, v in sy.tail(12)[::-1].items()}
                OUTX[f"{lab}: symbols that hurt v3.3 most"] = {k: round(float(v), 1) for k, v in sy.head(8).items()}
                OUTX[f"{lab}: trades v3.2 / v3.3"] = [len(a_), len(b_)]
            top = list(OUTX["2026: symbols that helped v3.3 most"])[:5]; mk = np.zeros(S.S_C.shape, bool)
            for t_ in top:
                if t_ in S.TI: mk[:, S.TI[t_]] = True
            R2x = run(**{**V32, "skip": mk}); R3x = run(**{**V32, **B33, "skip": EARN | mk})
            OUTX[f"without 2026's top 5 helpers ({', '.join(top)}) in BOTH versions"] = {"v3.2": {k: R2x[k] for k in ("per_year_pct", "worst_drop_pct", "years")}, "v3.3": {k: R3x[k] for k in ("per_year_pct", "worst_drop_pct", "years")}}
            print(json.dumps({k: v for k, v in OUTX.items() if "symbols" not in k and "month" not in k}, default=float)[:3000], flush=True)
        else:
            L2 = []; R2 = run(**V32, tlog=L2); A_ = tl_df(L2); Sx = A_[A_.k == "S"].copy()
            def st(x): x = x[np.isfinite(x)]; return {"avg_pct": round(float(x.mean()) * 100, 3), "median_pct": round(float(x.median()) * 100, 3), "n": int(len(x))}
            for lab, m_ in (("bought at the 3:45 step", Sx.buy_345), ("bought during the day", ~Sx.buy_345)):
                b = Sx[m_]
                OUTX[f"buys, {lab}: close vs our fill (+ = close was higher, backtest 'expected' too pessimistic)"] = st(b.buy_close / b.buy - 1)
                OUTX[f"buys, {lab}: next open vs our fill (+ = next open was higher, backtest 'worst case' too pessimistic)"] = st(b.next_open / b.buy - 1)
            for lab, m_ in (("sold at the 3:45 step", Sx.sell_345), ("sold during the day (+5% target)", ~Sx.sell_345)):
                b = Sx[m_]; OUTX[f"sells, {lab}: our fill vs close (+ = we sold above the close)"] = st(b.sell / b.sell_close - 1)
            n_yr = len(Sx) / (len(ds[tr0:]) / 252)
            OUTX["stock trades per year"] = round(n_yr, 1)
            bb = Sx[Sx.buy_345]; ss = Sx[Sx.sell_345]
            drag = (np.nanmean(bb.buy_close / bb.buy - 1) * len(bb) + np.nanmean(ss.sell / ss.sell_close - 1) * len(ss)) / len(Sx) if len(Sx) else 0
            OUTX["3:45 fills vs close fills: avg effect per trade (percent)"] = round(float(drag) * 100, 3)
            OUTX["v3.2 run"] = {k: v for k, v in R2.items() if k != "_months"}
            print(json.dumps(OUTX, default=float)[:3000], flush=True)
        json.dump(OUTX, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True); sys.exit(0)
if os.environ.get("VOLTEST") == "1":                    # Nov 24: skip or half-size busy dips (volume ratio known at that moment), v3.0 3:45 only and v3.2
    V = []
    for bot, kw in (("v3.0 (3:45 only)", dict(etf=True, bond=True)), ("v3.2 (15 min + target +5%)", dict(etf=True, bond=True, intraday_buy=True, bn=15, exit_mode="target", x=0.05))):
        V += [(f"{bot} | today (skip > 2x)", dict(**kw)), (f"{bot} | skip > 1.6x", dict(vcut=1.6, **kw)), (f"{bot} | skip > 1.4x", dict(vcut=1.4, **kw)),
              (f"{bot} | half size > 1.4x", dict(vhalf=1.4, **kw)), (f"{bot} | half size > 1.2x", dict(vhalf=1.2, **kw))]
if os.environ.get("HOLD") == "1":                       # Nov 23: how long to hold + target size, previous live rules (v1) and v3.0
    V = []
    for bot, kw in (("previous live (v1)", {}), ("v3.0", dict(etf=True, bond=True))):
        for mh in (3, 5, 7, 10, 15, 40): V.append((f"{bot} | 3:45 only | max hold {'40 (= until it bounces)' if mh == 40 else str(mh) + ' days'}", dict(mhs=mh, **kw)))
        i32 = dict(intraday_buy=True, bn=15, exit_mode="target", **kw)
        for x in (0.03, 0.05, 0.07, 0.10): V.append((f"{bot} | v3.2 (15 min) target +{int(x*100)}% | max hold 5 days", dict(x=x, **i32)))
        for mh in (7, 10, 40): V.append((f"{bot} | v3.2 (15 min) target +5% | max hold {'40 (= until it bounces)' if mh == 40 else str(mh) + ' days'}", dict(x=0.05, mhs=mh, **i32)))
RES = {}
for name, kw in V:
    RES[name] = run(**kw); a = RES[name]
    print(f"{name:62s} {a['per_year_pct']}%/yr same-day {a['same_day_sells_per_month']}/mo | worst {a['worst_drop_pct']}% | 16-20 {a['2016-2020']} 21-26 {a['2021-2026']} | {a['trades_per_month']}/mo avg {a['avg_trade_pct']}% win {a['win_pct']}% | early sells {a['sold_during_day_per_month']}/mo buys {a['bought_during_day_per_month']}/mo", flush=True)
print(f"5-minute series: {BAD[1]} looked up, {BAD[0]} fell back to the daily close", flush=True)
print(f"idle-money value by time of day: {PSTAT[0]} from the parked ETF's own bars, {PSTAT[1]} SPY stand-in, {PSTAT[2]} straight line | half-days: {sum(v != 945 for v in FINC.values())}", flush=True)
PAIRS = (("v3.2", "v3.3 = v3.2 + strength sizing + skip earnings dips + sector-wide 1.5x"), ("v3.0 | 3:45 only", "v3.0 + v3.3 changes | 3:45 only")) if os.environ.get("V33") == "1" else \
        (("v3.2 live-exact | daily step at 3:45 (today)", "v3.2 live-exact | daily step at 3:30"),) if os.environ.get("TIMING") == "1" else \
        (("v3.2 | dip 10% | target +5%", "v3.2 | dip 10% | target +3%"),) if os.environ.get("WF") == "1" else \
        (("v3.2 live: target +5%, checks every 15 min from 10:00", "v3.2 trailing: arm +5%, sell 1% below high, every 15 min"), ("v3.2 live: target +5%, checks every 15 min from 10:00", "v3.2 trailing: arm +5%, sell 1% below high, every 5 min")) if os.environ.get("TRAIL") == "1" else \
        (("v3.2 (15 min + target +5%) | today (skip > 2x)", "v3.2 (15 min + target +5%) | skip > 1.4x"), ("v3.2 (15 min + target +5%) | today (skip > 2x)", "v3.2 (15 min + target +5%) | half size > 1.4x")) if os.environ.get("VOLTEST") == "1" else \
        (("v3.0 | 3:45 only | max hold 5 days", "v3.0 | 3:45 only | max hold 10 days"), ("v3.0 | v3.2 (15 min) target +5% | max hold 5 days", "v3.0 | v3.2 (15 min) target +10% | max hold 5 days")) if os.environ.get("HOLD") == "1" else \
        (("v3.2", "v3.2 + 2 drift slots"), ("v3.0 | 3:45 only", "v3.1 = v3.0 + 2 drift slots (3:45 only)")) if os.environ.get("COMBO") == "1" else \
        (("v3.0 | v3.2 rules (no same-day sells)", "v3.0 | + same-day +5% sells, unlimited"), ("Robinhood rules | v3.2 rules (no same-day sells)", "Robinhood rules | + same-day +5% sells, unlimited")) if os.environ.get("SAME_DAY") == "1" else \
        (("v3.0 | base: 3:45 only", "v3.0 | buy during the day (15 min) + target +5%"), ("Robinhood rules | base: 3:45 only", "Robinhood rules | buy during the day (15 min) + target +5%"))
for a_, b_ in PAIRS:
    ya, yb = RES[a_]["years"], RES[b_]["years"]; d = {y: round(yb[y] - ya[y], 1) for y in ya}
    RES[f"YEARS: {b_} minus base"] = {"by_year": d, "years_better": sum(v > 0 for v in d.values()), "years": len(d), "best_year_share_of_gain_pct": round(100 * max(d.values()) / max(1e-9, sum(v for v in d.values() if v > 0)))}
    print("YEARS", b_, "vs base:", " ".join(f"{y}:{ya[y]}->{yb[y]}" for y in ya), "| better in", RES[f"YEARS: {b_} minus base"]["years_better"], "of", len(d), flush=True)
if FAIR: print(f"fair volume filter: {VSTAT[0]} checks, {VSTAT[1]} used today's volume so far, {VSTAT[2]} had no 5-minute volume (full-day filter)", flush=True)
WFR = None
if os.environ.get("WF") == "1":                          # pick each year's setting from earlier years only, chain the years
    names = [n for n, v in RES.items() if isinstance(v, dict) and isinstance(v.get("years"), dict)]; yrs = sorted({y for n in names for y in RES[n]["years"]})
    yr = lambda n, y: (RES[n].get("years") or {}).get(y)
    sc = lambda n, ys: np.prod([1 + (yr(n, y) or 0) / 100 for y in ys])
    fixed = "v3.2 | dip 10% | target +5%"; out = {}
    for lbl, win in (("all earlier years", 99), ("last 3 years", 3)):
        ch, picks = [], {}
        for i, y in enumerate(yrs):
            if i == 0: continue
            past = yrs[max(0, i - win):i]; n = max(names, key=lambda n: sc(n, past)); picks[y] = n; ch.append(yr(n, y) or 0)
        out[lbl] = {"per_year_pct": round((np.prod([1 + c / 100 for c in ch]) ** (1 / len(ch)) - 1) * 100, 1), "picks": picks}
    fx = [yr(fixed, y) or 0 for y in yrs[1:]]; out["fixed today (dip 10%, +5%)"] = round((np.prod([1 + c / 100 for c in fx]) ** (1 / len(fx)) - 1) * 100, 1)
    out["years_scored"] = f"{yrs[1]}-{yrs[-1]} (first year only used for picking)"; WFR = out; print("walk-forward", json.dumps(out)[:600], flush=True)
json.dump({"note": __doc__, "walk_forward": WFR, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "period_start": ds[tr0], "fallbacks": BAD, "park_value_lookups": PSTAT, "half_days": sum(v != 945 for v in FINC.values()), "fair_volume": FAIR, "fair_volume_stats": VSTAT, "alpaca_calls": CALLS[0], "results": RES},
          open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
