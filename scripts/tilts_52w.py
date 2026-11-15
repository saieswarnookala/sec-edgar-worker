"""52-week-high and same-month seasonality tests on point-in-time S&P 500 members (incl. companies that later left
or failed), Nov 15 2026. Research only, not financial advice. The published evidence ends ~2016-2017, so 2017-2026 here
is a clean out-of-sample check.
A) Monthly tilts, long-only, equal weight, rebalanced at each month-end close, held one month:
   - 52-week high: stocks closest to their 52-week high (price / highest close of the past 252 days), top 10% and 20%
   - seasonality: stocks with the best average return in the SAME calendar month over the past 10 years (>= 5 years of data)
   - both combined (average of the two ranks)
   compared with all members equal-weighted and SPY. Cost 0.10% per side on the part of the portfolio that changes.
B) 52-week-high as a filter on the dip bot's own signals (5-day drop >= 10% vs SPY, above 200-day avg, normal volume,
   price >= $5): trade return with the bot's sell rule (back above the 5-day average, max 5 days), bought at the close,
   split by how far below the 52-week high the stock was."""
import os, json, time, urllib.request
import numpy as np, pandas as pd

REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1996-01-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
if "SPY" not in set(px.ticker): raise SystemExit("SPY missing from price data")
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOL = P("adj_close"), P("close"), P("volume"); del px
tick = [t for t in ALLT if t != "SPY"]
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
print("tickers", len(tick), "with prices", int(A[tick].notna().any().sum()), dates[0].date(), dates[-1].date(), flush=True)
C = A[tick].ffill(limit=5); spy = A["SPY"].ffill()
prox = C / C.rolling(252, min_periods=240).max()
COST = 0.001
# ---------- A) monthly tilts ----------
me = pd.Series(dates, index=dates).groupby(dates.to_period("M")).max().values     # month-end trading days
me = pd.DatetimeIndex(me)
Cm = C.reindex(me); Mm = M.reindex(me); Pm = prox.reindex(me); SPm = spy.reindex(me)
mret = Cm.pct_change(fill_method=None).shift(-1)       # next month's return, decided at this month-end
# same-calendar-month seasonality: average return in this coming calendar month over the past 10 years
fwd_month = (me + pd.offsets.MonthEnd(1)).month
past = {}
seas = pd.DataFrame(np.nan, index=me, columns=tick)
R = Cm.pct_change(fill_method=None)                     # return OF the month ending at that row
for k, d in enumerate(me):
    target = fwd_month[k]
    rows = [j for j in range(max(0, k - 130), k) if me[j].month == target]          # same month in prior ~10 years
    if len(rows) >= 5: seas.iloc[k] = R.iloc[rows].mean().values
valid = Mm & Cm.notna() & mret.notna() & (RAW[tick].reindex(me) >= 5)
def portfolio(score, top):
    w_prev = pd.Series(0.0, index=tick); rets, dts = [], []
    for k, d in enumerate(me[:-1]):
        v = valid.iloc[k] & score.iloc[k].notna()
        if v.sum() < 50: continue
        s = score.iloc[k][v]; n = max(1, int(len(s) * top)); pick = s.nlargest(n).index
        w = pd.Series(0.0, index=tick); w[pick] = 1.0 / n
        turn = (w - w_prev).abs().sum(); r = float((w[pick] * mret.iloc[k][pick]).sum()) - turn * COST
        rets.append(r); dts.append(me[k + 1]); w_prev = w * (1 + mret.iloc[k].fillna(0)); w_prev /= max(w_prev.sum(), 1e-12)
    return pd.Series(rets, index=dts)
def eqw():
    rets, dts = [], []
    for k, d in enumerate(me[:-1]):
        v = valid.iloc[k]
        if v.sum() < 50: continue
        rets.append(float(mret.iloc[k][v].mean())); dts.append(me[k + 1])
    return pd.Series(rets, index=dts)
