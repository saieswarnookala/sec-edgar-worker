"""India factor-index rotation vs static blend (Nov 22 2026), test #5 of the India strategy report, plus #7 (large vs mid/small switch).
Data: NSE Indices' official Total Return Indices (TRI = with dividends), daily, from niftyindices.com, cached privately in R2 at nse/tri/<slug>.json.
NOTE: factor indices launched 2012-2022; NSE back-calculated their history before launch, so early years are a paper history.
Gold: GOLDBEES.NS (Yahoo) from 2007, liquid fund 6%/yr. Signal at the month-end close, trade the NEXT day's close (no look-ahead).
Costs: 0.2% per buy and per sell (index fund/ETF spread, exit load) + 0.4%/yr fund fee. After-tax (rough, Indian resident):
  switching strategies 20.8% on each year's net gain (losses carried); buy & hold 13% once at the end.
MODE=probe: fetch 60 days of NIFTY 50 and print what came back. DRY=1: fake data (code test)."""
import os, json, time, datetime, urllib.request, urllib.error
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; MODE = os.environ.get("MODE", "run")
OUT = "data/india_factor.json" if not DRY else "/tmp/india_factor_dry.json"
if not DRY and MODE != "probe": import r2cache
IDX = {  # slug: official name
    "n50": "NIFTY 50", "n500": "NIFTY 500", "mid150": "NIFTY MIDCAP 150", "small250": "NIFTY SMALLCAP 250",
    "val30": "NIFTY200 VALUE 30", "alpha50": "NIFTY ALPHA 50", "mom30": "NIFTY200 MOMENTUM 30", "lv30": "NIFTY100 LOW VOLATILITY 30",
    "qual30": "NIFTY200 QUALITY 30", "midmom50": "NIFTY MIDCAP150 MOMENTUM 50", "alv30": "NIFTY ALPHA LOW-VOLATILITY 30"}
LABEL = {"n50": "Nifty 50", "n500": "Nifty 500", "mid150": "Midcap 150", "small250": "Smallcap 250", "val30": "Value 30", "alpha50": "Alpha 50",
         "mom30": "Momentum 30", "lv30": "Low Vol 30", "qual30": "Quality 30", "midmom50": "Midcap150 Momentum 50", "alv30": "Alpha Low-Vol 30"}
