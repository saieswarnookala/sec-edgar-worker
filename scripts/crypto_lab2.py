"""Crypto lab, round 2 (Nov 25 2026). Research only, not financial advice.
Signals on day t's close, traded at day t+1's close. Idle money earns T-bills. Bitcoin (from 2015) and Ether (from 2018), Yahoo daily.
A) Trend robustness: every moving-average length 20-200 (step 10) for BTC and ETH, costs: ETF route 0.05%/side + 0.25%/yr fee, 0.50%, Robinhood 0.95%.
   Placebo: 300 random on/off schedules with the same time invested and the same number of switches as the 50-day rule (shuffled run lengths).
B) Fear & Greed index (alternative.me, from Feb 2018): (1) hold BTC only when the index is below 50 / 80; (2) 50-day trend OR extreme fear (<= 20);
   (3) weekly $100 savings plan vs 2x in extreme fear and 0 in extreme greed (same dates), BTC value per dollar put in.
C) MVRV (Coin Metrics community API, BTC price / average price holders paid): (1) forward 90 / 180 / 365-day BTC returns after MVRV < 1 vs all days;
   (2) 50-day trend OR MVRV < 1; (3) hold, but half out when MVRV is above its rolling 2-year 95th percentile.
D) Funding rates (BitMEX XBTUSD perpetual, from 2016): 30-day average funding < 0 -> hold BTC 90 days; forward returns vs all days; 50-day trend OR that window.
DRY=1: fake data (code test). Data sources that fail are reported and skipped."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/crypto_lab2.json" if not DRY else "/tmp/crypto_lab2_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
rng0 = np.random.default_rng(7)
def get(url, tries=3):
    for a in range(tries):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
        except Exception as e: print("retry", url[:90], str(e)[:80], flush=True); time.sleep(3 * (a + 1))
    return None
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.date_range("2014-09-17", "2026-11-24")
        if sym == "^IRX": return pd.Series(2.0, index=ix)
        return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0015, 0.04, len(ix)))), index=ix)
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1400000000&period2={int(time.time())}&interval=1d")["chart"]["result"][0]
    s = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s").normalize(), dtype=float)
    s = s[~s.index.duplicated(keep="last")]; return s[s > 0]
BTC, ETH = yahoo("BTC-USD"), yahoo("ETH-USD"); cal = pd.date_range(BTC.index[0], BTC.index[-1]); D = len(cal)
PX = pd.DataFrame({"BTC": BTC.reindex(cal).ffill(), "ETH": ETH.reindex(cal).ffill()}); R = PX.pct_change().fillna(0.0)
cash_r = ((1 + yahoo("^IRX").reindex(cal).ffill().bfill().clip(0, 8) / 100) ** (1 / 365) - 1).values
def run(sig, coin, cost, fee=0.0, start=None):
    """sig: Series/array of target weight (0..1) decided at t's close, traded at t+1's close."""
    s = np.nan_to_num(np.asarray(sig, float)); r = R[coin].values; e = 1.0; w = 0.0; eq = np.ones(D); s0 = 0 if start is None else int(np.searchsorted(cal, start))
    for t in range(1, D):
        if t <= s0: eq[t] = 1.0; continue
        rr = w * r[t] + (1 - w) * cash_r[t] - w * fee / 365; e *= 1 + rr
        w = w * (1 + r[t]) / (1 + rr) if rr > -1 else 0.0
        tgt = s[t - 1]
        if abs(tgt - w) > 1e-9 and (tgt in (0.0, 1.0) or abs(tgt - w) > 0.05): e *= 1 - cost * abs(tgt - w); w = tgt
        eq[t] = e
    return eq
def summ(eq, start):
    s = pd.Series(eq, index=cal); s = s[s.index >= start]; out = {}
    for nm, a, b in (("all", "2014", "2100"), ("2015-2019", "2015", "2020"), ("2018-2021", "2018", "2022"), ("2020-2026", "2020", "2100"), ("2023-2026", "2023", "2100")):
        x = s[(s.index >= a) & (s.index < b)]
        if len(x) < 200: continue
        x = x / x.iloc[0]; y = len(x) / 365
        out[nm] = {"per_year_pct": round((x.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((x / x.cummax() - 1).min()) * 100, 1)}
    return out
def pr(n, o): print(f"{n:70s} " + " | ".join(f"{k} {v['per_year_pct']}/{v['worst_drop_pct']}" if isinstance(v, dict) else f"{k} {v}" for k, v in o.items()), flush=True)
START = {"BTC": pd.Timestamp("2015-06-01"), "ETH": pd.Timestamp("2018-06-01")}
COSTS = {"ETF route 0.05% + 0.25%/yr": (0.0005, 0.0025), "0.50%/side": (0.005, 0.0), "Robinhood 0.95%/side": (0.0095, 0.0)}
RES = {"note": __doc__, "A_trend_grid": {}, "A_placebo": {}, "B_fear_greed": {}, "C_mvrv": {}, "D_funding": {}, "data": {}}
# ---------------- A) trend grid + placebo
for coin in ("BTC", "ETH"):
    p = PX[coin]; st = START[coin]
    RES["A_trend_grid"][f"{coin} hold"] = summ(run(np.ones(D), coin, 0.0005, 0.0025, st), st); pr(f"{coin} hold (ETF route)", RES["A_trend_grid"][f"{coin} hold"])
    for n in range(20, 201, 10):
        sig = (p > p.rolling(n).mean()).astype(float).values
        for cl, (c, fee) in COSTS.items():
            k = f"{coin} | above {n}-day | {cl}"; RES["A_trend_grid"][k] = summ(run(sig, coin, c, fee, st), st) | {"switches_per_year": round(float(np.abs(np.diff(sig[cal >= st])).sum()) / ((cal[-1] - st).days / 365), 1)}
            if n in (50, 100, 200) or cl.startswith("ETF"): pr(k, RES["A_trend_grid"][k])
    # placebo vs the 50-day rule (ETF route)
    sig = (p > p.rolling(50).mean()).astype(float).values; ii = cal >= st; base = summ(run(sig, coin, 0.0005, 0.0025, st), st)["all"]["per_year_pct"]
    s_ = sig[ii]; runs = []; cur, ln = s_[0], 0
    for v in s_:
        if v == cur: ln += 1
        else: runs.append((cur, ln)); cur, ln = v, 1
    runs.append((cur, ln)); ons = [l for v, l in runs if v == 1]; offs = [l for v, l in runs if v == 0]; res = []
    for k in range(300):
        a, b = rng0.permutation(ons), rng0.permutation(offs); seq = []
        for i in range(max(len(a), len(b))):
            if i < len(a): seq += [1.0] * a[i]
            if i < len(b): seq += [0.0] * b[i]
        z = np.zeros(D); z[ii] = np.array(seq[:ii.sum()] + [0.0] * max(0, ii.sum() - len(seq)))
        res.append(summ(run(z, coin, 0.0005, 0.0025, st), st)["all"]["per_year_pct"])
    res = np.array(res); RES["A_placebo"][coin] = {"rule_50d_per_year": base, "random_median": float(np.median(res)), "random_95th": float(np.percentile(res, 95)), "share_random_beating_rule_pct": round(float((res >= base).mean()) * 100, 1)}
    print("placebo", coin, RES["A_placebo"][coin], flush=True)
btc = PX["BTC"]; tr50 = (btc > btc.rolling(50).mean()).astype(float); stB = START["BTC"]
# ---------------- B) Fear & Greed
if DRY: fng = pd.Series(np.clip(50 + 30 * np.sin(np.arange(D) / 40), 0, 100), index=cal)
else:
    j = get("https://api.alternative.me/fng/?limit=0&format=json")
    fng = pd.Series({pd.to_datetime(int(x["timestamp"]), unit="s").normalize(): float(x["value"]) for x in j["data"]}).sort_index() if j else None
if fng is not None and len(fng) > 300:
    fng = fng.reindex(cal).ffill(); f0 = fng.first_valid_index() + pd.Timedelta(days=5); RES["data"]["fear_greed_from"] = str(f0.date())
    RES["B_fear_greed"]["BTC hold"] = summ(run(np.ones(D), "BTC", 0.005, 0, f0), f0)
    RES["B_fear_greed"]["50-day trend"] = summ(run(tr50.values, "BTC", 0.005, 0, f0), f0)
    for lbl, sig in (("hold only when index < 50 (fear side)", (fng < 50)), ("hold except when index >= 80 (extreme greed)", (fng < 80)),
                     ("50-day trend OR extreme fear (<= 20)", (tr50 > 0) | (fng <= 20)), ("50-day trend AND index < 80", (tr50 > 0) & (fng < 80))):
        RES["B_fear_greed"][lbl] = summ(run(sig.astype(float).values, "BTC", 0.005, 0, f0), f0)
    for k, v in RES["B_fear_greed"].items(): pr("F&G | " + k + " | 0.50%", v)
    sun = [t for t in range(D) if cal[t] >= f0 and cal[t].weekday() == 6]; px = btc.values
    plain = sum(100 / px[t] for t in sun); paid_plain = 100 * len(sun)
    tilt_units, tilt_paid = 0.0, 0.0
    for t in sun:
        m = 2.0 if fng.values[t] <= 20 else (0.0 if fng.values[t] >= 80 else 1.0); tilt_units += m * 100 / px[t]; tilt_paid += m * 100
    RES["B_fear_greed"]["savings plan"] = {"plain_avg_price": round(paid_plain / plain, 0), "tilted_avg_price": round(tilt_paid / tilt_units, 0), "plain_invested": paid_plain, "tilted_invested": tilt_paid,
                                          "tilted_buys_cheaper_by_pct": round((1 - (tilt_paid / tilt_units) / (paid_plain / plain)) * 100, 1)}
    print("F&G savings plan", RES["B_fear_greed"]["savings plan"], flush=True)
else: RES["B_fear_greed"]["error"] = "alternative.me not reachable"
def fwd(mask, H):
    p = btc.values; idx = np.flatnonzero(np.asarray(mask) & (np.arange(D) + H < D)); allx = np.arange(int(np.argmax(np.asarray(mask) | True)), D - H)
    f = lambda ix: float(np.median(p[ix + H] / p[ix] - 1)) * 100 if len(ix) else None
    return {"days": int(len(idx)), "median_fwd_pct": round(f(idx), 1) if len(idx) else None, "all_days_median_pct": round(f(allx[allx >= int(np.searchsorted(cal, stB))]), 1)}
# ---------------- C) MVRV
mv = None
if DRY: mv = pd.Series(np.exp(np.sin(np.arange(D) / 300)), index=cal)
else:
    url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur&frequency=1d&page_size=10000&start_time=2014-01-01"; rows = []
    while url:
        j = get(url)
        if not j: break
        rows += j.get("data", []); url = j.get("next_page_url")
    if rows: mv = pd.Series({pd.Timestamp(x["time"][:10]): float(x["CapMVRVCur"]) for x in rows if x.get("CapMVRVCur")}).sort_index()
if mv is not None and len(mv) > 300:
    mv = mv.reindex(cal).ffill(); RES["data"]["mvrv_from"] = str(mv.first_valid_index().date())
    low = (mv < 1.0).values
    for H in (90, 180, 365): RES["C_mvrv"][f"forward {H} days after MVRV < 1 (vs all days)"] = fwd(low & (cal >= stB), H)
    hi_band = mv.rolling(730, min_periods=365).quantile(0.95); half = np.where(mv > hi_band, 0.5, 1.0)
    for lbl, sig in (("BTC hold", np.ones(D)), ("50-day trend", tr50.values), ("50-day trend OR MVRV < 1", np.maximum(tr50.values, low.astype(float))),
                     ("hold, half out above the 2-year 95th percentile", half), ("50-day trend, half size above that band", tr50.values * half)):
        RES["C_mvrv"][lbl] = summ(run(sig, "BTC", 0.005, 0, stB), stB); pr("MVRV | " + lbl, RES["C_mvrv"][lbl])
    print("MVRV forward", {k: v for k, v in RES["C_mvrv"].items() if k.startswith("forward")}, flush=True)
else: RES["C_mvrv"]["error"] = "Coin Metrics community API not reachable"
# ---------------- D) funding (BitMEX)
fund = None
if DRY: fund = pd.Series(np.sin(np.arange(D) / 50) * 0.0002 + 0.0001, index=cal)
else:
    rows, startN = [], 0
    for _ in range(40):
        j = get(f"https://www.bitmex.com/api/v1/funding?symbol=XBTUSD&count=500&start={startN}&reverse=false")
        if not j: break
        rows += j; startN += len(j)
        if len(j) < 500: break
        time.sleep(1.2)
    if rows:
        f = pd.Series({pd.Timestamp(x["timestamp"]).tz_localize(None).normalize(): float(x["fundingRate"]) for x in rows}); fund = f.groupby(level=0).mean()
if fund is not None and len(fund) > 300:
    fund = fund.reindex(cal); RES["data"]["funding_from"] = str(fund.first_valid_index().date()); f30 = fund.rolling(30, min_periods=20).mean()
    neg = (f30 < 0).values; starts = neg & ~np.r_[False, neg[:-1]]
    win = np.zeros(D, bool)
    for t in np.flatnonzero(starts): win[t:t + 90] = True
    RES["D_funding"]["episodes_30d_avg_below_zero"] = int(starts.sum())
    for H in (30, 90, 180): RES["D_funding"][f"forward {H} days from each episode start (vs all days)"] = fwd(starts & (cal >= stB), H)
    for lbl, sig in (("BTC hold", np.ones(D)), ("50-day trend", tr50.values), ("50-day trend OR 90 days after negative funding", np.maximum(tr50.values, win.astype(float)))):
        RES["D_funding"][lbl] = summ(run(sig, "BTC", 0.005, 0, stB), stB); pr("FUND | " + lbl, RES["D_funding"][lbl])
    print("funding", {k: v for k, v in RES["D_funding"].items() if not isinstance(v, dict) or "days" in v}, flush=True)
else: RES["D_funding"]["error"] = "BitMEX funding not reachable"
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
