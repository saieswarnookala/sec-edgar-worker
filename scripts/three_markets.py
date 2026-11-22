"""Three non-stock-picking ideas (Nov 22 2026). Research only, not financial or tax advice.
A) LEVERAGE WITH A TREND FILTER (Sai's Roth): hold 1x/2x/3x the S&P 500 while it is above its 200-day average, else T-bills
   ("Leverage for the long run", Gayed & Bilello 2016). Simulated daily: L x index return - (L-1) x (T-bill + 0.5%) borrowing - fund fee
   (1x 0.09%, 2x 0.89%, 3x 0.91%/yr), 0.05% per switch, signal at the close, trade the NEXT close. Tests: 1960-2026 on ^GSPC price index
   (no dividends for anyone, so ~2-3 pts/yr low but fair between rows) and 1994-2026 on SPY total return; checked against the real SSO ETF (2006+).
   Variants: 200-day daily, 200-day with a 2% band, 10-month (monthly). No tax (Roth).
B) WHEN TO SEND USD -> INR (Sai): $1,000 saved each month. Baseline: convert on the 1st trading day of each month. Rules wait in T-bills
   (^IRX) and convert when the dollar is strong (USD/INR above its 50-day average, or at a 60-day high), but never wait more than 3 months.
   Rupees then earn 6.5%/yr (bank FD) until the end, so waiting has a real cost. Metric: rupees at the end vs baseline. 2004-2026, INR=X.
C) NIFTY vs GOLD (friends in India): Nifty 50 (^NSEI + 1.3%/yr dividends) and gold (GOLDBEES.NS, in rupees). Monthly checks:
   ratio rule = Nifty/gold vs its 5-year average (z-score): expensive (z > +1) -> 30% Nifty / 70% gold, cheap (z < -1) -> 100% Nifty, else 60/40;
   gold 10-month trend (gold or liquid 6%); fixed mixes. Costs 0.1% per switch. After tax rough: switching rules 20.8% on each year's net gain;
   buy & hold 13% once at the end.
DRY=1: fake data (code test)."""
import os, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/three_markets.json" if not DRY else "/tmp/three_markets_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym, p1=-1325635200):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.bdate_range("1955-01-03" if sym in ("^GSPC", "^IRX") else "2003-12-01", "2026-11-20")
        if sym == "^IRX": return pd.Series(4.0, index=ix)
        mu, v = {"INR=X": (0.00012, 0.004), "GOLDBEES.NS": (0.0004, 0.009)}.get(sym, (0.0003, 0.01))
        s = pd.Series(100 * np.exp(np.cumsum(rng.normal(mu, v, len(ix)))), index=ix)
        return s[s.index >= {"SPY": "1994-01-03", "SSO": "2006-06-21", "^NSEI": "2007-09-17", "GOLDBEES.NS": "2007-03-19"}.get(sym, "1900-01-01")]
    for a in range(4):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1={p1}&period2={int(time.time())}&interval=1d&events=div%2Csplit", headers=UA), timeout=60).read())["chart"]["result"][0]
            q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); s = s[~s.index.duplicated(keep="last")]
            return s[s > 0]
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data for " + sym)
SYM = ["^GSPC", "^IRX", "SPY", "SSO", "INR=X", "^NSEI", "GOLDBEES.NS"]
X = {s: yahoo(s) for s in SYM}
for s, v in X.items(): print(f"{s:12s} {v.index[0].date()} .. {v.index[-1].date()} ({len(v)})", flush=True)
def st(c, a=None, b=None):
    c = c.dropna(); c = c[(c.index >= (a or c.index[0])) & (c.index < (b or "2100-01-01"))]
    if len(c) < 120: return None
    y = (c.index[-1] - c.index[0]).days / 365.25; c = c / c.iloc[0]
    o = {"total_pct": round(float(c.iloc[-1] - 1) * 100, 1), "worst_drop_pct": round(float((c / c.cummax() - 1).min()) * 100, 1)}
    if y > 1.5: o["per_year_pct"] = round(float(c.iloc[-1] ** (1 / y) - 1) * 100, 1)
    return o
