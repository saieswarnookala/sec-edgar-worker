"""Insider buying as a filter on the dip bot (Nov 15 2026). Research only, not financial advice.
Question: when an S&P 500 stock triggers the live dip rule, does it bounce better if company officers/directors recently
bought shares with their own money on the open market (SEC Form 4, code P)?
Dip rule = live paper-dip.mjs: point-in-time S&P 500 member, price >= $5, above 200-day avg, 5-day return >= 10% worse than SPY,
volume over the drop <= 2x normal. Buy at the close, sell when the close is back above the 5-day avg (after >= 1 day) or after 5 days.
Insider data: SEC "Insider Transactions Data Sets" (quarterly Form 3/4/5 tables, 2006q1+). A filing counts from the first trading day
AFTER its filing date (Form 4s often arrive after the close), so there is no look-ahead.
Matching: issuer CIK -> price ticker (data/sec_events_sic.json), else the filing's trading symbol if that ticker has prices that day.
Parsed quarters are cached in R2 (sec/form4/<quarter>.json.gz) so re-runs don't re-download.
Modes (env DRY): unset = real SEC data; 'random' = fake insider buys on random days (should show NO edge);
'planted' = fake buys placed before the dips that bounced most (MUST show a big edge) -> proves the plumbing works.
QUARTERS env (e.g. '2024q1,2024q2') limits the download for a smoke run."""
import os, sys, json, time, io, zipfile, urllib.request, urllib.error, bisect
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r2cache

DRY = os.environ.get("DRY", "")
UA = os.environ.get("SEC_USER_AGENT", "")
OUT = os.environ.get("OUT", "data/insider_dips.json" if not DRY else f"/tmp/insider_dips_{DRY}.json")
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
START, SPLIT = "2006-07-01", "2016-01-01"     # 6 months of insider history before the first counted dip
if not DRY and not UA: raise SystemExit("SEC_USER_AGENT secret missing (SEC requires a contact in the User-Agent)")

# ---------------- prices (same build as combined_dip_etf.py)
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "2005-01-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOL = P("adj_close"), P("close"), P("volume"); del px
tick = [t for t in ALLT if t != "SPY"]; TI = {t: i for i, t in enumerate(tick)}; D, J = len(dates), len(tick)
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
valid = A[tick].notna(); HASPX = valid.values
M &= valid & valid.shift(-1, fill_value=False)
Cs = A[tick].ffill(); spy = A["SPY"].ffill()
ex5 = (Cs / Cs.shift(5) - 1).sub(spy / spy.shift(5) - 1, axis=0)
vr = VOL[tick].rolling(5).mean() / VOL[tick].shift(5).rolling(50).mean()
base_ok = M & (RAW[tick] >= 5) & (vr <= 2.0)
SIG = {(d, k): (base_ok & (Cs > Cs.rolling(k).mean()) & (ex5 <= -d)).values for d, k in ((0.10, 200), (0.08, 150))}
C, M5, RK, SP = Cs.values, Cs.rolling(5).mean().values, ex5.values, spy.values
dn = dates.values; t0 = int(np.searchsorted(dn, np.datetime64(START)))
print("stocks", J, dates[0].date(), dates[-1].date(), "dip signals since", START, int(SIG[(0.10, 200)][t0:].sum()), flush=True)

def trade(t, j, hold=5, cost=0.001):
    """Return of one dip trade bought at close t under the bot's exit rule, and SPY over the same days."""
    for k in range(1, hold + 1):
        u = t + k
        if u >= D: return None
        if C[u, j] > M5[u, j] or k == hold: return C[u, j] / C[t, j] - 1 - cost, SP[u] / SP[t] - 1, k
def fwd(t, j, h):
    u = t + h
    return None if u >= D or np.isnan(C[u, j]) else (C[u, j] / C[t, j] - 1) - (SP[u] / SP[t] - 1)

# ---------------- insider events -> per stock sorted lists of (day index, owner, usd, code)
def cik_map():
    j = json.load(open("data/sec_events_sic.json"))["tickers"]; m = {}
    for t, v in j.items():
        if v.get("cik") and t in TI: m.setdefault(int(v["cik"]), []).append(t)
    return m

