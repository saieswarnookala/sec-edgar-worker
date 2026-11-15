"""Candle ("bar reading") test, Nov 14 2026. Research only, not financial advice.
Part A: classic daily candle patterns on point-in-time S&P 500 stocks 1999-2026 (incl. companies that later failed) and SPY.
  Hammer (long lower tail), shooting star (long upper tail), bullish/bearish engulfing, doji, strong/weak close,
  inside/outside day; each alone, after a drop, or in an uptrend. Trade the next open (realistic) or that close,
  hold 1/3/5 days. Every trade is compared with the average member stock over the same days (excess), signed so a
  bearish pattern counts when the stock then lags. Rules are judged on 1999-2012 AND 2013-2026 separately.
Part B: candle shape as a filter on the dip bot's own signals (5-day drop >= 10% vs SPY, above 200-day avg, normal volume):
  do dips that close well off the day's low (a tail) bounce better than dips that close at the low?
  Measured with the bot's sell rule (back above the 5-day average, max 5 days), bought at the close."""
import os, json, time, urllib.request
import numpy as np, pandas as pd

REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
f = px.adj_close / px.close
for c in ("open", "high", "low"): px[c] = px[c] * f
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT).values
O, H, L, C, V, RAW = P("open"), P("high"), P("low"), P("adj_close"), P("volume"), P("close"); del px
D, N = C.shape; si = ALLT.index("SPY")
M = np.zeros((D, N), bool); di = {d: i for i, d in enumerate(dates)}
for _, m in mem.iterrows():
    if m.ticker in ALLT:
        j = ALLT.index(m.ticker); a = dates.searchsorted(m.start); b = dates.searchsorted(m.end) if pd.notna(m.end) else D
        M[a:b, j] = True
M[:, si] = False
print("days", D, "tickers", N, dates[0].date(), dates[-1].date(), flush=True)
sh = lambda X, k: np.vstack([X[k:], np.full((k, X.shape[1]), np.nan)]) if k > 0 else np.vstack([np.full((-k, X.shape[1]), np.nan), X[:k]])
with np.errstate(all="ignore"):
    rng_ = H - L; body = np.abs(C - O); up_sh = H - np.maximum(O, C); lo_sh = np.minimum(O, C) - L
    clv = (C - L) / rng_                                   # where the close sits in the day's range: 0 = at the low, 1 = at the high
    Cp, Op = sh(C, -1), sh(O, -1)
    r5 = C / sh(C, -5) - 1; ma200 = pd.DataFrame(C).rolling(200, min_periods=150).mean().values
    ma5 = pd.DataFrame(C).rolling(5).mean().values
    atr = pd.DataFrame(rng_).rolling(14, min_periods=10).mean().values
    valid = (rng_ > 0) & (rng_ >= 0.3 * atr)               # skip tiny, meaningless bars
    green, red = C > O, C < O
    PAT = {
        "hammer (long lower tail)": valid & (lo_sh >= 2 * body) & (up_sh <= 0.3 * rng_),
        "shooting star (long upper tail)": valid & (up_sh >= 2 * body) & (lo_sh <= 0.3 * rng_),
        "bullish engulfing": valid & green & (sh(red, -1) == 1) & (O <= Cp) & (C >= Op),
        "bearish engulfing": valid & red & (sh(green, -1) == 1) & (O >= Cp) & (C <= Op),
        "doji": valid & (body <= 0.1 * rng_),
        "strong close (top 20% of range)": valid & (clv >= 0.8),
        "weak close (bottom 20% of range)": valid & (clv <= 0.2),
        "inside day": valid & (H < sh(H, -1)) & (L > sh(L, -1)),
        "outside day, closes up": valid & (H > sh(H, -1)) & (L < sh(L, -1)) & green,
        "outside day, closes down": valid & (H > sh(H, -1)) & (L < sh(L, -1)) & red}
    BULL = {"hammer (long lower tail)", "bullish engulfing", "strong close (top 20% of range)", "outside day, closes up", "doji", "inside day"}
    spy = C[:, si]; spy5 = spy / np.r_[np.full(5, np.nan), spy[:-5]] - 1
    CTX = {"any": np.ones((D, N), bool), "after a 5%+ drop (5 days)": r5 <= -0.05, "in an uptrend (above 200-day)": C > ma200}
    ok = M.copy()
    for k in range(1, 6): ok &= ~np.isnan(sh(C, k)) & ~np.isnan(sh(O, 1))
    R, B = {}, {}
    for k in (1, 3, 5):
        R[("next open", k)] = sh(C, k) / sh(O, 1) - 1
        R[("close", k)] = sh(C, k) / C - 1
    for key, X in R.items(): B[key] = np.array([np.nanmean(X[i][ok[i]]) if ok[i].any() else np.nan for i in range(D)])
