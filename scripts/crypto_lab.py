"""Crypto lab, round 1 (Nov 24 2026). Research only, not financial advice.
Data: Yahoo daily (USD) for ~40 large coins INCLUDING dead / collapsed ones (Terra LUNC, FTT, BSV, EOS, ...) to soften survivorship bias;
^IRX T-bills for idle cash. Signals on day t's close, trades at day t+1's close (no look-ahead). Every calendar day (crypto trades 7 days).
Costs per side: 0.10% (exchange / spot ETF), 0.50%, 0.95% (Robinhood Crypto's published spread markup).
1) Faster trend rules on BTC and ETH: 20/50/100/200-day average, 10/30-day EMA cross, Donchian 20-day high in / 10-day low out, + 40% volatility target.
2) Rotation momentum: each week, among the 20 most-traded coins with 1+ year of history (by 30-day dollar volume, decided that day), hold the top 3 or 5
   by last 1 / 2 / 4 weeks' return, equal weight; optional BTC trend filter (cash when BTC < its 50 / 200-day average).
3) Crypto dip bot: coins (same universe) that fell 15% / 20% more than BTC in 5 days and are above their own 100-day average; up to 5 slots x 20%;
   sell on a close above the 5-day average or after 5 / 10 days; idle money in cash (T-bills) or BTC when BTC > 200-day.
4) Pattern matching (analogues): today's last 20 daily returns vs every earlier 20-day window (z-scored shape); the 25 nearest analogues'
   next-5-day returns; hold BTC (or ETH) for 5 days when their average is > 0. Walk-forward from 2018, only past windows used.
5) Calendar: average daily return by weekday (two halves), weekend-only vs weekday-only holding, turn of month (last 2 + first 3 days).
DRY=1: fake prices (code test)."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/crypto_lab.json" if not DRY else "/tmp/crypto_lab_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
COINS = ["BTC", "ETH", "XRP", "LTC", "BCH", "ADA", "DOGE", "SOL", "DOT", "LINK", "AVAX", "MATIC", "TRX", "XLM", "BNB", "ETC", "XMR", "EOS", "ATOM", "UNI",
         "FIL", "ALGO", "VET", "ICP", "NEAR", "LUNC", "FTT", "XEM", "DASH", "ZEC", "NEO", "MIOTA", "WAVES", "BSV", "SHIB", "HBAR", "XTZ", "THETA", "AAVE", "SAND"]
def yahoo(sym, with_vol=False):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.date_range("2014-09-17", "2026-11-23")
        if sym == "^IRX": return pd.Series(2.0, index=ix)
        start = rng.integers(0, 1500); ix = ix[start:]
        p = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.05, len(ix)))), index=ix); v = pd.Series(rng.lognormal(17, 1, len(ix)), index=ix)
        return (p, v) if with_vol else p
    for a in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1400000000&period2={int(time.time())}&interval=1d", headers=UA), timeout=60).read()
            j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]["quote"][0]; ix = pd.to_datetime(j["timestamp"], unit="s").normalize()
            p = pd.Series(q["close"], index=ix, dtype=float); v = pd.Series(q.get("volume"), index=ix, dtype=float)
            p = p[~p.index.duplicated(keep="last")]; v = v[~v.index.duplicated(keep="last")]
            ok = p > 0; p, v = p[ok], v.reindex(p[ok].index)
            return (p, v) if with_vol else p
        except Exception as e: print("retry", sym, str(e)[:80], flush=True); time.sleep(3 * (a + 1))
    return (None, None) if with_vol else None
P, V = {}, {}
for c in COINS:
    p, v = yahoo(f"{c}-USD", True)
    if p is None or len(p) < 400: print("skip", c, flush=True); continue
    P[c], V[c] = p, v; print(c, p.index[0].date(), "->", p.index[-1].date(), len(p), flush=True)
cal = pd.date_range(P["BTC"].index[0], P["BTC"].index[-1])
PX = pd.DataFrame({c: s.reindex(cal) for c, s in P.items()})            # no ffill: a dead coin simply stops (handled below)
VOL = pd.DataFrame({c: s.reindex(cal) for c, s in V.items()})
LASTPX = PX.ffill(); R = LASTPX.pct_change().fillna(0.0)                  # after a coin's data ends its return is 0 (we assume we sold at the last price)
irx = yahoo("^IRX"); cash_r = ((1 + irx.reindex(cal).ffill().bfill().clip(0, 8) / 100) ** (1 / 365) - 1).values
D = len(cal); dn = cal
def summ(eq, start=None):
    s = pd.Series(eq, index=dn); s = s[s.index >= (start or s.index[0])]
    out = {}
    for nm, a, b in (("all", "2014", "2100"), ("2015-2019", "2015", "2020"), ("2020-2026", "2020", "2100"), ("2023-2026", "2023", "2100")):
        x = s[(s.index >= a) & (s.index < b)]
        if len(x) < 200: continue
        x = x / x.iloc[0]; y = len(x) / 365
        out[nm] = {"per_year_pct": round((x.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((x / x.cummax() - 1).min()) * 100, 1)}
    y22 = s[(s.index >= "2022-01-01") & (s.index < "2023-01-01")]
    if len(y22) > 300: out["2022"] = round((y22.iloc[-1] / y22.iloc[0] - 1) * 100, 1)
    return out
def pr(name, o): print(f"{name:72s} " + " | ".join(f"{k} {v['per_year_pct']}/{v['worst_drop_pct']}" if isinstance(v, dict) else f"{k} {v}" for k, v in o.items()), flush=True)
def run_weights(W, cost):
    """W: DataFrame of target weights decided at day t close (rows sum <= 1); traded at t+1 close; return earned from t+2 on.
       Equity follows the held weights (drifting), cash earns T-bills."""
    Wv = np.nan_to_num(W.values); Rv = R.values; eq = np.ones(D); w = np.zeros(Wv.shape[1]); e = 1.0
    for t in range(1, D):
        r = float(w @ Rv[t]) + (1 - w.sum()) * cash_r[t]; e *= 1 + r
        if r > -1: w = w * (1 + Rv[t]) / (1 + r)
        tgt = Wv[t - 1]                                                     # decided yesterday, traded today at the close
        if not np.allclose(tgt, w, atol=1e-9):
            e *= 1 - cost * np.abs(tgt - w).sum(); w = tgt.copy()
        eq[t] = e
    return eq
RES = {"note": __doc__, "coins": {c: [str(P[c].index[0].date()), str(P[c].index[-1].date())] for c in P}, "trend": {}, "rotation": {}, "dip": {}, "patterns": {}, "calendar": {}}
COSTS = (0.001, 0.005, 0.0095)
cidx = {c: i for i, c in enumerate(PX.columns)}
# ---------------- 1) trend on BTC / ETH
def tsig(p, rule):
    if rule == "hold": return pd.Series(1.0, index=p.index)
    if rule.endswith("d"): n = int(rule[:-1]); return (p > p.rolling(n).mean()).astype(float)
    if rule == "ema10/30": return (p.ewm(span=10).mean() > p.ewm(span=30).mean()).astype(float)
    if rule == "donchian20/10":
        hi, lo = p.rolling(20).max().shift(1), p.rolling(10).min().shift(1); s = pd.Series(np.nan, index=p.index)
        s[p > hi] = 1.0; s[p < lo] = 0.0; return s.ffill().fillna(0.0)
for coin in ("BTC", "ETH"):
    p = LASTPX[coin]; first = P[coin].index[0] + pd.Timedelta(days=200)
    for rule in ("hold", "20d", "50d", "100d", "200d", "ema10/30", "donchian20/10"):
        for vt in (None, 0.40):
            if rule == "hold" and vt: continue
            s = tsig(p, rule)
            if vt:
                rv = R[coin].rolling(30).std() * np.sqrt(365); s = s * (vt / rv).clip(upper=1.0)
            W = pd.DataFrame(0.0, index=dn, columns=PX.columns); W[coin] = s.where(dn >= first, 0.0) if rule != "hold" else (dn >= first).astype(float)
            for cost in COSTS:
                if rule == "hold" and cost != 0.001: continue
                nm = f"{coin} | {rule}{' + 40% vol target' if vt else ''} | cost {cost*100:.2f}%/side"
                RES["trend"][nm] = summ(run_weights(W, cost), first); pr(nm, RES["trend"][nm])
# ---------------- universe: top 20 by 30-day dollar volume, 1+ year of history, still trading
DV = (PX * VOL).rolling(30, min_periods=20).mean()
AGE = PX.notna().cumsum()
ELIG = (AGE >= 365) & PX.notna()
RANKV = DV.where(ELIG).rank(axis=1, ascending=False)
U20 = RANKV <= 20
# ---------------- 2) rotation momentum
btc = LASTPX["BTC"]; F = {"none": pd.Series(True, index=dn), "BTC > 50d": btc > btc.rolling(50).mean(), "BTC > 200d": btc > btc.rolling(200).mean()}
start_rot = pd.Timestamp("2017-01-01")
for lb in (7, 14, 28):
    mom = LASTPX / LASTPX.shift(lb) - 1
    for k in (3, 5):
        for fl, fs in F.items():
            W = pd.DataFrame(0.0, index=dn, columns=PX.columns); cur = None
            for t, d in enumerate(dn):
                if d < start_rot: continue
                if d.weekday() == 6 or cur is None:                          # rebalance on Sundays
                    if not fs.iloc[t]: cur = np.zeros(len(PX.columns))
                    else:
                        m = mom.iloc[t].where(U20.iloc[t]); top = m.dropna().sort_values(ascending=False).index[:k]
                        cur = np.zeros(len(PX.columns)); cur[[cidx[c] for c in top]] = 1.0 / k
                W.iloc[t] = cur
            for cost in (0.001, 0.005):
                nm = f"top {k} by last {lb} days, weekly | filter {fl} | cost {cost*100:.2f}%"
                RES["rotation"][nm] = summ(run_weights(W, cost), start_rot); pr(nm, RES["rotation"][nm])
for nm, Wf in (("equal-weight top 20 (reference)", None), ("BTC hold (reference)", "BTC")):
    W = pd.DataFrame(0.0, index=dn, columns=PX.columns)
    for t, d in enumerate(dn):
        if d < start_rot: continue
        if Wf: W.iloc[t, cidx["BTC"]] = 1.0
        else:
            u = U20.iloc[t]; n = int(u.sum())
            if n: W.iloc[t] = u.astype(float).values / n
    RES["rotation"][nm] = summ(run_weights(W, 0.001), start_rot); pr(nm, RES["rotation"][nm])
# ---------------- 3) crypto dip bot (event loop)
def dip_bot(th=0.15, mh=5, idle="cash", ma=100, cost=0.005, slots=5):
    rel = (LASTPX / LASTPX.shift(5) - 1).sub(btc / btc.shift(5) - 1, axis=0); above = LASTPX > LASTPX.rolling(ma).mean(); m5 = LASTPX.rolling(5).mean()
    SIG = (rel <= -th) & above & U20 & PX.notna(); btc200 = btc > btc.rolling(200).mean()
    Pv = LASTPX.values; Rv = R.values; e = 1.0; eq = np.ones(D); pos = []; wbtc = 0.0; trades = []
    for t in range(1, D):
        r = sum(p_["w"] * Rv[t, p_["j"]] for p_ in pos) + wbtc * Rv[t, cidx["BTC"]]
        idle_w = 1 - sum(p_["w"] for p_ in pos) - wbtc; r += idle_w * cash_r[t]; e *= 1 + r
        for p_ in pos: p_["w"] *= (1 + Rv[t, p_["j"]]) / (1 + r)
        wbtc *= (1 + Rv[t, cidx["BTC"]]) / (1 + r)
        if dn[t] >= start_rot:
            keep = []
            for p_ in pos:                                                     # exits decided at yesterday's close, traded at today's close
                j = p_["j"]; age = t - p_["d"]
                if age >= 1 and (Pv[t - 1, j] > m5.values[t - 1, j] or age > mh or not np.isfinite(PX.values[t, j])):
                    e *= 1 - cost * p_["w"]; trades.append(Pv[t, j] / p_["px"] - 1 - 2 * cost)
                else: keep.append(p_)
            pos = keep
            cands = [cidx[c] for c in SIG.columns[SIG.values[t - 1]]] if t >= 1 else []
            cands.sort(key=lambda j: rel.values[t - 1, j])
            held = {p_["j"] for p_ in pos}
            want_btc = idle == "btc" and btc200.iloc[t - 1]
            for j in cands:
                if len(pos) >= slots or j in held: continue
                free = 1 - sum(p_["w"] for p_ in pos)
                if free < 0.05: break
                if wbtc > 0 and free - wbtc < 1.0 / slots:                      # sell some parked BTC to fund it
                    cut = min(wbtc, 1.0 / slots); wbtc -= cut; e *= 1 - cost * cut
                w = min(1.0 / slots, 1 - sum(p_["w"] for p_ in pos) - wbtc)
                if w < 0.05: break
                pos.append({"j": j, "d": t, "w": w, "px": Pv[t, j]}); e *= 1 - cost * w
            spare = 1 - sum(p_["w"] for p_ in pos)
            tgt_b = spare if want_btc else 0.0
            if abs(tgt_b - wbtc) > 0.02: e *= 1 - cost * abs(tgt_b - wbtc); wbtc = tgt_b
        eq[t] = e
    tr = np.array(trades) if trades else np.array([0.0])
    return eq, {"trades": len(trades), "win_pct": round(float((tr > 0).mean()) * 100, 1), "avg_trade_pct": round(float(tr.mean()) * 100, 2)}
for th in (0.15, 0.20):
    for mh in (5, 10):
        for idle in ("cash", "btc"):
            for cost in (0.001, 0.005, 0.0095):
                if cost != 0.005 and not (th == 0.15 and mh == 5): continue
                eq, st = dip_bot(th, mh, idle, cost=cost); nm = f"dip {int(th*100)}% vs BTC, hold <= {mh}d, idle {idle} | cost {cost*100:.2f}%"
                RES["dip"][nm] = summ(eq, start_rot) | st; pr(nm, RES["dip"][nm])
# ---------------- 4) analogue pattern matching (walk-forward)
def analog(coin, L=20, K=25, H=5, cost=0.005, start="2018-01-01"):
    r = np.log(LASTPX[coin]).diff().fillna(0).values; first = int(np.argmax(PX[coin].notna().values)); s0 = int(np.searchsorted(dn, pd.Timestamp(start)))
    sig = np.zeros(D); hold_until = -1; hits = []
    for t in range(max(s0, first + 400), D):
        if t <= hold_until: sig[t] = 1.0; continue
        x = r[t - L + 1:t + 1]; x = (x - x.mean()) / (x.std() + 1e-12)
        ends = np.arange(first + L, t - H - 30)                               # windows that ended (with their 5-day future) before today
        if len(ends) < 200: continue
        idx = ends[:, None] - np.arange(L - 1, -1, -1)[None, :]
        Wm = r[idx]; Wm = (Wm - Wm.mean(1, keepdims=True)) / (Wm.std(1, keepdims=True) + 1e-12)
        dist = ((Wm - x) ** 2).sum(1); nn = ends[np.argsort(dist)[:K]]
        fut = np.array([r[e + 1:e + 1 + H].sum() for e in nn]).mean()
        if fut > 0: sig[t] = 1.0; hold_until = t + H - 1
        hits.append((fut > 0, r[t + 1:t + 1 + H].sum() if t + H < D else np.nan))
    W = pd.DataFrame(0.0, index=dn, columns=PX.columns); W[coin] = sig
    h = np.array([x for x in hits if np.isfinite(x[1])]); acc = float(((h[:, 0] > 0) == (h[:, 1] > 0)).mean()) if len(h) else None
    return run_weights(W, cost), acc, float(sig.mean())
for coin in ("BTC", "ETH"):
    for cost in (0.001, 0.005):
        eq, acc, inv = analog(coin, cost=cost); nm = f"{coin} analogues (20-day shape, 25 nearest, hold 5 days) | cost {cost*100:.2f}%"
        RES["patterns"][nm] = summ(eq, pd.Timestamp("2018-01-01")) | {"direction_hit_rate_pct": round(acc * 100, 1) if acc else None, "time_invested_pct": round(inv * 100, 1)}; pr(nm, RES["patterns"][nm])
    W = pd.DataFrame(0.0, index=dn, columns=PX.columns); W[coin] = (dn >= pd.Timestamp("2018-01-01")).astype(float)
    RES["patterns"][f"{coin} hold from 2018 (reference)"] = summ(run_weights(W, 0.001), pd.Timestamp("2018-01-01"))
# ---------------- 5) calendar
for coin in ("BTC", "ETH"):
    rr = R[coin][PX[coin].notna()]; out = {}
    for half, a, b in (("2015-2020", "2015", "2021"), ("2021-2026", "2021", "2100")):
        x = rr[(rr.index >= a) & (rr.index < b)]
        out[half] = {d: round(float(x[x.index.weekday == i].mean()) * 100, 3) for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])}
    RES["calendar"][f"{coin} average daily return by weekday, %"] = out; print(coin, out, flush=True)
    for nm, mask in (("weekend only (Sat+Sun)", dn.weekday >= 5), ("weekdays only", dn.weekday < 5),
                     ("turn of month (last 2 + first 3 days)", (dn.day <= 3) | (dn.day >= dn.days_in_month - 1))):
        W = pd.DataFrame(0.0, index=dn, columns=PX.columns)
        held = pd.Series(mask, index=dn).shift(-2, fill_value=False)             # weights decided at t are traded at t+1's close and earn day t+2's return
        W[coin] = held.astype(float).values * (dn >= P[coin].index[0] + pd.Timedelta(days=30))
        for cost in (0.001, 0.005):
            k = f"{coin} | {nm} | cost {cost*100:.2f}%"; RES["calendar"][k] = summ(run_weights(W, cost)); pr(k, RES["calendar"][k])
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