def sec_get(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=180) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            print("sec http", e.code, url, flush=True)
        except Exception as e: print("sec err", str(e)[:120], url, flush=True)
        time.sleep(5 * 2 ** a)
    return None

NEED = {"SUBMISSION.TSV": {"ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERTRADINGSYMBOL"},
        "NONDERIV_TRANS.TSV": {"ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD"},
        "REPORTINGOWNER.TSV": {"ACCESSION_NUMBER", "RPTOWNERCIK"}}
OPT = {"REPORTINGOWNER.TSV": {"RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE"}}

def parse_quarter(b, q):
    """Form 4 open-market buys (P) and sells (S) at filing level: date, issuer cik, symbol, owner, usd, code, role."""
    z = zipfile.ZipFile(io.BytesIO(b)); nm = {n.split("/")[-1].upper(): n for n in z.namelist()}
    T = {}
    for f, cols in NEED.items():
        if f not in nm: raise SystemExit(f"{q}: table {f} missing; zip has {sorted(nm)}")
        want = cols | OPT.get(f, set())
        T[f] = pd.read_csv(z.open(nm[f]), sep="\t", dtype=str, usecols=lambda c: c.upper() in want, on_bad_lines="skip", quoting=3).rename(columns=str.upper)
        miss = cols - set(T[f].columns)
        if miss: raise SystemExit(f"{q}: {f} lacks columns {miss}; has {list(T[f].columns)}")
    sub, trn, own = T["SUBMISSION.TSV"], T["NONDERIV_TRANS.TSV"], T["REPORTINGOWNER.TSV"]
    sub = sub[sub.DOCUMENT_TYPE.str.strip().isin(["4", "4/A"])]
    trn = trn[trn.TRANS_CODE.str.strip().isin(["P", "S"])].copy(); trn["code"] = trn.TRANS_CODE.str.strip()
    trn = trn[((trn.code == "P") & (trn.TRANS_ACQUIRED_DISP_CD.str.strip() == "A")) | ((trn.code == "S") & (trn.TRANS_ACQUIRED_DISP_CD.str.strip() == "D"))]
    trn["usd"] = (pd.to_numeric(trn.TRANS_SHARES, errors="coerce") * pd.to_numeric(trn.TRANS_PRICEPERSHARE, errors="coerce")).clip(0, 5e9)
    v = trn.groupby(["ACCESSION_NUMBER", "code"]).usd.sum().reset_index()
    if "RPTOWNER_RELATIONSHIP" in own.columns:
        rel = own.RPTOWNER_RELATIONSHIP.fillna("").str.upper() + " " + own.get("RPTOWNER_TITLE", pd.Series("", index=own.index)).fillna("").str.upper()
        own["role"] = np.where(rel.str.contains("DIRECTOR") | rel.str.contains("OFFICER"), "od", np.where(rel.str.contains("TENPERCENT") | rel.str.contains("10%"), "10", "x"))
    else: own["role"] = "?"
    o = own.groupby("ACCESSION_NUMBER").agg(owner=("RPTOWNERCIK", "first"), role=("role", lambda r: "od" if (r == "od").any() else r.iloc[0]))
    s = sub.merge(v, on="ACCESSION_NUMBER").merge(o, left_on="ACCESSION_NUMBER", right_index=True, how="left")
    s["date"] = pd.to_datetime(s.FILING_DATE.str.strip(), errors="coerce", format="mixed")
    s = s[s.date.notna() & (s.usd > 0)]
    return {"date": s.date.dt.strftime("%Y-%m-%d").tolist(), "cik": pd.to_numeric(s.ISSUERCIK, errors="coerce").fillna(0).astype(int).tolist(),
            "sym": s.ISSUERTRADINGSYMBOL.fillna("").str.strip().str.upper().tolist(), "owner": s.owner.fillna("").tolist(),
            "usd": s.usd.round(0).tolist(), "code": s.code.tolist(), "role": s.role.fillna("?").tolist()}

def quarters():
    if os.environ.get("QUARTERS"): return [q.strip() for q in os.environ["QUARTERS"].split(",") if q.strip()]
    last = pd.Timestamp.today() - pd.Timedelta(days=45)       # SEC posts a quarter a few weeks after it ends
    return [f"{y}q{q}" for y in range(2006, last.year + 1) for q in range(1, 5) if pd.Timestamp(y, 3 * q, 1) <= last]

