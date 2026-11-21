"""VIX / volatility gate for the US dip bot (Nov 21 2026, research idea #1). Research only, not financial advice.
Engine: scripts/stack_and_rebound.py, Dip bot v3.0 (stocks + ETF dips + IEF/Clear Leader parking), 1999-2026, live-like and realistic fills.
Gate: only take NEW stock dips when fear is high. Measures: VIX (Yahoo ^VIX, previous close), or SPY's own 20-day realized volatility
(computable from Robinhood prices alone). Versions: above 15/20/25/30; 'high but calming' = above the level AND below its 5-day high.
Thresholds judged on 1999-2012 vs 2013-2026 and on the dead period 2013-2019. Money not used for dips stays in the normal parking.
DRY=1: fake ETF data."""
import os, sys, json, time, urllib.request
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/vix_gate.json" if not S.DRY else "/tmp/vix_gate_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True)
dn, t0, D = S.dn, S.t0, S.D
def cagr(cv, a="1999-01-01", b="2100-01-01"):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0)); c = cv[ix] / cv[max(ix[0] - 1, t0)]
    return round((c[-1] ** (252 / len(ix)) - 1) * 100, 1)
def worst(cv): c = cv[t0:]; return round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1)
def summ(cv, tr): return {"1999-2026": cagr(cv), "1999-2012": cagr(cv, "1999", "2013"), "2013-2026": cagr(cv, "2013"), "2013-2019": cagr(cv, "2013", "2020"), "2020-2026": cagr(cv, "2020"), "worst": worst(cv), "trades_per_month": round(len(tr) / ((D - t0) / 21), 1)}
if S.DRY: vix = pd.Series(np.clip(15 + np.cumsum(np.random.default_rng(1).normal(0, 1, D)) % 30, 9, 80), index=S.dates)
else:
    b = urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?period1=852076800&period2={int(time.time())}&interval=1d", headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    j = json.loads(b)["chart"]["result"][0]; vix = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna()
    vix = vix[~vix.index.duplicated(keep="last")]
vix = vix.reindex(S.dates).ffill().shift(1)                     # yesterday's close: known before the 3:45 decision
rv = pd.Series(S.spyr, index=S.dates).rolling(20).std() * np.sqrt(252) * 100
rv = rv.shift(1)
G = {}
for lv in (15, 20, 25, 30):
    G[f"VIX >= {lv}"] = (vix >= lv).values
    G[f"VIX >= {lv} and below its 5-day high (calming)"] = ((vix >= lv) & (vix < vix.rolling(5).max())).values
for lv in (12, 16, 20, 25):
    G[f"SPY 20-day vol >= {lv}%"] = (rv >= lv).values
print("share of days open:", {k: round(float(np.nanmean(v)) * 100) for k, v in G.items()}, flush=True)
RES = {}
for cn, cost in (("live-like", LIVE), ("realistic", REAL)):
    RES[f"{cn} | v3.0 (no gate)"] = summ(*S.sim(**V3, **cost))
    for k, g in G.items(): RES[f"{cn} | {k}"] = summ(*S.sim(**V3, **cost, sig=S.SIG & g[:, None]))
    for k in [k for k in RES if k.startswith(cn)]:
        r = RES[k]; print(f"GATE {k:62s} {r['1999-2026']}% | 99-12 {r['1999-2012']} 13-26 {r['2013-2026']} | 13-19 {r['2013-2019']} 20-26 {r['2020-2026']} | worst {r['worst']} | {r['trades_per_month']}/mo", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, "results": RES}, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
