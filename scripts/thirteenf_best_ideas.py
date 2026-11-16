"""13F 'best ideas' (Nov 15 2026). Research only, not financial advice.
Idea (Cohen, Polk & Silli 2010, 'Best Ideas'): a fund manager's single biggest position (highest portfolio weight) is their
highest-conviction pick and has historically beaten the market; picks that several managers share may be stronger.
Data (free): SEC Form 13F data sets (every 13F-HR filing, holdings by CUSIP), 2015q4 onward. Managers kept: 20-400 positions
(active stock pickers, not index giants), biggest position <= 40% of the portfolio (skip parent-company stakes).
CUSIP -> ticker: OpenFIGI (free API, common stock only, ETFs dropped). Prices: all-US daily (R2 daily/us_all_adj_all.json.gz, 2016+, incl delisted).
Portfolio: on each 13F deadline (quarter end + 46 days) equal-weight the stocks that are a best idea of >= 1 manager
(and >= 3 managers = 'consensus'); hold until the next deadline. Baselines: equal-weight ALL eligible stocks ($5+, $5M/day) and SPY.
Costs 0.3% per quarterly rebalance. DRY=random|planted uses synthetic prices and picks."""
import os, sys, io, json, time, zipfile, urllib.request, urllib.error
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DRY = os.environ.get("DRY", ""); OUT = os.environ.get("OUT", "data/thirteenf_best_ideas.json" if not DRY else f"/tmp/13f_{DRY}.json")
UA = os.environ.get("SEC_USER_AGENT", ""); FLIM = int(os.environ.get("FILES", "0"))
QCOST = 0.003
FILES = [f"{y}q{q}" for y in range(2015, 2024) for q in range(1, 5) if (y, q) >= (2015, 4)] + [
    "01jan2024-29feb2024", "01mar2024-31may2024", "01jun2024-31aug2024", "01sep2024-30nov2024", "01dec2024-28feb2025",
    "01mar2025-31may2025", "01jun2025-31aug2025", "01sep2025-30nov2025", "01dec2025-28feb2026", "01mar2026-31may2026", "01jun2026-31aug2026", "01sep2026-30nov2026"]

# ---------------- prices
if DRY:
    rng = np.random.default_rng(9); D, N = 2700, 1500
    dates = pd.bdate_range("2016-01-04", periods=D); tick = [f"S{i}" for i in range(N)]
    C = 30 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, (D, N)), axis=0)); V = np.full((D, N), 1e6); SP = 200 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, D)))
else:
    import r2cache
    if not UA: raise SystemExit("SEC_USER_AGENT secret missing")
    cache = r2cache.load("daily/us_all_adj_all.json.gz")
    if not cache: raise SystemExit("R2 cache daily/us_all_adj_all.json.gz missing")
    rows = cache["rows"]; del cache
    dates = pd.DatetimeIndex(sorted(rows["SPY"])); ds = [d.strftime("%Y-%m-%d") for d in dates]; di = {d: i for i, d in enumerate(ds)}
    tick = sorted(s for s in rows if s != "SPY"); D, N = len(ds), len(tick)
    C = np.full((D, N), np.nan); V = np.full((D, N), np.nan)
    for j, s in enumerate(tick):
        for d, v in rows[s].items():
            i = di.get(d)
            if i is not None: C[i, j], V[i, j] = v[0], v[1]
    SP = np.array([rows["SPY"][d][0] for d in ds]); del rows
TI = {t: j for j, t in enumerate(tick)}; dn = dates.values
with np.errstate(all="ignore"):
    Cf = pd.DataFrame(C).ffill().values
    dvol = pd.DataFrame(C * V).rolling(20, min_periods=15).mean().values
    ELIG = np.isfinite(C) & (C >= 5) & (dvol >= 5e6)
    rnk = pd.DataFrame(np.where(ELIG, dvol, np.nan)).rank(axis=1, ascending=False).values
print("days", D, "stocks", N, str(dn[0])[:10], str(dn[-1])[:10], flush=True)