H = {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Origin": "https://www.niftyindices.com", "Referer": "https://www.niftyindices.com/reports/historical-data"}
import http.cookiejar
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def warm():   # pick up the site's cookies first, like a browser
    try: OPENER.open(urllib.request.Request("https://www.niftyindices.com/reports/historical-data", headers={"User-Agent": H["User-Agent"]}), timeout=60).read(); print("warm ok", flush=True)
    except Exception as e: print("warm failed", e, flush=True)
def tri_chunk(name, a, b):
    body = json.dumps({"cinfo": json.dumps({"name": name, "startDate": a.strftime("%d-%b-%Y"), "endDate": b.strftime("%d-%b-%Y"), "indexName": name}).replace('"', "'")}).encode()
    for k in range(4):
        try:
            raw = OPENER.open(urllib.request.Request("https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString", data=body, headers=H), timeout=60).read()
            if MODE == "probe": print("  RAW", len(raw), raw[:300], flush=True)
            r = json.loads(raw.decode("utf-8-sig").strip())
            d_ = r.get("d")
            rows = (json.loads(d_) if d_.strip().startswith(("[", "{")) and '"' in d_[:5] else eval(d_, {"__builtins__": {}}, {})) if isinstance(d_, str) else d_ or []
            out = {}
            for x in rows:
                dk = next(k_ for k_ in x if "date" in k_.lower()); vk = next(k_ for k_ in x if "return" in k_.lower() or "tri" in k_.lower())
                try: out[str(pd.Timestamp(x[dk]).date())] = float(str(x[vk]).replace(",", ""))
                except (ValueError, TypeError): pass
            return out, (list(rows[0].keys()) if rows else [])
        except Exception as e: print("  retry", name, a.date(), e, flush=True); time.sleep(4 * (k + 1))
    return {}, []
def fetch(slug):
    name = IDX[slug]; key = f"nse/tri/{slug}.json"; have = r2cache.load(key) or {}
    end = pd.Timestamp.today().normalize(); start = pd.Timestamp(max(have)) + pd.Timedelta(days=1) if have else pd.Timestamp("2003-01-01")
    got = 0; a = start
    while a <= end:
        b = min(a + pd.Timedelta(days=364), end); d, _ = tri_chunk(name, a, b); have.update(d); got += len(d); a = b + pd.Timedelta(days=1); time.sleep(0.7)
    if got: r2cache.save(key, have)
    print(f"{slug:9s} {name:32s} {len(have)} days ({min(have) if have else '-'} to {max(have) if have else '-'}), +{got} new", flush=True)
    return pd.Series(have, dtype=float).sort_index().rename(slug)
def yahoo(sym):
    UA = {"User-Agent": H["User-Agent"]}
    for a in range(4):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1104537600&period2={int(time.time())}&interval=1d", headers=UA), timeout=60).read())["chart"]["result"][0]
            q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); return s[~s.index.duplicated(keep="last")]
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data for " + sym)
if not DRY: warm()
if MODE == "probe":
    end = pd.Timestamp.today().normalize(); d, keys = tri_chunk("NIFTY 50", end - pd.Timedelta(days=60), end)
    print("PROBE NIFTY 50 TRI rows:", len(d), "keys:", keys, "last:", sorted(d.items())[-3:] if d else None)
    d2, _ = tri_chunk("NIFTY200 VALUE 30", pd.Timestamp("2006-01-01"), pd.Timestamp("2006-12-31")); print("PROBE VALUE 30 (2006) rows:", len(d2))
    raise SystemExit(0 if d else 1)
# ---------- data ----------
if DRY:
    ix = pd.bdate_range("2005-04-01", "2026-11-20"); rng = np.random.default_rng(7)
    S = {k: pd.Series(1000 * np.exp(np.cumsum(rng.normal(0.0005 + 0.0001 * i, 0.012, len(ix)))), index=ix) for i, k in enumerate(IDX)}
    gold = pd.Series(np.exp(np.cumsum(rng.normal(0.0004, 0.009, len(ix)))), index=ix)
else:
    S = {k: fetch(k) for k in IDX}; gold = yahoo("GOLDBEES.NS")
P = pd.DataFrame(S); P.index = pd.to_datetime(P.index); P = P.sort_index()
P = P[P.index >= "2005-04-01"]; cal = P.index
gold = gold.reindex(cal).ffill(); gr = gold.pct_change().fillna(0).clip(-0.15, 0.15).values
LIQ = (1.06) ** (1 / 248) - 1; FEE = 0.004 / 248; COST = 0.002
R = P.pct_change()
R = R.where(R.abs() < 0.25)             # drop bad prints
print("first day per index:", {k: str(P[k].first_valid_index().date()) for k in P}, flush=True)
n50 = P["n50"]; n_on = (n50 > n50.rolling(100).mean()).values    # crash filter as of the close
g_on = (gold > gold.rolling(100).mean()).values
me = [i for i in range(len(cal) - 1) if cal[i].month != cal[i + 1].month]              # month-end rows
def engine(pick, freq="M", filt=False, name=""):
    """pick(i) -> dict{slug: weight} decided at close of row i; traded at close of i+1 (weights earn from i+2)."""
    reb = set(me if freq == "M" else [i for i in me if cal[i].month in (6, 12)])
    w = {}; pend = None; eq = 1.0; curve = np.full(len(cal), np.nan); start = None; sw = 0; turn = 0.0
    for i in range(len(cal)):
        if start is not None:
            r = sum(wi * (R[k].iat[i] if np.isfinite(R[k].iat[i]) else 0) for k, wi in w.items() if k not in ("gold", "liq"))
            r += w.get("gold", 0) * gr[i] + w.get("liq", 0) * LIQ - sum(wi for k, wi in w.items() if k not in ("gold", "liq")) * FEE
            eq *= 1 + r; w = {k: wi * (1 + (R[k].iat[i] if k not in ("gold", "liq") and np.isfinite(R[k].iat[i]) else gr[i] if k == "gold" else LIQ)) / (1 + r) for k, wi in w.items()}
            curve[i] = eq
        if pend is not None:                                   # trade at this close
            tv = sum(abs(pend.get(k, 0) - w.get(k, 0)) for k in set(pend) | set(w)); eq *= 1 - COST * tv; turn += tv
            if set(k for k, v in pend.items() if v > 0) != set(k for k, v in w.items() if v > 0): sw += 1
            w = dict(pend); pend = None
            if start is None: start = i; curve[i] = eq
        if i in reb:
            tgt = pick(i)
            if tgt is None: continue
            if filt and not n_on[i]: tgt = {"gold": 1.0} if g_on[i] else {"liq": 1.0}
            pend = tgt
    c = pd.Series(curve, index=cal).dropna(); yrs = len(c) / 248
    return c, sw / yrs, turn / yrs
