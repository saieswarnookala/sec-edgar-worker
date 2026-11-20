"""India intraday check (Nov 19 2026): does buying dips DURING the day (and a +5% target) help the India bot, like it did in the US?
Research only, not financial advice. Small test: Yahoo keeps only ~60 days of 5-minute prices, so this can show "obviously worse",
not prove "better".
India bot rules (scripts/paper_india.py): top-200 traded Nifty 500 stocks, above 200-day average, fell 12%+ more than the Nifty 50 over
5 sessions, 5-day volume <= 2x normal, no 35% one-day jumps; 10 slots x 10%; sell when back above the 5-day average (after >= 1 session)
or after 5 sessions; idle money NIFTYBEES (Nifty > 150-day avg) / GOLDBEES (gold > 100-day) / liquid fund (~6%/yr).
Base = decide and fill at the 3:10 pm IST price (India Bot B). Variants:
  + INTRADAY BUYS: every 15 min 9:45 am - 3:00 pm IST, buy a stock the moment it meets the rules (free slots only)
  + TARGET: every 15 min, sell a position held >= 1 session once it is +5% above its buy price
Costs 0.30% per side for stocks, 0.15% for ETFs. Idle money valued at the time of day it is spent (ETF 5-minute bars).
Per-signal check (more data points than the portfolio): every stock-day where the dip rule first became true during the day ->
  (a) still a dip at 3:10: was the 3:10 price higher (buying early was cheaper) or lower?
  (b) dips that recovered by 3:10 (the base never buys them): their return from the intraday buy to the next close / 3 sessions later.
DRY_FAKE=1: made-up prices (code test only)."""
import os, sys, io, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
OUT = "data/india_intraday.json" if not os.environ.get("DRY_FAKE") else "/tmp/india_intraday_dry.json"
DIP, TREND, LOOK, HOLD, VOLX, MINPX, TOP, SLOTS, W, BUF = 0.12, 200, 5, 5, 2.0, 20.0, 200, 10, 0.10, 0.02
CS, CE, LIQ = 0.003, 0.0015, (1.06) ** (1 / 248) - 1
OPEN, CLOSE, FINAL = 555, 930, 910            # IST minutes: 9:15, 15:30, decision 15:10
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def get(url, tries=4):
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception: time.sleep(3 * (a + 1))
    return None
def ychart(sym, rng, iv):
    b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval={iv}&events=div%2Csplit")
    if not b: return None
    try:
        j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]["quote"][0]
        ts = pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None)
        if iv == "1d":
            adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            df = pd.DataFrame({"c": adj, "rc": q["close"], "v": q["volume"]}, index=ts.normalize())
            df = df[~df.index.duplicated(keep="last")].dropna(subset=["c", "rc"]); return df[(df.c > 0) & (df.rc > 0)]
        df = pd.DataFrame({"c": q["close"], "v": q["volume"]}, index=ts).dropna(subset=["c"]); return df[df.c > 0]
    except Exception: return None
def to_slots(df5):
    """5-minute bars -> {day: (end_minute array, close array, volume array)} for the regular session"""
    out = {}
    if df5 is None or not len(df5): return out
    m = df5.index.hour * 60 + df5.index.minute
    df5 = df5[(m >= OPEN) & (m < CLOSE)]
    for d, g in df5.groupby(df5.index.normalize()):
        mm = (g.index.hour * 60 + g.index.minute + 5).values
        out[d] = (mm.astype(np.int32), g.c.values.astype(float), np.nan_to_num(g.v.values.astype(float)))
    return out