# ---------------- 13F parsing -> per quarter: {period_end: [(cik, filed, cusip_of_top, weight)]}
def sec_get(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            print("http", e.code, url, flush=True); time.sleep(5 * 2 ** a)
        except Exception as e: print("err", str(e)[:100], flush=True); time.sleep(5 * 2 ** a)
    return None
NEED = {"SUBMISSION.TSV": {"ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"},
        "INFOTABLE.TSV": {"ACCESSION_NUMBER", "CUSIP", "VALUE", "PUTCALL", "SSHPRNAMTTYPE"}}
def parse(b, name):
    z = zipfile.ZipFile(io.BytesIO(b)); nm = {n.split("/")[-1].upper(): n for n in z.namelist()}; T = {}
    for f, cols in NEED.items():
        if f not in nm: raise SystemExit(f"{name}: {f} missing; zip has {sorted(nm)}")
        T[f] = pd.read_csv(z.open(nm[f]), sep="\t", dtype=str, usecols=lambda c_: c_.upper() in cols, quoting=3, on_bad_lines="skip").rename(columns=str.upper)
        if cols - set(T[f].columns): raise SystemExit(f"{name}: {f} lacks {cols - set(T[f].columns)}")
    sub = T["SUBMISSION.TSV"]; sub = sub[sub.SUBMISSIONTYPE.str.strip() == "13F-HR"]
    it = T["INFOTABLE.TSV"]; it = it[it.ACCESSION_NUMBER.isin(set(sub.ACCESSION_NUMBER)) & it.PUTCALL.isna() & (it.SSHPRNAMTTYPE.str.strip() == "SH")]
    it = it.assign(v=pd.to_numeric(it.VALUE, errors="coerce"), cu=it.CUSIP.str.strip().str.upper().str[:9])
    pos = it.groupby(["ACCESSION_NUMBER", "cu"]).v.sum().reset_index()
    g = pos.groupby("ACCESSION_NUMBER"); n = g.cu.size(); tot = g.v.sum()
    top = pos.loc[pos.groupby("ACCESSION_NUMBER").v.idxmax()].set_index("ACCESSION_NUMBER")
    out = sub.set_index("ACCESSION_NUMBER").join(pd.DataFrame({"n": n, "tot": tot})).join(top[["cu", "v"]], how="inner")
    out = out[(out.n >= 20) & (out.n <= 400) & (out.tot > 0)]; out["w"] = out.v / out.tot; out = out[out.w <= 0.40]
    return {"cik": out.CIK.astype(str).tolist(), "filed": pd.to_datetime(out.FILING_DATE, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d").tolist(),
            "period": pd.to_datetime(out.PERIODOFREPORT, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d").tolist(), "cusip": out.cu.tolist(), "w": out.w.round(4).tolist()}
def load_ideas():
    rows = []
    for name in (FILES[:FLIM] if FLIM else FILES):
        key = f"sec/13f/{name}.json.gz"; d = r2cache.load(key)
        if d is None:
            b = None
            for base in ("https://www.sec.gov/files/structureddata/data", "https://www.sec.gov/files/datastandardsinnovation/data"):
                b = sec_get(f"{base}/form-13f-data-sets/{name}_form13f.zip"); time.sleep(1)
                if b: break
            if not b: print("not found", name, flush=True); continue
            d = parse(b, name); del b; r2cache.save(key, d)
        print(name, "managers kept", len(d["cik"]), flush=True); rows.append(pd.DataFrame(d))
    return pd.concat(rows, ignore_index=True)

def figi_map(cusips):
    m = r2cache.load("sec/cusip_figi.json.gz") or {}
    todo = [c_ for c_ in sorted(set(cusips)) if c_ not in m]
    print("CUSIPs to map", len(todo), "(cached", len(m), ")", flush=True)
    key = os.environ.get("OPENFIGI_KEY", ""); per, wait = (100, 0.26) if key else (10, 2.5)
    for i in range(0, len(todo), per):
        batch = todo[i:i + per]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c_, "exchCode": "US"} for c_ in batch]).encode()
        hdr = {"Content-Type": "application/json", **({"X-OPENFIGI-APIKEY": key} if key else {})}
        for a in range(6):
            try:
                res = json.load(urllib.request.urlopen(urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body, headers=hdr), timeout=60)); break
            except urllib.error.HTTPError as e:
                if e.code == 429: time.sleep(30); continue
                print("figi http", e.code, flush=True); res = None; break
            except Exception as e: print("figi err", str(e)[:80], flush=True); time.sleep(10); res = None
        if res is None: continue
        for c_, r in zip(batch, res):
            d0 = (r.get("data") or [{}])[0]
            m[c_] = [d0.get("ticker"), d0.get("securityType2") or d0.get("securityType")] if d0 else [None, None]
        time.sleep(wait)
        if i % (per * 50) == 0: print("figi", i, "of", len(todo), flush=True); r2cache.save("sec/cusip_figi.json.gz", m)
    r2cache.save("sec/cusip_figi.json.gz", m)
    return m

# ---------------- build quarterly portfolios
form_days, picks = [], {}
if DRY:
    rng2 = np.random.default_rng(1)
    for q in pd.period_range("2016Q1", "2026Q2", freq="Q"):
        fd = int(np.searchsorted(dn, np.datetime64(q.end_time.normalize() + pd.Timedelta(days=46))))
        if fd >= D - 5: break
        el = np.flatnonzero(ELIG[fd]); pk = rng2.choice(el, 150, replace=False); cnt = rng2.integers(1, 6, 150)
        form_days.append(fd); picks[fd] = dict(zip(pk.tolist(), cnt.tolist()))
    if DRY == "planted":
        for i, fd in enumerate(form_days):
            nd = form_days[i + 1] if i + 1 < len(form_days) else D - 1
            for j in picks[fd]:
                k = nd - fd; C[fd + 1:nd + 1, j] *= 1 + 0.04 * np.arange(1, k + 1) / k; C[nd + 1:, j] *= 1.04
        Cf = pd.DataFrame(C).ffill().values
