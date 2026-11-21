"""Slow crypto trend rules (Nov 20 2026). Research only, not financial advice.
Data: Yahoo daily BTC-USD (from Sep 2014) and ETH-USD (from Nov 2017), SPY, ^IRX (T-bills for idle money).
Rules (signal on the close, trade the NEXT day's close, so no look-ahead):
  buy & hold | 10-month average, checked at month end (Faber) | 200-day average, daily | 20-week average, checked Fridays |
  50/200-day crossover
Costs: 'ETF route' = spot bitcoin/ether ETF (IBIT/ETHA-style): 0.10% per trade + 0.25%/yr fee.
       'Robinhood Crypto route' = 0.95% per side (Robinhood's published spread markup), no fee.
Also: a 10% Bitcoin slice next to SPY (buy & hold vs the 10-month rule), rebalanced monthly.
Periods: whole history, 2015-2019, 2020-2026, 2022 (crypto winter). Crypto trades every day; monthly/weekly checks use calendar month ends / Fridays.
DRY=1: fake prices (code test)."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/crypto_trend.json" if not DRY else "/tmp/crypto_trend_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.date_range("2014-09-17", "2026-11-19")
        vol, mu = (0.04, 0.0015) if "USD" in sym else (0.011, 0.0004)
        if sym == "^IRX": return pd.Series(2.0, index=ix)
        return pd.Series(100 * np.exp(np.cumsum(rng.normal(mu, vol, len(ix)))), index=ix)
    for a in range(4):
        try:
            b = urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1400000000&period2={int(time.time())}&interval=1d&events=div%2Csplit", headers=UA), timeout=60).read()
            j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]
            adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); s = s[~s.index.duplicated(keep="last")]
            return s[s > 0]
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data for " + sym)
BTC, ETH, SPY, IRX = yahoo("BTC-USD"), yahoo("ETH-USD"), yahoo("SPY"), yahoo("^IRX")
cal = BTC.index                                                     # every calendar day (crypto trades 7 days)
irx = IRX.reindex(cal).ffill().bfill().clip(0, 8) / 100
cash_r = (1 + irx) ** (1 / 365) - 1
print("BTC from", BTC.index[0].date(), "ETH from", ETH.index[0].date(), "| last", BTC.index[-1].date(), flush=True)
def signal(p, rule):
    """1 = hold, decided on day t's close, held from day t+1"""
    if rule == "hold": return pd.Series(1.0, index=p.index)
    if rule == "200d": return (p > p.rolling(200).mean()).astype(float)
    if rule == "50/200": return (p.rolling(50).mean() > p.rolling(200).mean()).astype(float)
    if rule == "10m":
        me = p.resample("ME").last(); on = (me > me.rolling(10).mean()).astype(float)
        s = pd.Series(np.nan, index=p.index); s.loc[s.index.isin(me.index)] = on.reindex(s.index[s.index.isin(me.index)]).values
        return s.ffill().fillna(0)
    if rule == "20w":
        wk = p[p.index.dayofweek == 4]; on = (wk > wk.rolling(20).mean()).astype(float)
        s = pd.Series(np.nan, index=p.index); s.loc[wk.index] = on.values; return s.ffill().fillna(0)
def run(p, rule, cost, fee):
    p = p.dropna(); r = p.pct_change().fillna(0); sig = signal(p, rule).shift(1).fillna(0)   # act the day after the signal
    cr = cash_r.reindex(p.index).fillna(0)
    sw = sig.diff().abs().fillna(sig.iloc[0])
    daily = sig * (r - fee / 365) + (1 - sig) * cr - sw * cost
    cv = (1 + daily).cumprod(); return cv, int(sw.sum()), float(sig.mean())
def stats(cv, a=None, b=None):
    c = cv[(cv.index >= (a or cv.index[0])) & (cv.index < (b or "2100-01-01"))]
    if len(c) < 60: return None
    yrs = (c.index[-1] - c.index[0]).days / 365.25; c = c / c.iloc[0]
    return {"per_year_pct": round((c.iloc[-1] ** (1 / yrs) - 1) * 100, 1) if yrs > 1.5 else None, "total_pct": round((c.iloc[-1] - 1) * 100, 1), "worst_drop_pct": round(float((c / c.cummax() - 1).min()) * 100, 1)}
RES = {}
for coin, p in (("Bitcoin", BTC), ("Ether", ETH)):
    for route, cost, fee in (("ETF route", 0.001, 0.0025), ("Robinhood Crypto route", 0.0095, 0.0)):
        for rule, lab in (("hold", "buy & hold"), ("10m", "10-month average, monthly"), ("200d", "200-day average, daily"), ("20w", "20-week average, weekly"), ("50/200", "50/200-day crossover")):
            cv, n, inv = run(p, rule, cost, fee); yrs = (p.index[-1] - p.index[0]).days / 365.25
            k = f"{coin} | {route} | {lab}"
            RES[k] = {"all": stats(cv), "2015-2019": stats(cv, "2015-01-01", "2020-01-01"), "2020-2026": stats(cv, "2020-01-01"), "2022": stats(cv, "2022-01-01", "2023-01-01"),
                      "trades_per_year": round(n / yrs, 1), "time_invested_pct": round(inv * 100)}
            g = RES[k]; f = lambda x: None if x is None else (x["per_year_pct"] if x["per_year_pct"] is not None else f"{x['total_pct']} total")
            print(f"{k:62s} {f(g['all'])}%/yr worst {g['all']['worst_drop_pct']}% | 15-19 {f(g['2015-2019'])} 20-26 {f(g['2020-2026'])} 2022 {g['2022']['total_pct'] if g['2022'] else None}% | {g['trades_per_year']}/yr, in {g['time_invested_pct']}%", flush=True)
# 10% bitcoin next to SPY (monthly rebalance), from 2015
spy = SPY.reindex(cal).ffill(); m_spy = spy.resample("ME").last().pct_change()
for lab, rule in (("10% bitcoin buy & hold", "hold"), ("10% bitcoin with the 10-month rule", "10m")):
    cv, _, _ = run(BTC, rule, 0.001, 0.0025); m_b = cv.resample("ME").last().pct_change()
    for w in (0.05, 0.10):
        r = ((1 - w) * m_spy + w * m_b).loc["2015-01-01":].dropna(); c = (1 + r).cumprod()
        k = f"{100 - int(w * 100)}% SPY + {lab.replace('10%', str(int(w * 100)) + '%')}"
        RES[k] = {"per_year_pct": round((c.iloc[-1] ** (12 / len(r)) - 1) * 100, 1), "worst_monthly_drop_pct": round(float((c / c.cummax() - 1).min()) * 100, 1)}
        print(f"MIX {k:58s} {RES[k]['per_year_pct']}%/yr worst {RES[k]['worst_monthly_drop_pct']}%", flush=True)
r = m_spy.loc["2015-01-01":].dropna(); c = (1 + r).cumprod()
RES["100% SPY (2015-2026)"] = {"per_year_pct": round((c.iloc[-1] ** (12 / len(r)) - 1) * 100, 1), "worst_monthly_drop_pct": round(float((c / c.cummax() - 1).min()) * 100, 1)}
print("MIX 100% SPY", RES["100% SPY (2015-2026)"], flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