dn = dates.values; PER = {"1999-2012": (dn >= np.datetime64("1999-01-01")) & (dn < np.datetime64("2013-01-01")), "2013-2026": dn >= np.datetime64("2013-01-01")}
COST = 0.0005
res = []
for pn, pm in PAT.items():
    sign = 1 if pn in BULL else -1
    for cn, cm in CTX.items():
        sel = pm & cm & ok
        for (en, k), X in R.items():
            row = {"pattern": pn, "expect": "up" if sign > 0 else "down", "context": cn, "entry": en, "hold_days": k}
            for per, mask in PER.items():
                m = sel & mask[:, None]; I, J = np.nonzero(m)
                if len(I) < 50: row[per] = {"n": int(len(I))}; continue
                ex = sign * (X[I, J] - B[(en, k)][I]); raw = sign * X[I, J] - 2 * COST
                row[per] = {"n": int(len(I)), "excess_bps": round(float(np.nanmean(ex)) * 1e4, 1), "after_cost_bps": round(float(np.nanmean(raw)) * 1e4, 1),
                            "hit_pct": round(float(np.nanmean(ex > 0)) * 100, 1),
                            "t": round(float(np.nanmean(ex) / (np.nanstd(ex) or 1e-9) * np.sqrt(len(I) / k)), 2)}
            res.append(row)
both = [r for r in res if all(r[p].get("n", 0) >= 50 for p in PER)]
consistent = [r for r in both if all(r[p]["excess_bps"] > 0 and r[p]["t"] > 2 for p in PER)]
consistent.sort(key=lambda r: -min(r[p]["excess_bps"] for p in PER))
# SPY alone
spyres = []
for pn, pm in PAT.items():
    sign = 1 if pn in BULL else -1; col = pm[:, si]
    for (en, k) in [("next open", 1), ("next open", 3), ("next open", 5)]:
        X = (np.r_[spy[k:], np.full(k, np.nan)] / np.r_[O[1:, si], np.nan] - 1)
        row = {"pattern": pn, "hold_days": k}
        for per, mask in PER.items():
            m = col & mask & ~np.isnan(X); x = sign * X[m]; base = sign * np.nanmean(X[mask])
            row[per] = {"n": int(m.sum()), "avg_bps": round(float(np.nanmean(x)) * 1e4, 1) if m.sum() else None, "vs_any_day_bps": round(float(np.nanmean(x) - base) * 1e4, 1) if m.sum() else None}
        spyres.append(row)

# ---- Part B: candle shape on the dip bot's signals ----
with np.errstate(all="ignore"):
    ex5 = r5 - spy5[:, None]
    vr = pd.DataFrame(V).rolling(5).mean().values / pd.DataFrame(V).shift(5).rolling(50).mean().values
    dip = ok & (C > ma200) & (ex5 <= -0.10) & (RAW >= 5) & (vr <= 2.0)
    # bot exit: first close (day 1..5) above the 5-day avg, else day 5
    out = np.full((D, N), np.nan); done = np.zeros((D, N), bool)
    for k in range(1, 6):
        ck, mk = sh(C, k), sh(ma5, k); hit = ~done & ((ck > mk) | (k == 5)); out[hit] = ck[hit]; done |= hit
    tr = out / C - 1 - 2 * COST
GROUPS = {"all dip signals": dip, "closed at the low (CLV<0.2)": dip & (clv < 0.2), "closed low-ish (0.2-0.5)": dip & (clv >= 0.2) & (clv < 0.5),
          "closed off the low (CLV>=0.5)": dip & (clv >= 0.5), "hammer tail (lower tail >= 2x body)": dip & PAT["hammer (long lower tail)"],
          "green day (close > open)": dip & green, "red day (close < open)": dip & red, "bullish engulfing": dip & PAT["bullish engulfing"]}
partB = {}
for g, m0 in GROUPS.items():
    partB[g] = {}
    for per, mask in {**PER, "1999-2026": PER["1999-2012"] | PER["2013-2026"]}.items():
        I, J = np.nonzero(m0 & mask[:, None]); x = tr[I, J]; x = x[~np.isnan(x)]
        partB[g][per] = {"n": int(len(x)), "avg_trade_pct": round(float(x.mean()) * 100, 2) if len(x) else None, "win_pct": round(float((x > 0).mean()) * 100, 1) if len(x) else None}
json.dump({"note": __doc__, "consistent_patterns": consistent[:25], "n_versions": len(both), "n_consistent": len(consistent),
           "expected_by_luck_both_halves": round(len(both) * 0.023 * 0.023 * 4, 2), "spy": spyres, "dip_filter": partB, "all": res},
          open("data/candles.json", "w"), indent=1)
print("versions", len(both), "consistent (t>2 both halves)", len(consistent), flush=True)
for r in consistent[:15]: print(r["pattern"], "|", r["context"], "|", r["entry"], r["hold_days"], "|", r["1999-2012"], "|", r["2013-2026"])
for g, v in partB.items(): print("DIP", g, v)