def load_real():
    rows, got, cached = [], [], 0
    for q in quarters():
        key = f"sec/form4/{q}.json.gz"; d = r2cache.load(key)
        if d is not None: cached += 1
        else:
            b = None
            for base in ("https://www.sec.gov/files/structureddata/data", "https://www.sec.gov/files/datastandardsinnovation/data"):
                b = sec_get(f"{base}/insider-transactions-data-sets/{q}_form345.zip"); time.sleep(1.5)   # far below SEC's 10 requests/s
                if b: break
            if not b: print("not found:", q, flush=True); continue
            d = parse_quarter(b, q); r2cache.save(key, d)
        n = len(d["date"]); got.append(q)
        print(q, "filings", n, "buys", sum(c == "P" for c in d["code"]), "roles", {r: d["role"].count(r) for r in set(d["role"])}, flush=True)
        rows.append(pd.DataFrame(d))
    if not rows: raise SystemExit("no insider quarters loaded")
    E = pd.concat(rows, ignore_index=True); E["date"] = pd.to_datetime(E.date)
    print(f"quarters {len(got)} ({cached} from R2 cache), filings {len(E)}", flush=True)
    # map to price tickers: CIK first, else trading symbol (BRK.B -> BRK-B) if that ticker has a price that day
    cm = cik_map(); E["e"] = np.searchsorted(dn, E.date.values.astype("datetime64[ns]"), side="right")   # first trading day AFTER filing
    E = E[E.e < D]; out = []
    for r in E.itertuples(index=False):
        tks = cm.get(r.cik) or ([r.sym.replace(".", "-").replace("/", "-")] if r.sym else [])
        for tk in tks:
            j = TI.get(tk)
            if j is not None and HASPX[r.e, j]: out.append((j, r.e, r.owner, r.usd, r.code, r.role))
    ev = pd.DataFrame(out, columns=["j", "e", "owner", "usd", "code", "role"])
    print("mapped to S&P price history:", len(ev), "of", len(E), "| buys", int((ev.code == "P").sum()), "| roles", ev.role.value_counts().to_dict(), flush=True)
    return ev, got

def load_fake(sigs, rets):
    rng = np.random.default_rng(7); out = []
    if DRY == "random":
        for _ in range(60000):
            j, e = rng.integers(J), rng.integers(t0 - 130, D)
            if HASPX[e, j]: out.append((j, e, f"o{rng.integers(5)}", 50000.0, "P" if rng.random() < .3 else "S", "od"))
    else:   # planted: an insider buy 1-20 days before the top 15% best-bouncing dips
        cut = np.quantile(rets, 0.85)
        for (t, j), r in zip(sigs, rets):
            if r >= cut: out.append((j, t - rng.integers(0, 20), "o1", 200000.0, "P", "od"))
    return pd.DataFrame(out, columns=["j", "e", "owner", "usd", "code", "role"]), ["fake"]

# ---------------- per-signal trades + insider features
sig = SIG[(0.10, 200)]
S = [(t, j) for t in range(t0, D) for j in np.flatnonzero(sig[t])]
TR = [trade(t, j) for t, j in S]
keep = [i for i, x in enumerate(TR) if x is not None]; S = [S[i] for i in keep]; TR = [TR[i] for i in keep]
ev, got = load_real() if not DRY else load_fake(S, [x[0] for x in TR])
od = ev[ev.role.isin(["od", "?"])]                      # officers & directors (or unknown role if the column is missing)
BY = {}
for (j, code), g in od.sort_values("e").groupby(["j", "code"]): BY[(j, code)] = (g.e.values, g.owner.values, g.usd.values)
covered = set(ev.j.unique())

def feat(t, j, code, w):
    x = BY.get((j, code))
    if x is None: return 0, 0.0
    a, b = bisect.bisect_right(x[0], t - w), bisect.bisect_right(x[0], t)     # events known by day t, inside the window
    return len(set(x[1][a:b])), float(x[2][a:b].sum())

