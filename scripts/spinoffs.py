"""Spin-offs (Nov 15 2026). Research only, not financial advice.
Idea (Cusatis, Miles & Woolridge 1993; McConnell & Ovtchinnikov; Greenblatt): a newly spun-off company is often dumped by
funds that got shares they didn't want (wrong size / index / sector), then does better than the market over the next 1-2 years.
Data (all free): SEC EDGAR quarterly form index -> every Form 10-12B (registration a company files before it is spun off),
2015-2026. Match each filer to a stock: SEC's company file (data.sec.gov/submissions) tickers, else the Alpaca asset list
(includes delisted names) by company name. Prices: all-US daily bars cached in R2 (daily/us_all_adj_all.json.gz, 2016-2026,
incl. delisted). Spin-off day = the stock's first trading day, which must come after the 10-12B and within 18 months.
Buy at the close of trading day 1, 5 or 20; hold 60/125/250 trading days. If it stops trading (takeover, bankruptcy) the last
price is used. Compared with SPY and with the average stock ($5+) over the same days, after 0.4% round-trip costs.
Dry runs on random data swing +-7% vs the average stock with ~120 events (overlapping 1-year windows), so only a much bigger,
consistent gap counts. Bot: hold each spin-off 250 days from day 20, up to 10 at 10% each, idle money in SPY.
DRY=random|planted: synthetic prices; 'planted' adds +15% over the year after each fake spin-off (must be found)."""
import os, sys, re, io, gzip, json, time, urllib.request, urllib.parse, urllib.error
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DRY = os.environ.get("DRY", ""); OUT = os.environ.get("OUT", "data/spinoffs.json" if not DRY else f"/tmp/spinoffs_{DRY}.json")
QLIM = os.environ.get("QUARTERS", "")
UA = os.environ.get("SEC_USER_AGENT", "")
COST, H, ENTRY = 0.004, (60, 125, 250), (1, 5, 20)

# ---------------- prices
if DRY:
    rng = np.random.default_rng(4); D, N = 2700, 800
    dates = pd.bdate_range("2016-01-04", periods=D); ds = [d.strftime("%Y-%m-%d") for d in dates]
    C = 30 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, (D, N)), axis=0)); SP = 200 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, D)))
    tick = [f"S{i}" for i in range(N)]; starts = {}
    for j in range(0, 120):                                     # 120 fake spin-offs: no price before their first day
        s = int(rng.integers(30, D - 300)); C[:s, j] = np.nan; starts[tick[j]] = s
    SPIN = [(tick[j], s, "fake") for j, s in [(TI_, starts[tick[TI_]]) for TI_ in range(120)]]
    if DRY == "planted":
        for tk, s, _ in SPIN:
            j = tick.index(tk); k = min(250, D - s - 1); C[s + 1:s + 1 + k, j] *= 1 + 0.15 * np.arange(1, k + 1) / 250; C[s + 1 + k:, j] *= 1.15
else:
    import r2cache
    if not UA: raise SystemExit("SEC_USER_AGENT secret missing")
    cache = r2cache.load("daily/us_all_adj_all.json.gz")
    if not cache: raise SystemExit("R2 cache daily/us_all_adj_all.json.gz missing")
    rows = cache["rows"]; del cache
    dates = pd.DatetimeIndex(sorted(rows["SPY"])); ds = [d.strftime("%Y-%m-%d") for d in dates]; di = {d: i for i, d in enumerate(ds)}
    tick = sorted(s for s in rows if s != "SPY"); D, N = len(ds), len(tick)
    C = np.full((D, N), np.nan)
    for j, s in enumerate(tick):
        for d, v in rows[s].items():
            i = di.get(d)
            if i is not None: C[i, j] = v[0]
    SP = np.array([rows["SPY"][d][0] for d in ds]); del rows
TI = {t: j for j, t in enumerate(tick)}; dn = dates.values
firstpx = {t: int(np.argmax(np.isfinite(C[:, j]))) if np.isfinite(C[:, j]).any() else None for t, j in TI.items()}
print("days", D, "stocks", N, ds[0], ds[-1], flush=True)

