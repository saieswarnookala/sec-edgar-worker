"""'True live' replay of the dip bot with minute data (Nov 18 2026). Research only, not financial advice.
The live Robinhood bot decides on the ~3:45 pm prices and its orders fill a minute or two later. Backtests so far either buy at
the exact close (ideal) or at the next open (realistic). This replays what the bot really does, 2016-2026 (Alpaca SIP minute bars):
  decide at 15:45 ET with the 15:45 price (dips, exits, 200-day and 5-day averages all use it as 'today'),
  fill at the average of the 15:46-15:50 minute closes, plus a spread/slippage cost per side.
Variants: decide 15:45 (cost 0.05% and 0.10%), decide 15:55 (fill 15:56-15:59), ideal (close, 0.05%), realistic (next open, 0.15%);
for today's Robinhood rules and Dip bot v3.0 (+ ETF dips + bonds). Idle-money parking (Clear Leader / IEF / cash) uses daily closes.
Minute prices are turned into the adjusted daily scale with the stock's own move from that minute to its 15:59 close
(adj_px = adj_close * raw_px / raw_last_close); if Alpaca's raw last close is > 3% from the S&P data's raw close the minute data is
treated as a different company/bad and the daily close is used (counted).
Only stocks that could be near a signal are fetched: close-based 5-day gap vs SPY <= -7% (ETFs: 5-day drop <= -3%), plus the next
7 days for exits. Known shortcut: the volume filter uses the full day's volume (the live bot estimates it at 3:45).
Minute data cached in R2 (alpaca/m1540/<YYYY-MM>.json.gz). DRY=1: fake minute prices (no network)."""
import os, sys, json, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
import r2cache
DRY = S.DRY; OUT = "data/live_replay.json" if not DRY else "/tmp/live_replay_dry.json"
ET, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
START = os.environ.get("START", "2016-01-04")
tr0 = max(S.t0, int(np.searchsorted(S.dn, np.datetime64(START)))); D, dn, ds = S.D, S.dn, [str(d)[:10] for d in S.dn]
# ---------------- which (day, symbol) minute data is needed
def asym(t):  # parquet ticker -> Alpaca symbol
    b = t.rsplit("-", 1)[0] if len(t) > 7 and t[-7] == "-" and t[-6:].isdigit() else t
    return b.replace("-", ".")
ex5c = S.ex5.values; above = (S.Cs > S.Cs.rolling(200).mean()).values
NEAR = (S.M.values & (np.nan_to_num(ex5c, nan=1) <= -0.07)) & (np.nan_to_num(S.RAW[S.tick].values, nan=0) >= 4)
E5 = np.nan_to_num(S.E_C / np.vstack([np.full((5, S.E_C.shape[1]), np.nan), S.E_C[:-5]]) - 1, nan=1)
NEARE = E5 <= -0.03
need = {t: {"SPY"} for t in range(tr0, D)}
for t, j in zip(*np.nonzero(NEAR[tr0:])):
    for k in range(t + tr0, min(t + tr0 + 8, D)): need[k].add(S.tick[j])
for t, j in zip(*np.nonzero(NEARE[tr0:])):
    for k in range(t + tr0, min(t + tr0 + 12, D)): need[k].add("ETF:" + S.EN[j])
print("days", D - tr0, "| symbol-days needed", sum(len(v) for v in need.values()), flush=True)
# ---------------- fetch minute bars 15:40-16:00 ET (raw)
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
def fetch_day(day, syms):
    a = datetime.fromisoformat(day + "T15:40:00").replace(tzinfo=ET).astimezone(UTC); b = datetime.fromisoformat(day + "T16:00:00").replace(tzinfo=ET).astimezone(UTC)
    out, syms = {}, sorted(syms)
    for i in range(0, len(syms), 100):
        p = {"symbols": ",".join(syms[i:i + 100]), "timeframe": "1Min", "start": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": b.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "adjustment": "raw", "feed": "sip", "limit": "10000"}; tok = None
        while True:
            if tok: p["page_token"] = tok
            js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p))
            if not js: break
            for s, bars in (js.get("bars") or {}).items():
                for x in bars:
                    t = datetime.fromisoformat(x["t"].replace("Z", "+00:00")).astimezone(ET); out.setdefault(s, []).append([t.hour * 100 + t.minute, x["c"]])
            tok = js.get("next_page_token")
            if not tok: break
    return out
MIN = {}
if DRY:
    rng = np.random.default_rng(4)
    for t in range(tr0, D):
        MIN[ds[t]] = {}
        for s in need[t]:
            MIN[ds[t]][s.replace("ETF:", "")] = [[1540 + k if k < 20 else 1600, 100 * (1 + rng.normal(0, 0.002) * np.sqrt(20 - k))] for k in range(20)]