EW = eqw(); SPYm = SPm.pct_change().shift(-1).reindex(me[:-1]); SPYm.index = me[1:]
rank = lambda df: df.rank(axis=1, pct=True)
SC = {"52-week high: top 10%": (prox.reindex(me), 0.10), "52-week high: top 20%": (prox.reindex(me), 0.20),
      "52-week high: bottom 10% (farthest below)": (-prox.reindex(me), 0.10),
      "seasonality: top 10%": (seas, 0.10), "seasonality: top 20%": (seas, 0.20),
      "52w high + seasonality: top 10%": ((rank(prox.reindex(me).where(valid)) + rank(seas.where(valid))) / 2, 0.10)}
PER = {"1999-2016": ("1999-01-01", "2017-01-01"), "2017-2026 (out-of-sample)": ("2017-01-01", "2100-01-01")}
def stats(r, base):
    out = {}
    for pn, (a, b) in PER.items():
        x = r[(r.index >= a) & (r.index < b)].dropna(); y = base.reindex(x.index)
        if len(x) < 24: continue
        cum = (1 + x).cumprod(); yrs = len(x) / 12; ex = x - y
        out[pn] = {"per_year_pct": round((cum.iloc[-1] ** (1 / yrs) - 1) * 100, 1), "worst_drop_pct": round(float((cum / cum.cummax() - 1).min()) * 100, 1),
                   "vs_equal_weight_per_month_pct": round(float(ex.mean()) * 100, 2), "t": round(float(ex.mean() / (ex.std(ddof=1) or 1e-9) * np.sqrt(len(ex))), 2),
                   "months_beating_pct": round(float((ex > 0).mean()) * 100, 0)}
    return out
partA = {"equal-weight all members": stats(EW, EW), "SPY": stats(SPYm, EW)}
for name, (score, top) in SC.items():
    partA[name] = stats(portfolio(score, top), EW); print(name, partA[name], flush=True)
# ---------- B) 52-week high as a dip-bot filter ----------
with np.errstate(all="ignore"):
    spy5 = spy / spy.shift(5) - 1
    ex5 = (C / C.shift(5) - 1).sub(spy5, axis=0)
    vr = VOL[tick].rolling(5).mean() / VOL[tick].shift(5).rolling(50).mean()
    ma5 = C.rolling(5).mean()
    dip = (M & (C > C.rolling(200).mean()) & (ex5 <= -0.10) & (RAW[tick] >= 5) & (vr <= 2.0)).values
    Cv, M5 = C.values, ma5.values; D = len(dates)
    out_px = np.full(Cv.shape, np.nan); done = np.zeros(Cv.shape, bool)
    for k in range(1, 6):
        ck = np.vstack([Cv[k:], np.full((k, Cv.shape[1]), np.nan)]); mk = np.vstack([M5[k:], np.full((k, Cv.shape[1]), np.nan)])
        hit = ~done & ((ck > mk) | (k == 5)); out_px[hit] = ck[hit]; done |= hit
    tr = out_px / Cv - 1 - 2 * 0.0005
    pv = prox.values
G = {"all dip signals": np.ones_like(dip), "within 10% of 52w high": pv >= 0.90, "10-20% below": (pv >= 0.80) & (pv < 0.90),
     "20-30% below": (pv >= 0.70) & (pv < 0.80), "30%+ below": pv < 0.70}
dn = dates.values; PB = {**{k: (np.datetime64(a), np.datetime64(b)) for k, (a, b) in PER.items()}}
partB = {}
for g, gm in G.items():
    partB[g] = {}
    for pn, (a, b) in PB.items():
        m = dip & gm & ((dn >= a) & (dn < b))[:, None]; x = tr[m]; x = x[~np.isnan(x)]
        partB[g][pn] = {"n": int(len(x)), "avg_trade_pct": round(float(x.mean()) * 100, 2) if len(x) else None, "win_pct": round(float((x > 0).mean()) * 100, 1) if len(x) else None}
    print("DIP", g, partB[g], flush=True)
json.dump({"note": __doc__, "monthly_tilts": partA, "dip_filter": partB}, open("data/tilts_52w.json", "w"), indent=1)