def stats(c, a=None, b=None):
    c = c[(c.index >= (a or c.index[0])) & (c.index < (b or "2100-01-01"))]
    if len(c) < 200: return None
    y = len(c) / 248; c = c / c.iloc[0]
    return {"cagr": round((c.iloc[-1] ** (1 / y) - 1) * 100, 1), "dd": round(float((c / c.cummax() - 1).min()) * 100, 1)}
def after_tax(c, hold=False):
    y = len(c) / 248; m = c.iloc[-1] / c.iloc[0]
    if hold: return round(((1 + (m - 1) * 0.87) ** (1 / y) - 1) * 100, 1)
    ye = c.groupby(c.index.year).last(); prev = c.iloc[0]; eq = 1.0; carry = 0.0
    for v in ye.values:
        g = v / prev - 1; prev = v; t = 0.0
        if g > 0:
            tg = max(0.0, g - carry); carry = max(0.0, carry - g); t = tg * 0.208
        else: carry += -g
        eq *= 1 + g - t
    return round((eq ** (1 / y) - 1) * 100, 1)
def summ(c, sw, tv, hold=False):
    o = {"all": stats(c), "after_tax_rough": after_tax(c, hold), "2005_2012": stats(c, "2005-01-01", "2013-01-01"), "2013_2019": stats(c, "2013-01-01", "2020-01-01"),
         "2020_2026": stats(c, "2020-01-01"), "test_2019_2026": stats(c, "2019-01-01"), "switches_per_year": round(sw, 1), "turnover_per_year": round(tv, 1),
         "start": str(c.index[0].date())}
    return o
RES = {"note": __doc__, "built": str(datetime.date.today()), "dry": DRY or None, "first_day": {k: str(P[k].first_valid_index().date()) for k in P}, "hold": {}, "blend": {}, "rotation": {}, "size_switch": {}}
def avail(i, ks): return [k for k in ks if np.isfinite(P[k].iat[i]) and i >= 260 and np.isfinite(P[k].iat[i - 252])]
def pr(k, o): print(f"{k:70s} {o['all']['cagr'] if o['all'] else None:>5}% at~{o['after_tax_rough']:>5} dd {o['all']['dd'] if o['all'] else None:>6} | 19-26 {o['test_2019_2026']} | sw/yr {o['switches_per_year']}", flush=True)
# 1) buy & hold each (from its own first day)
for k in IDX:
    c, sw, tv = engine(lambda i, k=k: {k: 1.0} if np.isfinite(P[k].iat[i]) else None); RES["hold"][LABEL[k]] = summ(c, sw, tv, hold=True); pr("HOLD " + LABEL[k], RES["hold"][LABEL[k]])
