"""Crypto lab, round 4 (Nov 25 2026): is the 50-day trend rule real or luck? Research only, not financial advice.
1) Unseen coins: the same rule (above the 50-day average, else T-bills; next-day trade; 0.10%/side) on 20 other large coins it was never tuned on.
2) Rolling windows: in every 1-year and 2-year window since 2016, did the rule beat holding (return) and lose less (worst drop)?
3) Walk-forward: each year pick the average length (20-200) that did best in all EARLIER years, use it for that year only.
4) Late trading: the switch done 1, 2 or 3 days late (slow human / missed alert).
5) Luck check: deflated Sharpe (Bailey & Lopez de Prado) for the BTC 50-day rule, counting every length we looked at (19) x 3 cost levels.
DRY=1: fake prices."""
import os, json, time, math, urllib.request
from statistics import NormalDist
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/crypto_lab4.json" if not DRY else "/tmp/crypto_lab4_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.date_range("2014-09-17", "2026-11-24")[int(rng.integers(0, 1500)):]
        if sym == "^IRX": return pd.Series(2.0, index=pd.date_range("2014-09-17", "2026-11-24"))
        return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.05, len(ix)))), index=ix)
    for a in range(3):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1400000000&period2={int(time.time())}&interval=1d", headers=UA), timeout=60).read())["chart"]["result"][0]
            s = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s").normalize(), dtype=float)
            s = s[~s.index.duplicated(keep="last")]; return s[s > 0]
        except Exception as e: print("retry", sym, str(e)[:60], flush=True); time.sleep(4)
    return None
BTC = yahoo("BTC-USD"); cal = pd.date_range(BTC.index[0], BTC.index[-1]); D = len(cal)
irx = yahoo("^IRX"); cash_r = ((1 + irx.reindex(cal).ffill().bfill().clip(0, 8) / 100) ** (1 / 365) - 1).values
def curve(p, sig, cost=0.001, lag=1):
    """p: price Series on cal (NaN before listing); sig: 0/1 array decided at t's close; trade at t+lag close."""
    r = p.pct_change().fillna(0).values; e = 1.0; w = 0.0; out = np.full(D, np.nan); first = int(np.argmax(p.notna().values)); s = np.nan_to_num(sig)
    for t in range(first + 1, D):
        rr = w * r[t] + (1 - w) * cash_r[t]; e *= 1 + rr; w = w * (1 + r[t]) / (1 + rr) if rr > -1 else 0
        tgt = s[t - lag] if t - lag >= 0 else 0
        if tgt != w and abs(tgt - w) > 0.5: e *= 1 - cost; w = tgt
        out[t] = e
    return out