else:
    months = sorted({d[:7] for d in ds[tr0:]}); fetched = 0
    for mo in months:
        cache = r2cache.load(f"alpaca/m1540/{mo}.json.gz") or {}; changed = False
        for t in [t for t in range(tr0, D) if ds[t][:7] == mo]:
            day = ds[t]; have = cache.get(day, {}); none = set(have.get("_none", []))
            want = {asym(s) if not s.startswith("ETF:") else s[4:] for s in need[t]}
            miss = [s for s in want if s not in have and s not in none]
            if miss:
                got = fetch_day(day, miss); fetched += 1; have.update(got); have["_none"] = sorted(none | {s for s in miss if s not in got}); cache[day] = have; changed = True
            MIN[day] = have
        if changed: r2cache.save(f"alpaca/m1540/{mo}.json.gz", cache)
        print(mo, "days fetched", fetched, "calls", CALLS[0], flush=True)
# ---------------- minute price helpers (adjusted scale)
BAD = [0, 0]
def mpx(t, key, adj_close, raw_close, m, fill):
    """decision price (fill=False: last close at or before minute m) or fill price (avg of closes in (m, m+5]), adjusted scale"""
    bars = MIN.get(ds[t], {}).get(key)
    BAD[1] += 1
    if not bars or not np.isfinite(adj_close): BAD[0] += 1; return adj_close
    bars = sorted(bars); last = bars[-1][1]
    if raw_close and np.isfinite(raw_close) and abs(last / raw_close - 1) > 0.03: BAD[0] += 1; return adj_close
    if fill:
        xs = [c for hm, c in bars if m < hm <= m + 5 and hm < 1600] or [c for hm, c in bars if hm <= m][-1:]
    else:
        xs = [c for hm, c in bars if hm <= m][-1:]
    if not xs: BAD[0] += 1; return adj_close
    return adj_close * float(np.mean(xs)) / last