CORE = ["val30", "alpha50", "mom30", "lv30"]; ALL7 = CORE + ["qual30", "midmom50", "alv30"]
common = max(P[k].first_valid_index() for k in CORE); print("core 4 all available from", common.date(), flush=True)
ok_from = lambda ks: max(P[k].first_valid_index() for k in ks) + pd.Timedelta(days=380)
# 2) static blends, rebalanced every 6 months
for lbl, ks in (("Value 30 + Momentum 30 (50/50)", ["val30", "mom30"]), ("Value + Momentum + Low Vol (1/3 each)", ["val30", "mom30", "lv30"]),
                ("Core 4 equal (Value, Alpha, Momentum, Low Vol)", CORE), ("Core 4 + Quality 30 equal", CORE + ["qual30"]),
                ("Value 30 + Midcap150 Momentum 50 (50/50)", ["val30", "midmom50"])):
    fr = ok_from(ks)
    for filt in (False, True):
        c, sw, tv = engine(lambda i, ks=ks, fr=fr: {k: 1 / len(ks) for k in ks} if cal[i] >= fr else None, "S", filt)
        key = f"{lbl}{' + crash filter' if filt else ''}"; RES["blend"][key] = summ(c, sw, tv); pr("BLEND " + key, RES["blend"][key])
# 3) rotation: hold top-N by trailing return
for uni_l, uni in (("core 4", CORE), ("all 7 factors", ALL7)):
    fr = ok_from(CORE)
    for lb in (6, 12):
        for top in (1, 2):
            for freq in ("M", "S"):
                for filt in (False, True):
                    def pick(i, uni=uni, lb=lb, top=top, fr=fr):
                        if cal[i] < fr: return None
                        ks = avail(i, uni); sc = {k: P[k].iat[i] / P[k].iat[i - 21 * lb] - 1 for k in ks if np.isfinite(P[k].iat[i - 21 * lb])}
                        best = sorted(sc, key=lambda k: -sc[k])[:top]; return {k: 1 / len(best) for k in best} if best else None
                    c, sw, tv = engine(pick, freq, filt)
                    key = f"{uni_l} | top {top} by {lb}-month return | {'monthly' if freq == 'M' else 'every 6 months'}{' | crash filter' if filt else ''}"
                    RES["rotation"][key] = summ(c, sw, tv); pr("ROT " + key, RES["rotation"][key])
# 4) (#7) large vs mid vs small switch, monthly, liquid if the winner's trailing return < liquid
for lbl, uni in (("Nifty 50 vs Midcap 150", ["n50", "mid150"]), ("Nifty 50 vs Midcap 150 vs Smallcap 250", ["n50", "mid150", "small250"])):
    fr = ok_from(uni)
    for lb in (6, 12):
        def pick(i, uni=uni, lb=lb, fr=fr):
            if cal[i] < fr: return None
            sc = {k: P[k].iat[i] / P[k].iat[i - 21 * lb] - 1 for k in avail(i, uni) if np.isfinite(P[k].iat[i - 21 * lb])}
            if not sc: return None
            b = max(sc, key=sc.get); return {b: 1.0} if sc[b] > (1.06 ** (lb / 12) - 1) else {"liq": 1.0}
        c, sw, tv = engine(pick, "M"); key = f"{lbl} | best by {lb}-month return, liquid if none beats it | monthly"
        RES["size_switch"][key] = summ(c, sw, tv); pr("SIZE " + key, RES["size_switch"][key])
# monthly correlation between factor indices (shows how much rotation can add)
mo = P[CORE + ["n50"]].resample("ME").last().pct_change().dropna(); RES["monthly_correlation"] = mo.corr().round(2).rename(index=LABEL, columns=LABEL).to_dict()
best = max(RES["rotation"].items(), key=lambda kv: kv[1]["all"]["cagr"] if kv[1]["all"] else -99)
RES["best_rotation_in_sample_warning"] = f"best of {len(RES['rotation'])} rotation versions: {best[0]} - picked with hindsight, expect less"
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