# ---------------- spin-off list from EDGAR (real mode)
def sec_get(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}), timeout=120) as r:
                b = r.read(); return gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" or b[:2] == b"\x1f\x8b" else b
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 * 2 ** a)
        except Exception: time.sleep(2 * 2 ** a)
    return None
norm = lambda s: re.sub(r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|LLC|PLC|HOLDINGS?|GROUP|THE|N ?V|S ?A|LP|L ?P|TRUST)\b", " ", re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper())).split()
if not DRY:
    quarters = [f"{y}/QTR{q}" for y in range(2015, 2027) for q in range(1, 5) if pd.Timestamp(y, 3 * q - 2, 1) <= pd.Timestamp.today()]
    if QLIM: quarters = quarters[-int(QLIM):]
    filings = []
    for q in quarters:
        b = sec_get(f"https://www.sec.gov/Archives/edgar/full-index/{q}/form.idx"); time.sleep(0.3)
        if not b: print("no index", q, flush=True); continue
        txt = b.decode("latin1"); body = txt.split("-" * 20, 1)[-1].splitlines()
        n0 = len(filings)
        for ln in body:
            if not ln.startswith("10-12B "): continue                     # original 10-12B only (not /A amendments)
            m = re.match(r"^(\S+)\s+(.*?)\s{2,}(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\S+)", ln)
            if m: filings.append({"name": m.group(2).strip(), "cik": int(m.group(3)), "filed": m.group(4)})
        print(q, "10-12B filings", len(filings) - n0, flush=True)
    if not filings: raise SystemExit("no 10-12B filings parsed - index format changed?")
    seen, uniq = set(), []
    for f in sorted(filings, key=lambda x: x["filed"]):
        if f["cik"] not in seen: seen.add(f["cik"]); uniq.append(f)
    print("companies that filed a 10-12B:", len(uniq), flush=True)
    # Alpaca asset names (active + delisted) for name matching
    H_ = {"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""), "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", "")}
    names = {}
    for st in ("active", "inactive"):
        try:
            for a in json.load(urllib.request.urlopen(urllib.request.Request("https://paper-api.alpaca.markets/v2/assets?" + urllib.parse.urlencode({"status": st, "asset_class": "us_equity"}), headers=H_), timeout=120)):
                if a["symbol"] in TI: names.setdefault(" ".join(norm(a.get("name"))), set()).add(a["symbol"])
        except Exception as e: print("alpaca assets error", st, str(e)[:120], flush=True)
    print("alpaca names", len(names), flush=True)
    SPIN, how = [], {"sec_ticker": 0, "name": 0, "no_match": 0, "not_new": 0}
    for f in uniq:
        fi = int(np.searchsorted(dn, np.datetime64(f["filed"])))
        cands = []
        js = sec_get(f"https://data.sec.gov/submissions/CIK{f['cik']:010d}.json"); time.sleep(0.15)
        if js:
            try: cands = [t.replace(".", "-") for t in json.loads(js).get("tickers", [])]
            except Exception: pass
        src = "sec_ticker"
        if not any(c in TI for c in cands): cands = sorted(names.get(" ".join(norm(f["name"])), [])); src = "name"
        hit = None
        for c in cands:
            s = firstpx.get(c)
            if s is not None and s > 5 and fi - 10 <= s <= fi + 378: hit = (c, s); break        # new stock, first trade 0-18 months after filing
        if hit: SPIN.append((hit[0], hit[1], f["name"])); how[src] += 1
        elif any(c in TI for c in cands): how["not_new"] += 1
        else: how["no_match"] += 1
    print("spin-offs matched to a NEW stock:", len(SPIN), how, flush=True)
    print("examples:", [(t, ds[s], n[:30]) for t, s, n in SPIN[:12]], flush=True)

# ---------------- returns
with np.errstate(all="ignore"):
    Cf = pd.DataFrame(C).ffill().values
    elig = np.isfinite(C) & (C >= 5)
def fwd(j, t, h):
    if t >= D or not np.isfinite(C[t, j]): return None
    if t + h >= D: return None
    seg = C[t:t + h + 1, j]; ok = np.flatnonzero(np.isfinite(seg)); u = t + ok[-1]
    r = C[u, j] / C[t, j] - 1
    avg = np.nanmean(np.where(elig[t], Cf[t + h] / Cf[t] - 1, np.nan))
    return r - COST, r - COST - (SP[u] / SP[t] - 1), r - COST - avg
RES = {}
for e in ENTRY:
    for h in H:
        X = [x for x in (fwd(TI[tk], s + e - 1, h) for tk, s, _ in SPIN) if x]
        if len(X) < 8: continue
        X = np.array(X); ts = np.array([s for tk, s, _ in SPIN if fwd(TI[tk], s + e - 1, h)])
        late = dn[np.minimum(ts, D - 1)] >= np.datetime64("2021-01-01")
        def st(Y):
            if len(Y) < 3: return {"n": int(len(Y))}
            return {"n": int(len(Y)), "avg_pct": round(Y[:, 0].mean() * 100, 1), "vs_spy_pct": round(Y[:, 1].mean() * 100, 1), "median_vs_spy_pct": round(float(np.median(Y[:, 1])) * 100, 1),
                    "vs_avg_stock_pct": round(Y[:, 2].mean() * 100, 1), "beat_spy_pct": round((Y[:, 1] > 0).mean() * 100, 1), "t_vs_avg_stock": round(Y[:, 2].mean() / (Y[:, 2].std() / np.sqrt(len(Y))), 2)}
        RES[f"buy day {e}, hold {h}d"] = {"all": st(X), "2016-2020": st(X[~late]), "2021-2026": st(X[late])}
        a = RES[f"buy day {e}, hold {h}d"]
        print(f"buy day {e:2d} hold {h:3d}d  n={a['all']['n']:4d} avg {a['all'].get('avg_pct')}% vs SPY {a['all'].get('vs_spy_pct')}% (median {a['all'].get('median_vs_spy_pct')}%, beat SPY {a['all'].get('beat_spy_pct')}%) vs avg stock {a['all'].get('vs_avg_stock_pct')}% (t {a['all'].get('t_vs_avg_stock')}) | 2016-20 {a['2016-2020'].get('vs_spy_pct')} 2021-26 {a['2021-2026'].get('vs_spy_pct')}", flush=True)

# bot: buy each spin-off at day 20, hold 250 days, 10 slots x 10%, idle money in SPY
spyr = np.r_[0, SP[1:] / SP[:-1] - 1]; entries = {}
for tk, s, _ in SPIN: entries.setdefault(s + 19, []).append(TI[tk])
pos, eq, curve = [], 1.0, np.ones(D); t0 = 260
for t in range(t0, D):
    r = sum(0.1 * (Cf[t, j] / Cf[t - 1, j] - 1) for j, _ in pos)
    eq *= 1 + r + (1 - 0.1 * len(pos)) * spyr[t]; keep = []
    for j, e in pos:
        if t - e >= 250 or not np.isfinite(C[t, j]) and np.isfinite(C[t - 1, j]) is False: eq *= 1 - 0.1 * COST / 2
        else: keep.append((j, e))
    pos = keep
    for j in entries.get(t, []):
        if len(pos) < 10 and np.isfinite(C[t, j]): pos.append((j, t)); eq *= 1 - 0.1 * COST / 2
    curve[t] = eq
y = (D - t0) / 252; cv = curve[t0:] / curve[t0]
BOT = {"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
       "spy_pct": round(((SP[-1] / SP[t0]) ** (1 / y) - 1) * 100, 1)}
print("BOT spin-offs (day 20, hold 1 year, rest in SPY):", BOT, flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "spinoffs": len(SPIN),
           "list": [{"ticker": t, "first_day": ds[s], "name": n} for t, s, n in SPIN], "results": RES, "bot": BOT},
          open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
