# Four new strategy ideas on the point-in-time S&P 500 (research only, not advice). One mode per run:
#   insider   - cluster of insiders buying their own stock on the open market (SEC Form 4 data sets, 2006+)
#   buyback   - companies shrinking their share count (net buybacks) over the past year (SEC XBRL cover-page shares, ~2010+)
#   additions - buy stocks the day they join the S&P 500; also "deletions" = buy stocks the day they are removed
#   high52    - stocks closest to their 52-week high, rebalanced monthly
# Realistic fills: signal at the close, buy at the next open, 0.15% cost per side. Idle money in SPY (or cash).
# Honest checks: every nearby setting (grid), first half vs second half (pick on A, test on B), SPY over the same years.
import os, sys, json, time, io, zipfile, urllib.request, urllib.error
import pandas as pd, numpy as np

MODE = sys.argv[1]
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
UA = os.environ.get("SEC_USER_AGENT", "research sentinel@example.com")
COST = 0.0015

def fetch(url, dest):
    for i in range(6):
        try: urllib.request.urlretrieve(url, dest); return
        except Exception as e: print("download retry", i + 1, url, e, flush=True); time.sleep(20 * (i + 1))
    raise RuntimeError("download failed: " + url)

def sec(url, raw=False, tries=6):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as r:
                b = r.read(); return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
        except Exception: pass
        time.sleep(1.5 * 2 ** a)
    return None