def stats(eq, a=None, b=None):
    s = pd.Series(eq, index=cal).dropna()
    if a: s = s[(s.index >= a) & (s.index < b)]
    if len(s) < 60: return None
    s = s / s.iloc[0]; y = len(s) / 365
    return {"per_year_pct": round((s.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((s / s.cummax() - 1).min()) * 100, 1)}
def trend(p, n): return (p > p.rolling(n).mean()).astype(float).values
RES = {"note": __doc__, "unseen_coins": {}, "rolling": {}, "walk_forward": {}, "late": {}, "luck": {}}
# 1) unseen coins (start each from 200 days after its listing)
OTHER = ["XRP", "LTC", "BCH", "ADA", "DOGE", "SOL", "DOT", "LINK", "AVAX", "TRX", "XLM", "BNB", "ETC", "XMR", "ATOM", "UNI", "FIL", "ALGO", "VET", "EOS"]
wins_r = wins_d = n = 0
for c in OTHER:
    s = yahoo(f"{c}-USD")
    if s is None or len(s) < 700: print("skip", c); continue
    p = s.reindex(cal).ffill().where(cal >= s.index[0]); st0 = s.index[0] + pd.Timedelta(days=200); p = p.where(cal >= st0)
    h = stats(curve(p, np.ones(D))); t50 = stats(curve(p, trend(p, 50)))
    RES["unseen_coins"][c] = {"from": str(st0.date()), "hold": h, "rule_50d": t50}; n += 1; wins_r += t50["per_year_pct"] > h["per_year_pct"]; wins_d += t50["worst_drop_pct"] > h["worst_drop_pct"]
    print(f"{c:5s} from {st0.date()} hold {h['per_year_pct']}/{h['worst_drop_pct']}  rule {t50['per_year_pct']}/{t50['worst_drop_pct']}", flush=True)
RES["unseen_coins"]["summary"] = {"coins": n, "rule_beat_hold_on_return": wins_r, "rule_had_smaller_worst_drop": wins_d}
# 2) rolling windows (BTC from 2016, ETH from 2018)
ETH = yahoo("ETH-USD"); PXS = {"BTC": BTC.reindex(cal).ffill(), "ETH": ETH.reindex(cal).ffill().where(cal >= ETH.index[0])}
for coin, p in PXS.items():
    eh, et = curve(p, np.ones(D)), curve(p, trend(p, 50)); s0 = pd.Timestamp("2016-01-01" if coin == "BTC" else "2018-06-01"); o = {}
    for yrs in (1, 2):
        ends = pd.date_range(s0 + pd.DateOffset(years=yrs), cal[-1], freq="MS"); rb = db = nw = 0
        for e_ in ends:
            a = e_ - pd.DateOffset(years=yrs); x, y = stats(et, a, e_), stats(eh, a, e_)
            if not x or not y: continue
            nw += 1; rb += x["per_year_pct"] > y["per_year_pct"]; db += x["worst_drop_pct"] > y["worst_drop_pct"]
        o[f"{yrs}-year windows"] = {"windows": nw, "rule_beat_hold_pct": round(rb / max(nw, 1) * 100, 0), "rule_smaller_drop_pct": round(db / max(nw, 1) * 100, 0)}
    RES["rolling"][coin] = o; print("rolling", coin, o, flush=True)
# 3) walk-forward over average lengths
for coin, p in PXS.items():
    Ns = list(range(20, 201, 10)); eqs = {N: curve(p, trend(p, N)) for N in Ns}; years = range(2017 if coin == "BTC" else 2020, 2027); chain, picks = [], {}
    yr_ret = lambda eq, y: (lambda s: s.iloc[-1] / s.iloc[0] - 1 if len(s) > 30 else None)(pd.Series(eq, index=cal).dropna()[lambda s: (s.index.year == y) | (s.index == pd.Timestamp(f"{y-1}-12-31"))])
    for y in years:
        past = lambda N: np.prod([1 + (yr_ret(eqs[N], k) or 0) for k in range(cal[0].year + 1, y)])
        best = max(Ns, key=past); picks[y] = best; r_ = yr_ret(eqs[best], y)
        if r_ is not None: chain.append(r_)
    fixed = [yr_ret(eqs[50], y) for y in years]; hold = [yr_ret(curve(p, np.ones(D)), y) for y in years]
    g = lambda L: round((np.prod([1 + x for x in L if x is not None]) ** (1 / len([x for x in L if x is not None])) - 1) * 100, 1)
    RES["walk_forward"][coin] = {"years": f"{min(years)}-{max(years)}", "walk_forward_per_year": g(chain), "fixed_50d_per_year": g(fixed), "hold_per_year": g(hold), "picks": picks}
    print("walk-forward", coin, RES["walk_forward"][coin], flush=True)
# 4) late trading
for coin, p in PXS.items():
    RES["late"][coin] = {("on time (next close)" if lag == 1 else f"{lag - 1} day(s) late"): stats(curve(p, trend(p, 50), lag=lag)) for lag in (1, 2, 3, 4)} | {"hold": stats(curve(p, np.ones(D)))}
    print("late", coin, RES["late"][coin], flush=True)
# 5) deflated Sharpe, BTC
p = PXS["BTC"]; Z = NormalDist(); g_ = 0.5772156649
def dsr_stats(eq):
    s = pd.Series(eq, index=cal).dropna(); s = s[s.index >= "2015-06-01"]; r = s.pct_change().dropna().values; m, sd = r.mean(), r.std(ddof=1); z = (r - m) / sd
    return m / sd, float((z ** 3).mean()), float((z ** 4).mean()), len(r)
srs = []
for N in range(20, 201, 10):
    for c_ in (0.0005, 0.005, 0.0095): srs.append(dsr_stats(curve(p, trend(p, N), c_))[0])
sr, sk, ku, T = dsr_stats(curve(p, trend(p, 50), 0.0005)); V = float(np.var(srs, ddof=1)); Nt = len(srs)
sr0 = math.sqrt(V) * ((1 - g_) * Z.inv_cdf(1 - 1 / Nt) + g_ * Z.inv_cdf(1 - 1 / (Nt * math.e)))
dsr = Z.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2))
hs = dsr_stats(curve(p, np.ones(D), 0.0005))[0]
RES["luck"] = {"trials": Nt, "sharpe_50d": round(sr * math.sqrt(365), 2), "sharpe_hold": round(hs * math.sqrt(365), 2), "luck_bar_sharpe": round(sr0 * math.sqrt(365), 2), "deflated_sharpe_prob": round(dsr, 4),
               "t_stat": round(sr * math.sqrt(T), 2)}
print("luck", RES["luck"], flush=True)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