# ---------------- data
if os.environ.get("DRY_FAKE"):
    rng = np.random.default_rng(3); days = pd.bdate_range(end="2026-11-19", periods=320); N = 80
    def fake_daily(vol, drift):
        c = 100 * np.exp(np.cumsum(rng.normal(drift, vol, len(days)))); return pd.DataFrame({"c": c, "rc": c, "v": rng.lognormal(13, 0.3, len(days))}, index=days)
    def fake_5m(dd):
        rows = []
        for i, d in enumerate(dd.index[-60:]):
            prev = dd.c.iloc[-61 + i]; close = dd.c.loc[d]; w = np.cumsum(rng.normal(0, 0.004, 75)); path = prev * np.exp(w - np.arange(1, 76) / 75 * (w[-1] - np.log(close / prev)))
            for k in range(75): rows.append((d + pd.Timedelta(minutes=OPEN + 5 * k), path[k], dd.v.loc[d] / 75))
        return pd.DataFrame(rows, columns=["t", "c", "v"]).set_index("t")
    D1 = {f"S{i:02d}": fake_daily(0.022, 0.0015) for i in range(N)}
    for i in range(0, N, 4):                                  # planted dips
        k = len(days) - 5 - 3 * i // 4; D1[f"S{i:02d}"].iloc[k:k + 5, 0] *= np.linspace(0.97, 0.85, 5); D1[f"S{i:02d}"].iloc[k + 5:, 0] *= 0.85; D1[f"S{i:02d}"]["rc"] = D1[f"S{i:02d}"].c
    NIF, NB, GB = fake_daily(0.009, 0.0004), fake_daily(0.009, 0.0004), fake_daily(0.008, 0.0003)
    M5 = {s: to_slots(fake_5m(d)) for s, d in D1.items()}; M5N = to_slots(fake_5m(NIF)); M5NB = to_slots(fake_5m(NB)); M5GB = to_slots(fake_5m(GB))
else:
    syms = None
    for u in ["https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv", "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"]:
        b = get(u)
        if b:
            try: syms = sorted(set(pd.read_csv(io.BytesIO(b)).Symbol.dropna().astype(str))); break
            except Exception: pass
    if not syms or len(syms) < 400: raise SystemExit("could not load the Nifty 500 list")
    NIF, NB, GB = ychart("^NSEI", "2y", "1d"), ychart("NIFTYBEES.NS", "2y", "1d"), ychart("GOLDBEES.NS", "2y", "1d")
    M5N, M5NB, M5GB = to_slots(ychart("^NSEI", "60d", "5m")), to_slots(ychart("NIFTYBEES.NS", "60d", "5m")), to_slots(ychart("GOLDBEES.NS", "60d", "5m"))
    if NIF is None or not M5N: raise SystemExit("no Nifty data from Yahoo")
    D1, M5 = {}, {}
    for i, s in enumerate(syms):
        d = ychart(s + ".NS", "2y", "1d")
        if d is not None and len(d) > 260: D1[s] = d
        time.sleep(0.2)
        if i % 100 == 0: print(i, "daily loaded", len(D1), flush=True)
    # members: top 200 by 120-session median traded value, measured before the 5-minute window starts
    first5 = min(M5N)
    tv = {s: float((d.rc * d.v)[d.index < first5].tail(120).median()) for s, d in D1.items()}
    members = sorted([s for s in tv if np.isfinite(tv[s])], key=lambda s: -tv[s])[:TOP]
    for i, s in enumerate(members):
        M5[s] = to_slots(ychart(s + ".NS", "60d", "5m")); time.sleep(0.25)
        if i % 50 == 0: print(i, "5-minute loaded", flush=True)
    D1 = {s: D1[s] for s in members}
print("stocks", len(D1), "| 5-minute days (Nifty)", len(M5N), flush=True)
dates = NIF.index; DS = [d for d in sorted(M5N) if d in dates]
C = pd.DataFrame({s: d.c for s, d in D1.items()}).reindex(dates).ffill(); RC = pd.DataFrame({s: d.rc for s, d in D1.items()}).reindex(dates)
V = pd.DataFrame({s: d.v for s, d in D1.items()}).reindex(dates); n = NIF.c.reindex(dates).ffill()
nb, gb = NB.c.reindex(dates).ffill(), GB.c.reindex(dates).ffill()
TI = {d: i for i, d in enumerate(dates)}; SY = list(D1)
BAD = [0, 0]; SERC = {}
def series(slots, day, adj, raw):
    """5-minute closes for one day scaled to the daily adjusted close (None if missing / doesn't match the daily close)"""
    x = slots.get(day)
    if x is None or len(x[1]) < 10 or not np.isfinite(adj): return None
    m, c, v = x
    if raw is not None and np.isfinite(raw) and abs(c[-1] / raw - 1) > 0.03: return None
    return m, c * adj / c[-1], v