# ---------------- prices + membership
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): fetch(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close", "stock_splits"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1996-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})].copy(); px["aopen"] = px.open * px.adj_close / px.close
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
C, O = P("adj_close"), P("aopen")
SPL = px[px.stock_splits.fillna(0) > 0][["date", "ticker", "stock_splits"]] if MODE == "buyback" else None
del px
tick = [t for t in ALLT if t != "SPY"]; TI = {t: i for i, t in enumerate(tick)}
valid = C[tick].notna(); Cf = C.ffill()
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
M &= valid & valid.shift(-1, fill_value=False)
spy = Cf["SPY"]; spyr = spy.pct_change().fillna(0).values
Rt = Cf[tick].pct_change().fillna(0).values; OC = (Cf[tick] / O[tick] - 1).fillna(0).values
D = len(dates); di = lambda d: int(np.searchsorted(dates.values, np.datetime64(pd.Timestamp(d))))  # first trading day on/after d
monthstart = np.r_[True, dates.month[1:] != dates.month[:-1]]
PARK = {"spy": spyr, "cash": np.zeros(D)}

def sim(S, R, hold, slots, park, start, end=None, monthly=False):
    """S, R: (D x N) bool / float. Buy top-R signals at next open, hold `hold` days (renewed if still signalled), 1/slots each."""
    end = end or D; eq = 1.0; curve = np.ones(D); pos = []; tr = []; inv = []
    for t in range(start, end):
        used = sum(p[2] for p in pos); day = 0.0
        for p in pos:
            g = OC[t, p[0]] if p[1] == 0 else Rt[t, p[0]]; p[3] *= 1 + g; day += p[2] * g
        day += max(0.0, 1 - used) * park[t]; inv.append(used); eq *= 1 + day
        keep = []
        for p in pos:
            g = OC[t, p[0]] if p[1] == 0 else Rt[t, p[0]]
            p[1] += 1; p[2] *= (1 + g) / (1 + day)
            if (p[1] >= hold - 5 and monthstart[t]) if monthly else p[1] >= hold:   # monthly ideas exit only on rebalance days
                if S[t, p[0]]: p[1] = 1; keep.append(p); continue          # still a signal: keep holding, no trade
                eq *= 1 - COST * p[2]; tr.append(p[3] - 1 - 2 * COST)
            else: keep.append(p)
        pos = keep; used = sum(p[2] for p in pos)
        free = slots - len(pos)
        if free > 0:
            cand = np.where(S[t])[0]
            if len(cand):
                held = {p[0] for p in pos}
                new = [c for c in cand[np.argsort(-R[t, cand])] if c not in held][:free]
                if new:
                    w = min(1.0 / slots, max(0.0, 1 - used) / len(new))
                    for c in new: pos.append([c, 0, w, 1.0]); eq *= 1 - COST * w
        curve[t] = eq
    c = pd.Series(curve[start:end], index=dates[start:end])
    return c, tr, float(np.mean(inv)) if inv else 0.0

def cagr(c):
    yrs = len(c) / 252; return round(100 * ((c.iloc[-1] / c.iloc[0]) ** (1 / yrs) - 1), 1) if yrs > 0.5 else None
def mdd(c): return round(100 * float((c / c.cummax() - 1).min()), 1)

def evaluate(S, R, grid, first_year, split_year, label_fn, extra=None):
    """Run every setting in the grid; report full period, half A / half B, and SPY over the same years."""
    s0, sp = di(f"{first_year}-01-01"), di(f"{split_year}-01-01")
    spyc = pd.Series(spy.values[s0:], index=dates[s0:])
    bench = {"SPY_full": cagr(spyc), "SPY_dd": mdd(spyc), "SPY_A": cagr(spyc.iloc[:sp - s0]), "SPY_B": cagr(spyc.iloc[sp - s0:]),
             "years": f"{first_year}-2026", "A": f"{first_year}-{split_year - 1}", "B": f"{split_year}-2026"}
    rows = []
    for kw in grid:
        SS, RR = (S(kw), R(kw)) if callable(S) else (S, R)
        c, tr, inv = sim(SS, RR, kw["hold"], kw["slots"], PARK[kw.get("park", "spy")], s0, monthly=MODE in ("high52", "buyback"))
        r = dict(setting=label_fn(kw), **{k: v for k, v in kw.items()}, cagr=cagr(c), dd=mdd(c), A=cagr(c.iloc[:sp - s0]), B=cagr(c.iloc[sp - s0:]),
                 trades=len(tr), trades_per_yr=round(len(tr) / (len(c) / 252), 1), win=round(100 * float(np.mean(np.array(tr) > 0)), 1) if tr else None,
                 avg_trade=round(100 * float(np.mean(tr)), 2) if tr else None, invested=round(100 * inv, 1))
        rows.append(r); print(r["setting"], "|", r["cagr"], r["dd"], "A", r["A"], "B", r["B"], "trades/yr", r["trades_per_yr"], flush=True)
    spy_rows = [r for r in rows if r.get("park", "spy") == "spy"] or rows
    best_A = max(spy_rows, key=lambda r: r["A"] if r["A"] is not None else -99)
    summ = {"settings": len(rows), "beat_SPY_full": sum(r["cagr"] > bench["SPY_full"] for r in spy_rows),
            "beat_SPY_both_halves": sum((r["A"] or -99) > bench["SPY_A"] and (r["B"] or -99) > bench["SPY_B"] for r in spy_rows),
            "median_cagr": float(np.median([r["cagr"] for r in spy_rows])), "median_B": float(np.median([r["B"] for r in spy_rows if r["B"] is not None])),
            "best_hindsight": max(spy_rows, key=lambda r: r["cagr"])["setting"], "best_hindsight_cagr": max(r["cagr"] for r in spy_rows),
            "picked_on_A": best_A["setting"], "picked_on_A_then_B": best_A["B"], "spy_rows_counted": len(spy_rows)}
    out = {"mode": MODE, "built": time.strftime("%Y-%m-%d"), "cost_per_side": COST, "benchmark": bench, "summary": summ, "results": rows}
    if extra: out.update(extra)
    os.makedirs("data", exist_ok=True); json.dump(out, open(f"data/new_ideas_{MODE}.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps({"benchmark": bench, "summary": summ}, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))

def grid_of(**axes):
    keys = list(axes); out = [{}]
    for k in keys: out = [dict(o, **{k: v}) for o in out for v in axes[k]]
    return out

def cik_map():
    j = json.load(open("data/sec_events_sic.json"))["tickers"]; m = {}
    for t, v in j.items():
        if v.get("cik") and t in TI: m.setdefault(int(v["cik"]), []).append(t)
    return m

# ---------------- modes
if MODE == "high52":
    hi = Cf[tick].rolling(252, min_periods=240).max(); ratio = (Cf[tick] / hi).where(M).values
    trend200 = (spy > spy.rolling(200).mean()).values
    base = np.nan_to_num(ratio, nan=0.0)
    def S(kw):
        top = np.zeros_like(M.values)
        for t in np.where(monthstart)[0]:
            if kw["trend"] and not trend200[t]: continue
            ok = np.where(M.values[t] & (base[t] > 0))[0]
            top[t, ok[np.argsort(-base[t, ok])][:kw["slots"]]] = True
        return top
    grid = grid_of(slots=[10, 20, 30], hold=[21, 63, 126], trend=[False, True], park=["spy"]) + [dict(slots=20, hold=21, trend=False, park="cash")]
    evaluate(S, lambda kw: base, grid, 1998, 2012, lambda kw: f"top {kw['slots']} nearest 52w high, hold {kw['hold']}d" + (", only when SPY>200d" if kw["trend"] else "") + (", idle cash" if kw["park"] == "cash" else ""))

elif MODE == "additions":
    Sadd = np.zeros((D, len(tick)), bool); Sdel = np.zeros((D, len(tick)), bool); nA = nD = 0
    hasp = valid.values
    for _, m in mem.iterrows():
        if m.ticker not in TI: continue
        j = TI[m.ticker]
        if pd.Timestamp("1998-01-01") <= m.start <= dates[-1]:
            t = di(m.start)
            if t < D and t >= 60 and hasp[t - 60:t, j].sum() >= 40: Sadd[t, j] = True; nA += 1   # traded before joining (skips renames/spin-offs)
        if pd.notna(m.end) and pd.Timestamp("1998-01-01") <= m.end <= dates[-1]:
            t = di(m.end)
            if t + 25 < D and hasp[t:t + 25, j].sum() >= 20: Sdel[t, j] = True; nD += 1           # still trades after removal (skips takeovers)
    Rz = np.zeros((D, len(tick)))
    grid = [dict(kind=k, hold=h, slots=s, park="spy") for k in ["add", "delete"] for h in [5, 21, 63, 126, 252] for s in [10, 20]]
    evaluate(lambda kw: Sadd if kw["kind"] == "add" else Sdel, lambda kw: Rz, grid, 1998, 2012,
             lambda kw: f"{'joins' if kw['kind'] == 'add' else 'removed from'} S&P 500, hold {kw['hold']}d, {kw['slots']} slots", extra={"additions": nA, "deletions": nD})

elif MODE == "insider":
    cm = cik_map(); ev = []; loaded = []
    for y in range(2006, 2027):
        for q in range(1, 5):
            b = None
            for host in ["https://www.sec.gov", "https://dcm.sec.gov"]:
                b = sec(f"{host}/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip", raw=True, tries=3)
                if b: break
            if not b: continue
            try:
                z = zipfile.ZipFile(io.BytesIO(b)); nm = {n.split("/")[-1].upper(): n for n in z.namelist()}
                rd = lambda f, cols: pd.read_csv(z.open(nm[f]), sep="\t", dtype=str, usecols=lambda c: c.upper() in cols, on_bad_lines="skip", quoting=3).rename(columns=str.upper)
                sub = rd("SUBMISSION.TSV", {"ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK"})
                trn = rd("NONDERIV_TRANS.TSV", {"ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD"})
                own = rd("REPORTINGOWNER.TSV", {"ACCESSION_NUMBER", "RPTOWNERCIK"})
            except Exception as e: print("parse fail", y, q, e, flush=True); continue
            sub = sub[sub.DOCUMENT_TYPE.str.strip() == "4"]
            trn = trn[(trn.TRANS_CODE.str.strip() == "P") & (trn.TRANS_ACQUIRED_DISP_CD.str.strip() == "A")].copy()
            trn["val"] = pd.to_numeric(trn.TRANS_SHARES, errors="coerce") * pd.to_numeric(trn.TRANS_PRICEPERSHARE, errors="coerce")
            v = trn.groupby("ACCESSION_NUMBER").val.sum()
            o = own.groupby("ACCESSION_NUMBER").RPTOWNERCIK.first()
            s = sub[sub.ACCESSION_NUMBER.isin(v.index)].copy()
            s["val"] = s.ACCESSION_NUMBER.map(v); s["owner"] = s.ACCESSION_NUMBER.map(o)
            s["date"] = pd.to_datetime(s.FILING_DATE, errors="coerce", format="mixed")
            s["cik"] = pd.to_numeric(s.ISSUERCIK, errors="coerce")
            s = s[s.cik.isin(cm.keys()) & (s.val > 0) & s.date.notna()]
            ev.append(s[["date", "cik", "owner", "val"]]); loaded.append(f"{y}q{q}"); print("loaded", y, q, len(s), flush=True)
            time.sleep(0.3)
    if not ev: raise SystemExit("no Form 4 data sets downloaded")
    E = pd.concat(ev); print("purchase filings at S&P 500 issuers:", len(E), "quarters", len(loaded), flush=True)
    # for each filing day: distinct buyers and $ bought in the trailing 30 calendar days (filed on or before that day)
    cl = []
    for cik, g in E.groupby("cik"):
        g = g.sort_values("date")
        for d in g.date.unique():
            w = g[(g.date > d - pd.Timedelta(days=30)) & (g.date <= d)]
            cl.append((d, cik, w.owner.nunique(), w.val.sum()))
    CL = pd.DataFrame(cl, columns=["date", "cik", "n", "usd"])
    def S_R(kw):
        S = np.zeros((D, len(tick)), bool); R = np.zeros((D, len(tick)))
        for r in CL[(CL.n >= kw["buyers"]) & (CL.usd >= kw["min_usd"])].itertuples():
            t = di(r.date)            # Form 4s often arrive after the close: signal that evening, buy next open
            if t >= D: continue
            for tk in cm[r.cik]:
                j = TI[tk]
                if M.values[t, j]: S[t, j] = True; R[t, j] = r.n * 1e12 + r.usd
        return S, R
    cache = {}
    def get(kw):
        k = (kw["buyers"], kw["min_usd"])
        if k not in cache: cache[k] = S_R(kw)
        return cache[k]
    grid = grid_of(buyers=[1, 2, 3], min_usd=[100_000, 500_000], hold=[21, 63, 126], slots=[10, 20], park=["spy"])
    evaluate(lambda kw: get(kw)[0], lambda kw: get(kw)[1], grid, 2007, 2016,
             lambda kw: f"{kw['buyers']}+ insiders bought >= ${kw['min_usd'] // 1000}k in 30d, hold {kw['hold']}d, {kw['slots']} slots",
             extra={"quarters_loaded": loaded, "purchase_filings": int(len(E))})

elif MODE == "buyback":
    cm = cik_map(); obs = {}   # ticker -> DataFrame(filed, shares)
    for i, (cik, tks) in enumerate(cm.items()):
        j = sec(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"); time.sleep(0.12)
        if not j: continue
        f = j.get("facts", {}); rows = None
        for ns, tag in [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")]:
            u = f.get(ns, {}).get(tag, {}).get("units", {}).get("shares")
            if u: rows = pd.DataFrame(u); break
        if rows is None or rows.empty: continue
        rows = rows[rows.form.isin(["10-K", "10-Q", "10-K/A", "10-Q/A"])]
        s = rows.groupby("accn").agg(filed=("filed", "first"), shares=("val", "sum")).reset_index()   # sum share classes per filing
        s["filed"] = pd.to_datetime(s.filed); s = s.sort_values("filed").drop_duplicates("filed", keep="last")
        for tk in tks: obs[tk] = s[["filed", "shares"]].values
        if i % 100 == 0: print("companyfacts", i, len(cm), flush=True)
    splits = {t: g.set_index("date").stock_splits for t, g in SPL.groupby("ticker")}
    CHG = np.full((D, len(tick)), np.nan)
    for tk, a in obs.items():
        j = TI[tk]; fd = pd.DatetimeIndex(a[:, 0]); sh = a[:, 1].astype(float); sp = splits.get(tk)
        for t in np.where(monthstart)[0]:
            d = dates[t]
            i1 = fd.searchsorted(d, "right") - 1
            if i1 < 0 or (d - fd[i1]).days > 130: continue
            win = np.where((fd <= d - pd.Timedelta(days=300)) & (fd >= d - pd.Timedelta(days=430)))[0]
            if not len(win): continue
            i0 = win[-1]; adj = 1.0
            if sp is not None:
                k = sp[(sp.index > fd[i0]) & (sp.index <= fd[i1])]
                if len(k): adj = float(np.prod(k.values))
            if sh[i0] <= 0: continue
            c = sh[i1] / (sh[i0] * adj) - 1
            if -0.4 < c < 0.4: CHG[t, j] = c
    print("stocks with share-count history:", len(obs), "signal months with data:", int((~np.isnan(CHG)).any(1).sum()), flush=True)
    Mv = M.values
    def S(kw):
        out = np.zeros((D, len(tick)), bool)
        for t in np.where(monthstart)[0]:
            ok = np.where(Mv[t] & (CHG[t] <= -kw["shrink"]))[0]
            out[t, ok[np.argsort(CHG[t, ok])][:kw["slots"]]] = True
        return out
    Rb = np.nan_to_num(-CHG, nan=-9)
    grid = grid_of(shrink=[0.01, 0.03, 0.05], slots=[10, 20, 30], hold=[21, 63], park=["spy"])
    evaluate(S, lambda kw: Rb, grid, 2011, 2019, lambda kw: f"shares down >= {int(kw['shrink'] * 100)}% in a year, top {kw['slots']}, hold {kw['hold']}d",
             extra={"stocks_with_share_history": len(obs)})
else:
    raise SystemExit("unknown mode " + MODE)