RES = {"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "A_leverage": {}, "B_usd_inr": {}, "C_nifty_gold": {}}
# ---------------------------------------------------------------- A) leverage with a trend filter
irx = X["^IRX"]
def lev_test(px, label, start):
    px = px[px.index >= pd.Timestamp(start) - pd.Timedelta(days=420)]; ix = px.index
    tb = (irx.reindex(ix).ffill().bfill().clip(0, 20) / 100); tbd = (1 + tb) ** (1 / 252) - 1
    r = px.pct_change().fillna(0)
    sma = px.rolling(200).mean(); me = px.resample("ME").last(); m10 = me.rolling(10).mean()
    sig = {"200-day": (px > sma),
           "200-day with 2% band": None,
           "10-month (checked monthly)": (me > m10).reindex(ix, method="ffill").fillna(False)}
    b = np.zeros(len(ix), bool); on = False; pv, sv = px.values, sma.values
    for i in range(len(ix)):
        if np.isfinite(sv[i]): on = pv[i] > sv[i] * 1.02 if not on else not (pv[i] < sv[i] * 0.98)
        b[i] = on
    sig["200-day with 2% band"] = pd.Series(b, index=ix)
    out = {}
    def curve(L, s_):
        fee = {1: 0.0009, 2: 0.0089, 3: 0.0091}[L] / 252
        lr = L * r - (L - 1) * (tbd + 0.005 / 252) - fee
        if s_ is None: d = lr
        else:
            h = s_.astype(float).shift(1).fillna(0)                    # signal at close t -> held from t+1 (trade at that close)
            d = h * lr + (1 - h) * tbd - h.diff().abs().fillna(0) * 0.0005
        c = (1 + d[ix >= pd.Timestamp(start)]).cumprod(); return c, (s_.astype(int).diff().abs().sum() / ((ix[-1] - ix[0]).days / 365.25) if s_ is not None else 0)
    rows = [(f"{L}x buy & hold", L, None) for L in (1, 2, 3)] + [(f"{L}x with {k}", L, k) for k in sig for L in (1, 2, 3)]
    for nm, L, k in rows:
        c, sw = curve(L, sig[k] if k else None)
        o = {"all": st(c), "1960-1979": st(c, "1960-01-01", "1980-01-01"), "1980-1999": st(c, "1980-01-01", "2000-01-01"), "2000-2012": st(c, "2000-01-01", "2013-01-01"),
             "2013-2026": st(c, "2013-01-01"), "2008": st(c, "2008-01-01", "2009-01-01"), "2020": st(c, "2020-01-01", "2021-01-01"), "2022": st(c, "2022-01-01", "2023-01-01"),
             "switches_per_year": round(float(sw), 1)}
        w12 = (c.resample("ME").last().pct_change(12)).min(); o["worst_12m_pct"] = round(float(w12) * 100, 1) if np.isfinite(w12) else None
        out[nm] = o; a = o["all"]
        print(f"LEV {label:28s} {nm:34s} {a.get('per_year_pct')}%/yr worst {a['worst_drop_pct']}% w12m {o['worst_12m_pct']} | 2008 {o['2008']['total_pct'] if o['2008'] else None} 2020 {o['2020']['total_pct'] if o['2020'] else None} 2022 {o['2022']['total_pct'] if o['2022'] else None} | sw {o['switches_per_year']}", flush=True)
    return out
RES["A_leverage"]["S&P 500 price index, 1960-2026 (no dividends)"] = lev_test(X["^GSPC"], "^GSPC 1960-2026", "1960-01-04")
RES["A_leverage"]["SPY total return, 1994-2026"] = lev_test(X["SPY"], "SPY 1994-2026", "1994-01-03")
# simulation check vs the real 2x ETF (SSO), buy & hold, same days
s0 = X["SSO"].index[0] + pd.Timedelta(days=5); spy = X["SPY"][X["SPY"].index >= s0]; ix = spy.index
tbd = (1 + irx.reindex(ix).ffill().bfill() / 100) ** (1 / 252) - 1
sim = (1 + 2 * spy.pct_change().fillna(0) - (tbd + 0.005 / 252) - 0.0089 / 252).cumprod()
RES["A_leverage"]["check: simulated 2x vs real SSO (buy & hold)"] = {"simulated": st(sim), "real_SSO": st(X["SSO"][X["SSO"].index >= s0])}
print("CHECK sim vs SSO", RES["A_leverage"]["check: simulated 2x vs real SSO (buy & hold)"], flush=True)
# ---------------------------------------------------------------- B) USD -> INR timing
fx = X["INR=X"][X["INR=X"].index >= "2004-01-01"]; ix = fx.index
tbd = ((1 + irx.reindex(ix).ffill().bfill().clip(0, 20) / 100) ** (1 / 252) - 1).values; fdd = (1.065) ** (1 / 252) - 1
first = np.r_[True, ix.month[1:] != ix.month[:-1]]
ma50 = fx.rolling(50).mean().values; hi60 = fx.rolling(60).max().values; f = fx.values
def remit(rule):
    usd = 0.0; inr = 0.0; waited = 0; conv = []
    for i in range(len(ix)):
        usd *= 1 + tbd[i]; inr *= 1 + fdd
        if first[i]: usd += 1000.0; waited += 1
        go = False
        if rule == "1st of every month": go = first[i]
        elif rule == "every 3 months (1st of Jan/Apr/Jul/Oct)": go = first[i] and ix[i].month in (1, 4, 7, 10)
        elif rule == "dollar above its 50-day average (max wait 3 months)": go = (np.isfinite(ma50[i]) and f[i] > ma50[i]) or waited >= 3
        elif rule == "dollar at a 60-day high (max wait 3 months)": go = (np.isfinite(hi60[i]) and f[i] >= hi60[i]) or waited >= 3
        if go and usd > 0: inr += usd * f[i] * (1 - 0.0025); conv.append(f[i]); usd = 0.0; waited = 0      # 0.25% transfer spread
    inr += usd * f[-1] * (1 - 0.0025)
    return inr, float(np.mean(conv)) if conv else None, len(conv)
base, _, _ = remit("1st of every month")
for rule in ("1st of every month", "every 3 months (1st of Jan/Apr/Jul/Oct)", "dollar above its 50-day average (max wait 3 months)", "dollar at a 60-day high (max wait 3 months)"):
    v, avg_rate, n_ = remit(rule)
    RES["B_usd_inr"][rule] = {"rupees_at_end_lakh": round(v / 1e5, 2), "vs_monthly_pct": round((v / base - 1) * 100, 2), "avg_rate_when_converting": round(avg_rate, 2) if avg_rate else None, "transfers": n_}
    print(f"FX {rule:52s} Rs {v/1e5:8.2f} lakh  vs monthly {(v/base-1)*100:+.2f}%  avg rate {avg_rate:.2f}  transfers {n_}", flush=True)
RES["B_usd_inr"]["note_rupee_trend"] = f"USD/INR {f[0]:.1f} -> {f[-1]:.1f} ({((f[-1]/f[0])**(1/((ix[-1]-ix[0]).days/365.25))-1)*100:.1f}%/yr rupee weakening)"
# ---------------------------------------------------------------- C) Nifty vs gold
nf = X["^NSEI"]; gd = X["GOLDBEES.NS"]; ix = nf.index.intersection(gd.index); ix = ix[ix >= "2008-01-01"]
nr = nf.reindex(ix).pct_change().fillna(0) + (1.013 ** (1 / 248) - 1); grr = gd.reindex(ix).pct_change().fillna(0).clip(-0.15, 0.15)
liq = (1.06) ** (1 / 248) - 1
lvl_n = (1 + nr).cumprod(); lvl_g = (1 + grr).cumprod(); ratio = np.log(lvl_n / lvl_g); z = (ratio - ratio.rolling(1240, min_periods=750).mean()) / ratio.rolling(1240, min_periods=750).std()
gme = lvl_g.resample("ME").last(); gtr = (gme > gme.rolling(10).mean())
mend = set(lvl_n.resample("ME").last().index)
def mix(rule, tax="switch"):
    wN = 1.0 if rule != "100% gold" else 0.0; eq = 1.0; out = []; prev_w = None
    for i, d in enumerate(ix):
        if prev_w is not None:
            gpart = grr.iloc[i] if rule != "70% Nifty + 30% gold with 10-month trend (else liquid)" or gold_on else liq
            eq *= 1 + wN * nr.iloc[i] + (1 - wN) * gpart
        out.append(eq)
        is_me = (i + 1 < len(ix) and ix[i + 1].month != d.month)
        if prev_w is None or is_me:
            new = wN
            if rule == "100% Nifty": new = 1.0
            elif rule == "100% gold": new = 0.0
            elif rule.startswith("fixed 70/30"): new = 0.7
            elif rule.startswith("fixed 50/50"): new = 0.5
            elif rule.startswith("ratio rule"):
                zz = z.iloc[i]; new = 0.6 if not np.isfinite(zz) else (0.3 if zz > 1 else (1.0 if zz < -1 else 0.6))
            elif rule.startswith("70% Nifty + 30% gold with 10-month"):
                new = 0.7; m = d + pd.offsets.MonthEnd(0); gold_on = bool(gtr.asof(m)) if len(gtr.loc[:m]) else False
            if prev_w is not None and abs(new - wN) > 1e-9: eq *= 1 - 0.001 * abs(new - wN) * 2
            wN = new; prev_w = new
    c = pd.Series(out, index=ix); return c
gold_on = False
def after_tax(c, hold):
    y = (c.index[-1] - c.index[0]).days / 365.25; m = c.iloc[-1] / c.iloc[0]
    if hold: return round(((1 + (m - 1) * 0.87) ** (1 / y) - 1) * 100, 1)
    ye = c.groupby(c.index.year).last(); prev = c.iloc[0]; eq = 1.0; carry = 0.0
    for v in ye.values:
        g = v / prev - 1; prev = v
        if g > 0: tg = max(0.0, g - carry); carry = max(0.0, carry - g); eq *= 1 + g - tg * 0.208
        else: carry += -g; eq *= 1 + g
    return round((eq ** (1 / y) - 1) * 100, 1)
for rule, hold in (("100% Nifty", True), ("100% gold", True), ("fixed 70/30 Nifty/gold (rebalanced monthly)", False), ("fixed 50/50 Nifty/gold (rebalanced monthly)", False),
                   ("ratio rule: 30/70 when Nifty is expensive vs gold, 100% Nifty when cheap, else 60/40", False),
                   ("70% Nifty + 30% gold with 10-month trend (else liquid)", False)):
    c = mix(rule); o = {"all": st(c), "after_tax_rough_pct": after_tax(c, hold), "2008-2013": st(c, "2008-01-01", "2014-01-01"), "2014-2019": st(c, "2014-01-01", "2020-01-01"),
                        "2020-2026": st(c, "2020-01-01"), "2008": st(c, "2008-01-01", "2009-01-01"), "2020": st(c, "2020-01-01", "2021-01-01")}
    RES["C_nifty_gold"][rule] = o; a = o["all"]
    print(f"NG {rule:90s} {a.get('per_year_pct')}%/yr after~{o['after_tax_rough_pct']} worst {a['worst_drop_pct']}% | 08-13 {o['2008-2013']} 14-19 {(o['2014-2019'] or {}).get('per_year_pct')} 20-26 {(o['2020-2026'] or {}).get('per_year_pct')}", flush=True)
RES["C_nifty_gold"]["ratio_now"] = {"z_score_latest": round(float(z.dropna().iloc[-1]), 2) if z.notna().any() else None,
                                    "monthly_correlation_nifty_gold": round(float(nr.resample("ME").apply(lambda x: (1 + x).prod() - 1).corr(grr.resample("ME").apply(lambda x: (1 + x).prod() - 1))), 2)}
print("RATIO NOW", RES["C_nifty_gold"]["ratio_now"], flush=True)
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