def px(s, day, T):
    k = (s, day)
    if k not in SERC: BAD[1] += 1; SERC[k] = series(M5.get(s, {}), day, C[s].iloc[TI[day]], RC[s].iloc[TI[day]]); BAD[0] += SERC[k] is None
    z = SERC[k]
    if z is None: return float(C[s].iloc[TI[day]]) if T >= FINAL else None
    i = np.searchsorted(z[0], T, side="right") - 1
    return float(z[1][i]) if i >= 0 else None
def vol_so_far(s, day, T):
    z = SERC.get((s, day));
    if z is None: return None
    return float(z[2][z[0] <= T].sum())
def ratio(slots, day, T):
    x = slots.get(day)
    if x is None or len(x[1]) < 10: return None
    i = np.searchsorted(x[0], T, side="right") - 1
    if i < 0: return None
    r = x[1][i] / x[1][-1]; return r if 0.85 < r < 1.15 else None
def nifty_at(day, T):
    r = ratio(M5N, day, T); return n.iloc[TI[day]] * (r if r is not None else 1.0)
def is_dip(s, day, T):
    t = TI[day]; p = px(s, day, T)
    if p is None or t < TREND + 60: return None
    c = C[s].values
    if not (np.isfinite(c[t - 199:t]).all() and np.isfinite(c[t - LOOK])): return None
    if RC[s].iloc[t - 1] <= MINPX: return None
    if not p > np.mean(np.r_[c[t - 199:t], p]): return None
    rel = p / c[t - LOOK] - 1 - (nifty_at(day, T) / n.iloc[t - LOOK] - 1)
    if rel > -DIP: return None
    if (np.abs(np.diff(c[t - 6:t]) / c[t - 6:t - 1]) > 0.35).any() or abs(p / c[t - 1] - 1) > 0.35: return None
    vv = V[s].values; so = vol_so_far(s, day, T); fr = max(0.2, min(1.0, (T - OPEN) / (CLOSE - OPEN)))
    today_v = so / fr if so else vv[t]
    if np.isfinite(vv[t - 54:t]).all() and vv[t - 54:t - 4].mean() > 0 and (vv[t - 4:t].sum() + today_v) / 5 / vv[t - 54:t - 4].mean() > VOLX: return None
    return rel
CHECKS = list(range(585, 901, 15))          # 9:45 am - 3:00 pm IST
def run(intraday=False, target=None, cs=CS, ce=CE):
    cu, liq, pos, park, curve, trades, eb, es = 1.0, 0.0, [], None, [], [], 0, 0
    for day in DS:
        t = TI[day]
        want = "NB" if n.iloc[t - 1] > n.iloc[t - 150:t].mean() else ("GB" if gb.iloc[t - 1] > gb.iloc[t - 100:t].mean() else "LIQ")
        if want != park:
            if park in ("NB", "GB"): cu *= 1 - ce
            if want in ("NB", "GB"): cu *= 1 - ce
            park = want
        r_day = {"NB": nb.iloc[t] / nb.iloc[t - 1] - 1, "GB": gb.iloc[t] / gb.iloc[t - 1] - 1, "LIQ": LIQ}[park]
        def pf(T):
            if park == "LIQ": return 1 + LIQ * (T - OPEN) / (CLOSE - OPEN)
            q = ratio(M5NB if park == "NB" else M5GB, day, T); return (1 + r_day) * q if q is not None else 1 + r_day * (T - OPEN) / (CLOSE - OPEN)
        for p in pos: p["ref"] = C[p["s"]].iloc[t - 1]
        times = sorted(set(CHECKS if (intraday or target) else []) | {FINAL})
        for T in times:
            final, f = T == FINAL, pf(T)
            keep = []
            for p in pos:
                age = t - p["t"]; now = px(p["s"], day, T)
                if now is None or age < 1: keep.append(p); continue
                if final: out = now > np.mean(np.r_[C[p["s"]].values[t - 4:t], now]) or age >= HOLD
                else: out = target is not None and now >= p["px"] * (1 + target)
                if out:
                    cu += p["v"] * now / p["ref"] * (1 - cs) / f; trades.append(now / p["px"] * (1 - cs) / (1 + cs) - 1); es += not final
                else: keep.append(p)
            pos = keep
            if final or intraday:
                eq = cu * f + sum(p["v"] * (px(p["s"], day, T) or p["ref"]) / p["ref"] for p in pos)
                held = {p["s"] for p in pos}
                cand = sorted([(r, s) for s in SY if s not in held and (r := is_dip(s, day, T)) is not None])
                for r, s in cand:
                    if len(pos) >= SLOTS: break
                    a = min(W * eq, cu * f)
                    if a < 0.02 * eq: break
                    p0 = px(s, day, T); cu -= a / f; pos.append({"s": s, "t": t, "px": p0, "ref": p0, "v": a * (1 - cs)}); eb += not final
        cash_close = cu * pf(CLOSE)
        for p in pos: p["v"] *= C[p["s"]].iloc[t] / p["ref"]; p["ref"] = C[p["s"]].iloc[t]
        cu = cash_close; curve.append(cu + sum(p["v"] for p in pos))
    cv = np.array(curve); dd = float((cv / np.maximum.accumulate(cv) - 1).min())
    return {"period_return_pct": round((cv[-1] - 1) * 100, 2), "per_year_pct_rough": round((cv[-1] ** (248 / len(cv)) - 1) * 100, 1), "worst_drop_pct": round(dd * 100, 1),
            "trades": len(trades), "avg_trade_pct": round(float(np.mean(trades)) * 100, 2) if trades else None, "win_pct": round(float(np.mean(np.array(trades) > 0)) * 100) if trades else None,
            "bought_during_day": eb, "sold_during_day": es}