RAWC = S.RAW[S.tick].values
def spx(t, k, m, fill=False): return mpx(t, asym(S.tick[k]), S.S_C[t, k], RAWC[t, k], m, fill)
def epx(t, k, m, fill=False): return mpx(t, S.EN[k], S.E_C[t, k], None, m, fill)
SPYK = None
def spy_at(t, m): return mpx(t, "SPY", S.SP[t], S.RAW["SPY"].values[t], m, False)
# ---------------- replay engine (values, not returns)
VOLOK = (np.nan_to_num(S.vr.values, nan=9) <= 2.0) & (np.nan_to_num(RAWC, nan=0) >= 5) & S.M.values
def run(mode, etf=False, bond=False, cs=0.0005, ce=0.0002, cp=0.0005):
    """mode: 'close' (ideal), 'open' (next open), or minute int (decision minute, e.g. 1545)"""
    cash, pos, curve, held_park, trades, diff = 1.0, [], np.ones(D), "CASH", [], {"decisions": 0, "differs_from_close": 0}
    for t in range(tr0, D):
        eq_prev = cash + sum(p["v"] for p in pos)
        want = "SPY" if S.park_on[t] else ("IEF" if bond and S.BOND_OK[t] else "CASH")
        if want != held_park: cash *= 1 - cp * ((held_park != "CASH") + (want != "CASH")); held_park = want
        idle_ret = S.CLR[t] if held_park == "SPY" else (S.BOND_R[t] if held_park == "IEF" else 0.0)
        minute = isinstance(mode, int)
        # decision prices
        if minute:
            sp_now = spy_at(t, mode)
            dpx = lambda p: (spx if p["k"] == "S" else epx)(t, p["j"], mode)
            fpx = lambda k, j: (spx if k == "S" else epx)(t, j, mode, True)
        def do_entries():
            nonlocal cash, pos
            def signals(tt, at_minute):
                if at_minute:
                    spy5 = sp_now / S.SP[tt - 5] - 1; out = []
                    for j in np.flatnonzero(NEAR[tt] & VOLOK[tt]):
                        px = spx(tt, j, mode)
                        if not np.isfinite(px): continue
                        if px / S.S_C[tt - 5, j] - 1 - spy5 <= -0.10 and px > np.mean(np.r_[S.S_C[tt - 199:tt, j], px]): out.append((px / S.S_C[tt - 5, j] - 1 - spy5, j))
                    ce_ = []
                    if etf:
                        for j in np.flatnonzero(NEARE[tt]):
                            px = epx(tt, j, mode)
                            if np.isfinite(px) and px / S.E_C[tt - 5, j] - 1 <= -0.05 and px > np.mean(np.r_[S.E_C[tt - 199:tt, j], px]): ce_.append((px / S.E_C[tt - 5, j] - 1, j))
                    close_s = set(np.flatnonzero(S.SIG[tt])); live_s = {j for _, j in out}
                    diff["decisions"] += len(close_s | live_s); diff["differs_from_close"] += len(close_s ^ live_s)
                    return [j for _, j in sorted(out)], [j for _, j in sorted(ce_)]
                c = sorted(np.flatnonzero(S.SIG[tt]), key=lambda j: S.S_RK[tt, j])
                e = sorted([j for j in np.flatnonzero(S.E_SIG[tt]) if np.isfinite(S.E_C[tt, j])], key=lambda j: S.E_RK[tt, j]) if etf else []
                return c, e
            cs_, ce_ = signals(t - 1 if mode == "open" else t, minute)
            held = {(p["k"], p["j"]) for p in pos}; eq_now = cash + sum(p["v"] for p in pos)
            for k, lst in (("S", cs_), ("E", ce_)):
                for j in lst:
                    if len(pos) >= 10 or (k, j) in held: continue
                    Cx, Ox = (S.S_C, S.S_O) if k == "S" else (S.E_C, S.E_O)
                    f = Cx[t, j] if mode == "close" else (Ox[t, j] if mode == "open" else fpx(k, j))
                    if not (np.isfinite(f) and f > 0 and np.isfinite(Cx[t, j])): continue
                    a = min(0.10 * eq_now, cash); c = cs if k == "S" else ce
                    if a < 0.02 * eq_now: break
                    cash -= a; pos.append({"k": k, "j": j, "d": t, "px": f, "v": a * (1 - c) * (1 if mode == "open" else Cx[t, j] / f), "o": mode == "open"}); held.add((k, j))
        if mode == "open": do_entries()                          # bought at the open: before the day's moves and exits
        cash *= 1 + idle_ret
        # exits
        keep = []
        for p in pos:
            Cx, Mx = (S.S_C, None) if p["k"] == "S" else (S.E_C, None)
            j = p["j"]; age = t - p["d"] + (1 if p.get("o") else 0); mh = 5 if p["k"] == "S" else 10
            if mode in ("close", "open"):
                now = Cx[t, j]; m5 = np.mean(Cx[t - 4:t + 1, j])
            else:
                now = dpx(p); m5 = np.mean(np.r_[Cx[t - 4:t, j], now])
            if age >= 1 and (now > m5 or age >= mh or not np.isfinite(now)):
                f = Cx[t, j] if mode in ("close", "open") else fpx(p["k"], j)
                c = cs if p["k"] == "S" else ce
                base = p["px"] if (p.get("o") and p["d"] == t) else Cx[t - 1, j]
                cash += p["v"] * (f / base) * (1 - c); trades.append(f / p["px"] - 1 - 2 * c)
            else: p["v"] *= Cx[t, j] / (p["px"] if (p.get("o") and p["d"] == t) else Cx[t - 1, j]); keep.append(p)
        pos = keep
        if mode != "open": do_entries()
        curve[t] = cash + sum(p["v"] for p in pos)
    ix = np.arange(tr0, D); cv = curve[ix] / curve[tr0 - 1] if tr0 > 0 else curve[ix]; y = len(ix) / 252
    o = {"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
         "trades": len(trades), "avg_trade_pct": round(float(np.mean(trades)) * 100, 2) if trades else None, "win_pct": round(float(np.mean(np.array(trades) > 0)) * 100) if trades else None}
    for name, a, b in (("2016-2020", "2016-01-01", "2021-01-01"), ("2021-2026", "2021-01-01", "2100-01-01")):
        jj = np.flatnonzero((dn[ix] >= np.datetime64(a)) & (dn[ix] < np.datetime64(b)))
        if len(jj) > 200: c2 = cv[jj] / (cv[jj[0] - 1] if jj[0] > 0 else 1); o[name] = round((c2[-1] ** (252 / len(jj)) - 1) * 100, 1)
    if diff["decisions"]: o["signals_different_from_close_pct"] = round(diff["differs_from_close"] / diff["decisions"] * 100, 1)
    return o
V = []
for bot, kw in (("Robinhood rules", {}), ("Dip bot v3.0", dict(etf=True, bond=True))):
    V += [(f"{bot} | ideal (close, 0.05%)", dict(mode="close", **kw)), (f"{bot} | LIVE 3:45 decide, 3:46-3:50 fill, 0.05%", dict(mode=1545, **kw)),
          (f"{bot} | LIVE 3:45, 0.10% per side", dict(mode=1545, cs=0.001, ce=0.0004, **kw)), (f"{bot} | LIVE 3:55 decide, 3:56-3:59 fill, 0.05%", dict(mode=1555, **kw)),
          (f"{bot} | realistic (next open, 0.15%)", dict(mode="open", cs=0.0015, ce=0.0005, **kw))]
RES = {}
for name, kw in V:
    RES[name] = run(**kw); a = RES[name]
    print(f"{name:52s} {a['per_year_pct']}%/yr worst {a['worst_drop_pct']}% | 16-20 {a.get('2016-2020')} 21-26 {a.get('2021-2026')} | trades {a['trades']} avg {a['avg_trade_pct']}% win {a['win_pct']}% | differs {a.get('signals_different_from_close_pct')}%", flush=True)
print(f"minute prices: {BAD[1]} looked up, {BAD[0]} fell back to the daily close", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "period_start": ds[tr0], "minute_fallbacks": BAD, "alpaca_calls": CALLS[0], "results": RES},
          open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