rows = []
for (t, j), (r, s, k) in zip(S, TR):
    b21, u21 = feat(t, j, "P", 21); b63, u63 = feat(t, j, "P", 63); b126, _ = feat(t, j, "P", 126); b7, _ = feat(t, j, "P", 7)
    s63, su63 = feat(t, j, "S", 63)
    rows.append(dict(t=t, j=j, year=int(str(dn[t])[:4]), late=dn[t] >= np.datetime64(SPLIT), covd=j in covered, ret=r, exc=r - s, days=k,
                     f21=fwd(t, j, 21), f63=fwd(t, j, 63), b7=b7, b21=b21, b63=b63, b126=b126, u63=u63, s63=s63, su63=su63))
X = pd.DataFrame(rows)
print("dip trades", len(X), "| issuer has insider data:", f"{X.covd.mean():.0%}", flush=True)
Xc = X[X.covd]

def stats(g):
    if len(g) == 0: return {"n": 0}
    m, sd = g.ret.mean(), g.ret.std()
    return {"n": int(len(g)), "avg_trade_pct": round(m * 100, 2), "win_pct": round((g.ret > 0).mean() * 100, 1),
            "avg_vs_spy_pct": round(g.exc.mean() * 100, 2), "next_21d_vs_spy_pct": round(g.f21.dropna().mean() * 100, 2),
            "next_63d_vs_spy_pct": round(g.f63.dropna().mean() * 100, 2), "_m": m, "_v": sd ** 2 / len(g) if len(g) > 1 else np.nan}

GROUPS = [("all dips (issuer has insider data)", lambda x: x.t >= 0),
          ("no insider buy in prior 6 months", lambda x: x.b126 == 0),
          ("insider buy in prior 1 month", lambda x: x.b21 >= 1),
          ("insider buy in prior 3 months", lambda x: x.b63 >= 1),
          ("insider buy in prior 6 months", lambda x: x.b126 >= 1),
          ("insider bought INTO the drop (last 7 days)", lambda x: x.b7 >= 1),
          ("2+ insiders bought in prior 3 months", lambda x: x.b63 >= 2),
          ("insiders bought >= $100k in prior 3 months", lambda x: x.u63 >= 1e5),
          ("insider sales in prior 3 months", lambda x: x.s63 >= 1),
          ("no insider sales in prior 3 months", lambda x: x.s63 == 0),
          ("3+ insiders sold in prior 3 months", lambda x: x.s63 >= 3)]
res = {}
for per, sl in (("2006-2026", Xc), ("2006-2015", Xc[~Xc.late]), ("2016-2026", Xc[Xc.late])):
    base = stats(sl[sl.b126 == 0]); res[per] = {}
    for name, f in GROUPS:
        st = stats(sl[f(sl)])
        if st["n"] > 1 and base["n"] > 1 and name != "no insider buy in prior 6 months":
            st["diff_vs_no_buy_pct"] = round((st["_m"] - base["_m"]) * 100, 2); st["t_stat"] = round((st["_m"] - base["_m"]) / np.sqrt(st["_v"] + base["_v"]), 2)
        res[per][name] = {k: v for k, v in st.items() if not k.startswith("_")}
for name, _ in GROUPS:
    a, b, c = (res[p][name] for p in ("2006-2026", "2006-2015", "2016-2026"))
    print(f"{name:45s} n={a['n']:6d} avg {a.get('avg_trade_pct')}% win {a.get('win_pct')}% diff {a.get('diff_vs_no_buy_pct', '')} t {a.get('t_stat', '')} "
          f"| early {b.get('avg_trade_pct')} late {c.get('avg_trade_pct')} | 21d {a.get('next_21d_vs_spy_pct')} 63d {a.get('next_63d_vs_spy_pct')}", flush=True)
yrs = {}
for y, g in Xc.groupby("year"):
    a, b = g[g.b63 >= 1].ret, g[g.b126 == 0].ret
    if len(a) >= 3: yrs[int(y)] = {"insider_n": int(len(a)), "insider_avg": round(a.mean() * 100, 2), "no_buy_avg": round(b.mean() * 100, 2)}
beat = sum(v["insider_avg"] > v["no_buy_avg"] for v in yrs.values())
print(f"years where 'insider buy in 3 months' dips beat 'no buy' dips: {beat} of {len(yrs)}", flush=True)

