# Buy-the-dip strategy on Indian stocks (NSE), 2008-2026. Research only.
# Universe: approx point-in-time top-100 / top-200 NSE stocks by 120-session median traded value, re-picked every 6 months,
# from today's Nifty 500 + former large caps (stocks that vanished from Yahoo are missing -> some survivorship bias).
# Rule (same as US): above 200-day avg, fell >=10% vs Nifty 50 over 5 sessions, buy biggest dips first, 10 slots x 10%,
# smart exit (close > 5-day avg, max 5 sessions). Optional: skip if 5-day volume > 2x its normal 50-day volume.
# Idle money: cash (0%), liquid fund (~6%/yr), or Nifty while Nifty > its 100-day avg else liquid fund.
import os, sys, json, time, traceback, urllib.request, urllib.parse, io
import numpy as np, pandas as pd
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
FORMER = ['HDFC', 'MINDTREE', 'LTI', 'IBULHSGFIN', 'DHFL', 'ZEEL', 'IDEA', 'YESBANK', 'CADILAHC', 'MCDOWELL-N', 'GRUH', 'BHARTIINFRA', 'PEL', 'AUROPHARMA', 'GLENMARK', 'RCOM', 'RELINFRA', 'RPOWER', 'JETAIRWAYS', 'SRTRANSFIN', 'L&TFH', 'NIACL', 'GICRE', 'BANKBARODA', 'IDBI', 'PNB', 'CANBK', 'MOTHERSUMI', 'AMARAJABAT', 'TATAMTRDVR', 'ADANITRANS', 'ADANIGAS', 'INFRATEL', 'HDFCAMC', 'VEDL', 'NMDC', 'SAIL', 'BHEL', 'OFSS', 'MRF', 'PAGEIND', 'BOSCHLTD', 'CONCOR', 'PETRONET', 'IGL', 'GAIL', 'ACC', 'AMBUJACEM', 'LUPIN', 'BIOCON', 'COLPAL', 'MARICO', 'DABUR', 'GODREJCP', 'HAVELLS', 'BERGEPAINT', 'PIDILITIND', 'SIEMENS', 'ABB', 'INDIGO', 'NAUKRI', 'UBL', 'TORNTPHARM', 'ICICIPRULI', 'ICICIGI', 'BANDHANBNK', 'PGHH', 'DLF', 'MUTHOOTFIN', 'COFORGE', 'PERSISTENT', 'TATAPOWER', 'TATACHEM', 'CHOLAFIN', 'APOLLOHOSP']
LIQUID = 0.06
def get(url, tries=5):
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("fail", url[:100], err); return None
def yahoo(sym):
    b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=1104537600&period2={int(time.time())}&interval=1d&events=div%2Csplit")
    if not b: return None
    try:
        j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]["quote"][0]
        adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
        df = pd.DataFrame({"c": adj, "rc": q["close"], "o": q["open"], "v": q["volume"]}, index=pd.to_datetime(j["timestamp"], unit="s").normalize())
        df = df[~df.index.duplicated(keep="last")].dropna(subset=["c", "rc"]); df = df[(df.c > 0) & (df.rc > 0)]
        df["o"] = df.o * df.c / df.rc   # adjust open like close
        return df
    except Exception as e: print("parse", sym, e); return None
def universe():
    syms = []
    for u in ["https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv", "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"]:
        b = get(u)
        if b:
            try: syms = list(pd.read_csv(io.BytesIO(b)).Symbol.dropna().astype(str)); break
            except Exception as e: print("csv", e)
    if not syms: raise RuntimeError("could not load Nifty 500 list")
    return sorted(set(syms) | set(FORMER))