RES = {"sessions": len(DS), "from": str(DS[0].date()), "to": str(DS[-1].date()), "stocks": len(SY)}
for name, kw in (("base: 3:10 pm only (India bot B)", {}), ("+ buy dips during the day (15 min)", dict(intraday=True)), ("+ profit target +5%", dict(target=0.05)),
                 ("+ intraday buys + target +5% (India v3.2-style)", dict(intraday=True, target=0.05)), ("intraday buys + target, 2x costs", dict(intraday=True, target=0.05, cs=0.006, ce=0.003)),
                 ("base, 2x costs", dict(cs=0.006, ce=0.003))):
    RES[name] = run(**kw); a = RES[name]
    print(f"{name:50s} {a['period_return_pct']}% over {len(DS)} sessions (~{a['per_year_pct_rough']}%/yr) worst {a['worst_drop_pct']}% | {a['trades']} trades avg {a['avg_trade_pct']}% win {a['win_pct']}% | intraday buys {a['bought_during_day']} sells {a['sold_during_day']}", flush=True)
# ---------------- per-signal check
both, only_intra = [], []
for day in DS:
    t = TI[day]
    for s in SY:
        first = next((T for T in CHECKS if is_dip(s, day, T) is not None), None)
        if first is None: continue
        p0 = px(s, day, first); pf_ = px(s, day, FINAL)
        if p0 is None or pf_ is None: continue
        if is_dip(s, day, FINAL) is not None: both.append(pf_ / p0 - 1)
        elif t + 1 < len(dates) and dates[t + 1] in TI and np.isfinite(C[s].iloc[t + 1]):
            r1 = C[s].iloc[t + 1] / p0 - 1; r3 = C[s].iloc[min(t + 3, len(dates) - 1)] / p0 - 1 if t + 3 < len(dates) else np.nan
            only_intra.append((r1, r3))
def st_(x):
    x = np.array([v for v in x if np.isfinite(v)]);
    if not len(x): return None
    return {"n": len(x), "avg_pct": round(float(x.mean()) * 100, 2), "median_pct": round(float(np.median(x)) * 100, 2), "share_positive_pct": round(float((x > 0).mean()) * 100), "t_stat": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 else None}
RES["per_signal"] = {"dips_found_during_the_day_and_still_dips_at_3:10__price_3:10_vs_first_seen": st_(both),
                     "note_1": "positive = the price was HIGHER at 3:10 than when first seen, so buying early was cheaper (good for intraday buying)",
                     "dips_that_recovered_by_3:10__return_to_next_close": st_([a for a, _ in only_intra]),
                     "dips_that_recovered_by_3:10__return_to_3_sessions_later": st_([b for _, b in only_intra]),
                     "note_2": "these are extra trades only the intraday version makes; positive average = they pay (costs ~0.6% round trip not included)"}
RES["fallbacks"] = BAD
print("PER-SIGNAL", json.dumps(RES["per_signal"]), flush=True)
print(f"5-minute series: {BAD[1]} looked up, {BAD[0]} missing or not matching the daily close", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": bool(os.environ.get("DRY_FAKE")), "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