else:
    I = load_ideas(); I = I[I.period.notna() & I.filed.notna()]
    fm = figi_map(I.cusip.tolist())
    I["ticker"] = [(fm.get(c_) or [None])[0] for c_ in I.cusip]; I["typ"] = [(fm.get(c_) or [None, None])[1] for c_ in I.cusip]
    print("security types of best ideas:", I.typ.value_counts().head(8).to_dict(), flush=True)
    I = I[I.typ.isin(["Common Stock", "REIT", "Ltd Part", "Depositary Receipt"]) & I.ticker.notna()]
    I["ticker"] = I.ticker.str.replace("/", "-").str.upper()
    print("best ideas mapped to a ticker in our price data:", int(I.ticker.isin(TI).sum()), "of", len(I), flush=True)
    for per, g in I.groupby("period"):
        fdate = pd.Timestamp(per) + pd.Timedelta(days=46)
        fd = int(np.searchsorted(dn, np.datetime64(fdate)))
        if fd >= D - 5 or fdate < pd.Timestamp("2016-03-01"): continue
        g = g[pd.to_datetime(g.filed) <= fdate]                           # only filings public by the formation date
        cnt = g[g.ticker.isin(TI)].groupby("ticker").cik.nunique()
        pk = {TI[t]: int(n_) for t, n_ in cnt.items() if np.isfinite(C[fd, TI[t]]) and C[fd, TI[t]] >= 5}
        if len(pk) >= 10: form_days.append(fd); picks[fd] = pk
    form_days = sorted(set(form_days))
    print("quarters", len(form_days), "| avg best-idea stocks per quarter", round(np.mean([len(picks[f]) for f in form_days]), 1), flush=True)
    print("example (latest):", sorted(((tick[j], n_) for j, n_ in picks[form_days[-1]].items()), key=lambda x: -x[1])[:15], flush=True)

# ---------------- simulate: equal weight, buy at formation close, hold to next formation
def run(select):
    curve = np.ones(D); eq = 1.0; per_q = []
    for i, fd in enumerate(form_days):
        nd = form_days[i + 1] if i + 1 < len(form_days) else D - 1
        js = np.array(select(fd), dtype=int)
        if len(js) == 0: curve[fd:nd + 1] = eq; continue
        rel = Cf[fd:nd + 1, js] / Cf[fd, js]; rel = np.where(np.isfinite(rel), rel, 1.0)
        path = rel.mean(axis=1) * (1 - QCOST); curve[fd:nd + 1] = eq * path; per_q.append(path[-1] - 1); eq = curve[nd]
    return curve, per_q
def summary(curve, a, b):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= form_days[0]) & (np.arange(D) <= form_days[-1]))
    if len(ix) < 60: return None
    cv = curve[ix] / curve[ix[0]]; y = len(ix) / 252
    return {"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1)}
SEL = {"best ideas (>= 1 manager)": lambda fd: list(picks[fd]),
       "consensus best ideas (>= 3 managers)": lambda fd: [j for j, n_ in picks[fd].items() if n_ >= 3],
       "best ideas, large (top 500)": lambda fd: [j for j in picks[fd] if rnk[fd, j] <= 500],
       "best ideas, mid (501-1500)": lambda fd: [j for j in picks[fd] if 500 < rnk[fd, j] <= 1500],
       "best ideas, small (1501+)": lambda fd: [j for j in picks[fd] if rnk[fd, j] > 1500],
       "BASELINE all eligible stocks": lambda fd: np.flatnonzero(ELIG[fd]).tolist(),
       "BASELINE large (top 500)": lambda fd: np.flatnonzero(ELIG[fd] & (rnk[fd] <= 500)).tolist()}
RES = {}
spy_curve = SP / SP[0]
for name, f in SEL.items():
    cv, pq = run(f); RES[name] = {p_: summary(cv, a, b) for p_, a, b in (("all", "2016", "2100"), ("2016-2020", "2016", "2021"), ("2021-2026", "2021", "2100"))}
    RES[name]["avg_stocks"] = round(float(np.mean([len(f(fd)) for fd in form_days])), 1)
    print(f"{name:40s} stocks~{RES[name]['avg_stocks']:6.1f} | all {RES[name]['all']} | 2016-20 {RES[name]['2016-2020']} | 2021-26 {RES[name]['2021-2026']}", flush=True)
RES["SPY"] = {p_: summary(spy_curve, a, b) for p_, a, b in (("all", "2016", "2100"), ("2016-2020", "2016", "2021"), ("2021-2026", "2021", "2100"))}
print("SPY", RES["SPY"], flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "quarters": len(form_days), "results": RES,
           "latest_picks": sorted(((tick[j], n_) for j, n_ in picks[form_days[-1]].items()), key=lambda x: -x[1])[:40] if form_days else []},
          open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