def run():
    MODE = sys.argv[1] if len(sys.argv) > 1 else "dip"
    syms = universe(); print(len(syms), "symbols", flush=True)
    nifty = yahoo("^NSEI"); px = {}
    for i, s in enumerate(syms):
        d = yahoo(s + ".NS")
        if d is not None and len(d) > 250: px[s] = d
        if i % 50 == 0: print(i, len(px), flush=True)
        time.sleep(0.25)
    dates = nifty.index[nifty.index >= "2006-06-01"]
    C = pd.DataFrame({s: d.c for s, d in px.items()}).reindex(dates); O = pd.DataFrame({s: d.o for s, d in px.items()}).reindex(dates)
    RC = pd.DataFrame({s: d.rc for s, d in px.items()}).reindex(dates); V = pd.DataFrame({s: d.v for s, d in px.items()}).reindex(dates)
    valid = C.notna(); Cf = C.ffill(); tick = list(C.columns); n = nifty.c.reindex(dates).ffill()
    r1 = Cf.pct_change()
    glitch = (r1.abs() > 0.35).rolling(6, min_periods=1).max().astype(bool)          # skip windows with suspicious jumps
    tv = (RC * V).rolling(120, min_periods=60).median()
    D = len(dates); START = int(np.searchsorted(dates.values, np.datetime64("2008-01-01")))
    halves = [i for i in range(1, D) if dates[i].month in (1, 7) and dates[i - 1].month not in (1, 7)]
    def members(k):
        M = pd.DataFrame(False, index=dates, columns=tick); b = [0] + halves + [D]
        for a, z in zip(b[:-1], b[1:]):
            if a == 0: continue
            row = tv.iloc[a - 1].dropna().sort_values(ascending=False)
            M.iloc[a:z, M.columns.get_indexer(row.index[:k])] = True
        return M & valid & valid.shift(-1, fill_value=False) & (RC > 20)
    above = Cf > Cf.rolling(200).mean()
    rl = Cf.pct_change(5).sub(n.pct_change(5), axis=0)
    vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5))
    over5 = (Cf > Cf.rolling(5).mean()).values; Rt = r1.fillna(0).values; OC = (Cf / O - 1).fillna(0).values
    nr = n.pct_change().fillna(0).values; liq = np.full(D, (1 + LIQUID) ** (1 / 248) - 1)
    ntr = (n > n.rolling(100).mean()).shift(1, fill_value=False).values
    PARK = {"cash": np.zeros(D), "liquid fund ~6%": liq, "Nifty trend (100-day), else liquid": np.where(ntr, nr, liq), "Nifty always": nr}
    def sim(S, R, park, cost=0.0015, entry="close", mx=5, slots=10):
        eq = 1.0; curve = np.ones(D); pos = []; tr = []; inv = []
        for t in range(START, D):
            used = sum(p[2] for p in pos); day = 0.0
            for p in pos:
                g = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[3] *= 1 + g; day += p[2] * g
            day += max(0.0, 1 - used) * park[t]; inv.append(used); eq *= 1 + day; keep = []
            for p in pos:
                g = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[1] += 1; p[2] *= (1 + g) / (1 + day)
                if p[1] >= mx or over5[t, p[0]]: eq *= 1 - cost * p[2]; tr.append(p[3] - 1 - 2 * cost)
                else: keep.append(p)
            pos = keep; used = sum(p[2] for p in pos); held = {p[0] for p in pos}
            new = [c for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
            if new:
                w = min(1.0 / slots, max(0.0, 1 - used) / len(new))
                for c in new: pos.append([c, 0, w, 1.0]); eq *= 1 - cost * w
            curve[t] = eq
        return summarize(curve, tr, inv)
    def summarize(curve, tr=None, inv=None):
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0); yrs = len(p) / 248
        per = {}
        for a, b in [("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[a + "-" + b] = round(100 * ((1 + q).prod() ** (248 / max(len(q), 1)) - 1), 1)
        o = {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per}
        if inv is not None: o["invested_pct"] = round(100 * float(np.mean(inv)), 1)
        if tr: o["trades"] = len(tr); o["win_rate"] = round(100 * float((np.array(tr) > 0).mean()), 1); o["avg_trade_pct"] = round(100 * float(np.mean(tr)), 2)
        return o
    OUT = {"years": f"{dates[START].date()} to {dates[-1].date()}", "stocks_with_prices": len(px),
           "nifty50": summarize((1 + pd.Series(nr, index=dates)).cumprod().values / (1 + nr[:START + 1]).prod()),
           "note": "Nifty 50 price index (no dividends, ~1.2-1.5%/yr understated). Ideal = buy at close, 0.15%/side (STT, stamp, charges). Realistic = next open, 0.30%/side.", "results": []}
    if MODE == "trend":
        g = yahoo("GOLDBEES.NS"); gold = g.c.reindex(dates).ffill() if g is not None else None
        if gold is None or gold.notna().sum() < 1000:   # fallback: gold futures in USD x USDINR
            gu, fx = yahoo("GC=F"), yahoo("USDINR=X"); gold = (gu.c.reindex(dates).ffill() * fx.c.reindex(dates).ffill())
        gr = gold.pct_change().fillna(0).values
        OUT["gold_source"] = "GOLDBEES" if g is not None and g.c.reindex(dates).notna().sum() >= 1000 else "GC=F x USDINR"
        nm = n.copy(); me = nm.groupby(nm.index.to_period("M")).transform("last") == nm   # month-end closes
        def trend_sig(kind):
            if kind.endswith("m"):   # N-month average, checked at month ends only
                k = int(kind[:-1]); mc = nm[me]; ok = (mc > mc.rolling(k).mean()).reindex(dates).ffill().fillna(False)
            else: ok = nm > nm.rolling(int(kind)).mean()
            return ok.shift(1, fill_value=False).values.astype(bool)
        gtr = (gold > gold.rolling(100).mean()).shift(1, fill_value=False).values
        SW = 0.0005   # cost per switch (ETF, ~0.05%)
        def park_series(sig, below):
            alt = {"liquid": liq, "cash": np.zeros(D), "gold": gr, "gold if trending else liquid": np.where(gtr, gr, liq)}[below]
            r = np.where(sig, nr, alt).astype(float)
            sw = np.r_[False, sig[1:] != sig[:-1]]; r[sw] -= SW
            if below == "gold if trending else liquid":
                sw2 = np.r_[False, (gtr[1:] != gtr[:-1])] & ~sig; r[sw2] -= SW
            return r
        TR = {}
        for kind in ("50", "100", "150", "200", "10m"):
            for below in ("liquid", "cash", "gold", "gold if trending else liquid"):
                ps = park_series(trend_sig(kind), below); TR[(kind, below)] = ps
                r = summarize(np.cumprod(1 + ps) / np.prod(1 + ps[:START + 1])); r.update(avg=kind, below=below, scenario="parking only", switches_per_year=round(float(np.sum(np.r_[False, trend_sig(kind)[1:] != trend_sig(kind)[:-1]][START:]) / ((D - START) / 248)), 1))
                OUT["results"].append(r); print(kind, below, r["cagr"], r["dd"], r["switches_per_year"], r["per"], flush=True)
        # best dip version (top 200, 12% dip, skip volume > 2x) on top of each parking rule
        M = members(200).values; ab = above.values & M & ~glitch.values; R = (-rl).values; volok = ~(vr > 2.0).values
        for th in (0.10, 0.12):
            S = (rl.values <= -th) & ab & volok
            for (kind, below), ps in TR.items():
                if below not in ("liquid", "gold if trending else liquid"): continue
                for tag, kw in [("ideal", {}), ("realistic", dict(entry="open", cost=0.003))]:
                    r = sim(S, R, ps, **kw); r.update(avg=kind, below=below, scenario=tag, dip=f"{int(th*100)}% + volume<2x, top 200")
                    OUT["results"].append(r); print("dip", th, kind, below, tag, r["cagr"], r["dd"], flush=True)
        OUT["note"] += " Trend rule: hold Nifty while above its average (checked daily at the close, acted on next day; '10m' = 10-month average checked at month end); otherwise the 'below' choice. 0.05% per switch."
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_trend.json", "w"), indent=1, default=float); return
    for k in (100, 200):
        M = members(k).values; ab = above.values & M & ~glitch.values; R = (-rl).values; volok = ~(vr > 2.0).values
        for th in (0.08, 0.10, 0.12):
            S = (rl.values <= -th) & ab
            for vname, sig in [("no volume filter", S), ("skip volume > 2x", S & volok)]:
                for pname, park in PARK.items():
                    if th != 0.10 and pname != "Nifty trend (100-day), else liquid": continue
                    for tag, kw in [("ideal", {}), ("realistic", dict(entry="open", cost=0.003))]:
                        r = sim(S if sig is None else sig, R, park, **kw); r.update(universe=f"top {k}", dip=f"{int(th*100)}%", volume=vname, parking=pname, scenario=tag)
                        OUT["results"].append(r); print(k, th, vname, pname, tag, r["cagr"], r["dd"], r.get("win_rate"), r["per"], flush=True)
        # parking alone (no trades)
        for pname, park in PARK.items():
            r = sim(np.zeros_like(M), R, park); r.update(universe=f"top {k}", dip="none", volume="-", parking=pname, scenario="parking only"); OUT["results"].append(r)
    os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_dip.json", "w"), indent=1, default=float)
try: run()
except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open("data/india_trend.json" if sys.argv[1:2] == ["trend"] else "data/india_dip.json", "w")); print(traceback.format_exc()); sys.exit(1)