# ---------------- portfolio: 10 slots x 10%, idle money in SPY when SPY > 100-day avg
spyr = np.r_[0, SP[1:] / SP[:-1] - 1]; park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]
INS = {}
for r in X.itertuples(): INS[(r.t, r.j)] = (r.b63, r.s63)
def flags(t, j, sigk):
    if sigk == (0.10, 200) and (t, j) in INS: return INS[(t, j)]
    return feat(t, j, "P", 63)[0], feat(t, j, "S", 63)[0]
def sim(mode="base", sigk=(0.10, 200), hold=5, slots=10, w=0.10, cost=0.0005):
    sg = SIG[sigk]; pos, eq, curve, trades = [], 1.0, np.ones(D), []
    for t in range(t0, D):
        r = sum(w * (C[t, p[0]] / C[t - 1, p[0]] - 1) for p in pos)
        if park_on[t]: r += (1 - w * len(pos)) * spyr[t]
        eq *= 1 + r; keep = []
        for p in pos:
            age = t - p[1]
            if age >= 1 and (C[t, p[0]] > M5[t, p[0]] or age >= hold): eq *= 1 - w * 2 * cost; trades.append((p[1], C[t, p[0]] / p[2] - 1 - 2 * cost))
            else: keep.append(p)
        pos = keep; held = {p[0] for p in pos}; free = slots - len(pos)
        if free > 0:
            c = [j for j in np.flatnonzero(sg[t]) if j not in held]
            if mode != "base":
                fl = {j: flags(t, j, sigk) for j in c}
                if mode == "insider only": c = [j for j in c if fl[j][0] >= 1]
                if mode == "skip heavy sellers": c = [j for j in c if fl[j][1] < 3]
                if mode == "insider first": c.sort(key=lambda j: (-min(fl[j][0], 1), RK[t, j]))
                else: c.sort(key=lambda j: RK[t, j])
            else: c.sort(key=lambda j: RK[t, j])
            for j in c[:free]: pos.append((j, t, C[t, j]))
        curve[t] = eq
    out = {}
    for name, a, b in (("2006-2026", START, "2100-01-01"), ("2006-2015", START, SPLIT), ("2016-2026", SPLIT, "2100-01-01")):
        idx = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
        cv = curve[idx] / curve[idx[0]]; yrs_ = len(idx) / 252; s = SP[idx] / SP[idx[0]]
        tr = [x[1] for x in trades if a <= str(dn[x[0]])[:10] < b]
        out[name] = {"per_year_pct": round((cv[-1] ** (1 / yrs_) - 1) * 100, 1), "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
                     "spy_pct": round((s[-1] ** (1 / yrs_) - 1) * 100, 1), "trades_per_month": round(len(tr) / (yrs_ * 12), 1),
                     "avg_trade_pct": round(float(np.mean(tr)) * 100, 2) if tr else None, "win_pct": round(float(np.mean([x > 0 for x in tr])) * 100, 1) if tr else None}
    return out
PORT = {}
for name, kw in (("today's rules", {}), ("insider buyers get slots first", {"mode": "insider first"}),
                 ("only dips with an insider buy (3 months)", {"mode": "insider only"}), ("skip dips where 3+ insiders sold", {"mode": "skip heavy sellers"}),
                 ("bot 6 tuned (8%/150-day/hold 7)", {"sigk": (0.08, 150), "hold": 7}),
                 ("bot 6 tuned + insider buyers first", {"sigk": (0.08, 150), "hold": 7, "mode": "insider first"})):
    PORT[name] = sim(**kw); a = PORT[name]
    print(f"PORTFOLIO {name:42s} {a['2006-2026']['per_year_pct']}%/yr worst {a['2006-2026']['worst_drop_pct']}% | early {a['2006-2015']['per_year_pct']} late {a['2016-2026']['per_year_pct']} "
          f"| trades/mo {a['2006-2026']['trades_per_month']} avg {a['2006-2026']['avg_trade_pct']}%", flush=True)

json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "quarters": got, "dip_trades": int(len(X)),
           "share_with_insider_data": round(float(X.covd.mean()), 3), "groups": res, "by_year_3m_buy_vs_none": yrs,
           "years_insider_dips_beat": f"{beat} of {len(yrs)}", "portfolio": PORT}, open(OUT, "w"), indent=1)
print("wrote", OUT, flush=True)
