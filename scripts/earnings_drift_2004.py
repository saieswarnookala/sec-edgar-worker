# Earnings drift 2004-2015 (out-of-sample) on survivorship-free S&P 500 data (Johnbrick123/sp500-data).
# Events: SEC 8-K Item 2.02. Reaction = stock adj return minus SPY on reaction day (filed before 09:30 ET -> same day, else next).
# Buy next open, hold h days, sell at close, 10 slots, costs 0.05%/side. Point-in-time membership. Research only.
import os, json, re, time, urllib.request, random
import pandas as pd, numpy as np
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet", "members.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
UA = os.environ["SEC_USER_AGENT"]; LOG = {}
def sec(url, tries=6):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r: return json.load(r) if url.endswith(".json") else r.read().decode("latin-1")
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
        except Exception: pass
        time.sleep(1.5 * 2 ** a)
    return None
START, END = "2004-08-01", "2015-12-31"
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
mem = mem[(mem.end.isna() | (mem.end > START)) & (mem.start < END)].copy()
info = pd.read_parquet("/tmp/members.parquet"); LOG["members_columns"] = list(info.columns)
tcol = next((c for c in info.columns if "tick" in c.lower() or "symbol" in c.lower()), None)
ncol = next((c for c in info.columns if any(k in c.lower() for k in ["name", "security", "company", "title"])), None)
ccol = next((c for c in info.columns if "cik" in c.lower()), None)
names, ciks = {}, {}
if tcol:
    for _, r in info.iterrows():
        if ncol and pd.notna(r[ncol]): names.setdefault(r[tcol], str(r[ncol]))
        if ccol and pd.notna(r[ccol]):
            try: ciks.setdefault(r[tcol], int(float(r[ccol])))
            except Exception: pass
LOG["names"], LOG["ciks_in_dataset"] = len(names), len(ciks)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close"])
px["date"] = pd.to_datetime(px.date); px = px[(px.date >= "2004-06-01") & (px.date <= "2016-04-30")]
want = set(mem.ticker) | {"SPY"}; px = px[px.ticker.isin(want)]
px["aopen"] = px.open * px.adj_close / px.close
dates = sorted(px[px.ticker == "SPY"].date.unique()); D = [str(pd.Timestamp(d).date()) for d in dates]; N = len(D); idx = {d: i for i, d in enumerate(D)}
C = px.pivot_table(index="date", columns="ticker", values="adj_close").reindex(dates); O = px.pivot_table(index="date", columns="ticker", values="aopen").reindex(dates)
Craw = C.copy(); C = C.ffill()
LOG["days"], LOG["tickers_with_prices"] = N, int(C.shape[1])
# CIK mapping
tk = sec("https://www.sec.gov/files/company_tickers.json") or {}
byT = {v["ticker"].upper(): v["cik_str"] for v in tk.values()}
SUF = set("INC INCORPORATED CORP CORPORATION CO COMPANY COMPANIES LTD LIMITED PLC LLC LP HOLDINGS HOLDING GROUP THE NV SA AG SE TRUST BANCORP CLASS A B C DE NEW INTERNATIONAL INTL".split())
norm = lambda s: " ".join(w for w in re.sub(r"[^A-Z0-9 ]", " ", re.sub(r"\(.*?\)", " ", (s or "").upper().replace("&", " AND "))).split() if w not in SUF)
need_names = {norm(names[t]) for t in mem.ticker if t in names}; nameC = {}
lk = sec("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt") or ""
for line in lk.split("\n"):
    i = line.rfind(":", 0, len(line) - 1)
    if i < 0: continue
    k = norm(line[:i])
    if k in need_names:
        try: c = int(line[i + 1:].strip(":"))
        except Exception: continue
        if c not in nameC.setdefault(k, []) and len(nameC[k]) < 6: nameC[k].append(c)
evc = {}
def events(cik):
    if cik in evc: return evc[cik]
    j = sec(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"); time.sleep(0.12); pages = []
    if j:
        pages.append(j["filings"]["recent"])
        for f in j["filings"].get("files", []):
            if (f.get("filingTo") or "9999") < "2004-07-01" or (f.get("filingFrom") or "0000") > "2016-03-01": continue
            x = sec("https://data.sec.gov/submissions/" + f["name"]); time.sleep(0.12)
            if x: pages.append(x)
    ev = []
    for r in pages:
        for i, form in enumerate(r.get("form", [])):
            if form != "8-K" or not re.search(r"(^|,)\s*2\.02\s*(,|$)", (r.get("items") or [""] * 99)[i] or ""): continue
            fd = r["filingDate"][i]
            if fd < "2004-08-01" or fd > "2016-03-01": continue
            a = (r.get("acceptanceDateTime") or [""] * 99)[i] or ""; m = re.search(r"T(\d\d):(\d\d)", a)
            ev.append((a[:10] if m else fd, int(m.group(1)) * 60 + int(m.group(2)) if m else 999))
    evc[cik] = ev; return ev
cov = {"members": 0, "with_prices": 0, "with_events": 0, "missing": []}
signals = {}
def ridx(day, mins):
    lo = next((i for i, d in enumerate(D) if d >= day), None)
    if lo is None: return -1
    if D[lo] == day and mins >= 570: lo += 1
    return lo if lo < N else -1
for _, m in mem.iterrows():
    t = m.ticker; cov["members"] += 1; base = t.split("-")[0]
    if t not in Craw.columns or Craw[t].notna().sum() < 20: cov["missing"].append(f"{t} no prices"); continue
    cov["with_prices"] += 1
    s0, e0 = str(max(m.start, pd.Timestamp(START)).date()), str((m.end if pd.notna(m.end) else pd.Timestamp(END)).date())
    cands = []
    if t in ciks: cands.append(ciks[t])
    for k in [base, base.replace(".", "-")]:
        if k in byT and byT[k] not in cands: cands.append(byT[k])
    for c in nameC.get(norm(names.get(t, "")), []):
        if c not in cands: cands.append(c)
    best, bn = None, 0
    for c in cands[:6]:
        ev = events(c); n = sum(1 for d, _ in ev if s0 <= d < e0)
        if n > bn: best, bn = c, n
    if not best or bn < 2: cov["missing"].append(f"{t} {names.get(t, '')[:30]} no events ({len(cands)} ciks)"); continue
    cov["with_events"] += 1; seen = set()
    for d, mi in evc[best]:
        if not (s0 <= d < e0): continue
        k = ridx(d, mi)
        if k < 1 or k + 1 >= N or k in seen: continue
        seen.add(k)
        c0, c1, s1, s2 = Craw[t].iat[k], Craw[t].iat[k - 1], C["SPY"].iat[k], C["SPY"].iat[k - 1]
        if not (c0 > 0 and c1 > 0): continue
        r = c0 / c1 - 1 - (s1 / s2 - 1)
        if r >= 0.03: signals.setdefault(k + 1, []).append((r, t))
for k in signals: signals[k].sort(reverse=True)
cov["signals"] = sum(len(v) for v in signals.values()); cov["missing"] = cov["missing"][:60]; LOG["coverage"] = cov
Oa, Ca = {t: O[t].to_numpy() for t in O.columns}, {t: C[t].to_numpy() for t in C.columns}; spy = Ca["SPY"]
t0 = next(i for i, d in enumerate(D) if d >= START); tEnd = max(i for i, d in enumerate(D) if d <= END)
COST = 0.0005
def sim(th, h, n=10, rate=0.0, park=False, sig=None):
    sig = sig if sig is not None else signals
    cash, pos, pk, pkb, yg, carry, curve = 1.0, [], 0.0, 0.0, 0.0, 0.0, []
    def sellpk(amt, t):
        nonlocal pk, pkb, cash, yg
        if pk <= 0: return
        sh = min(pk, amt / spy[t]); fr = sh / pk; pr = sh * spy[t]; yg += pr - pkb * fr; pkb -= pkb * fr; pk -= sh; cash += pr
    def tax(t):
        nonlocal yg, carry, cash
        g = yg - carry
        if g > 0:
            tx = g * rate
            if cash < tx: sellpk(tx - cash + 1e-12, t)
            cash -= tx; carry = 0
        else: carry = -g
        yg = 0
    for t in range(t0, tEnd + 1):
        if t > t0 and D[t][:4] != D[t - 1][:4]: tax(t - 1)
        eq = cash + pk * spy[t] + sum(p[2] * p[4] for p in pos)
        for r, s in sig.get(t, []):
            if r < th: break
            if len(pos) >= n: break
            if any(p[0] == s for p in pos): continue
            o = Oa.get(s, [None] * N)[t]
            if not (o and o > 0): continue
            want = eq / n
            if cash < want and park: sellpk(want - cash, t)
            al = min(want, cash)
            if al <= 1e-9: break
            cash -= al; pos.append([s, al, al * (1 - COST) / o, t + h - 1, o])
        for p in pos:
            c = Ca[p[0]][t]
            if c == c and c > 0: p[4] = c
        keep = []
        for p in pos:
            if t < p[3] and t < tEnd: keep.append(p); continue
            v = p[2] * p[4] * (1 - COST); cash += v; yg += v - p[1]
        pos = keep
        if park and cash > 1e-9: pk += cash / spy[t]; pkb += cash; cash = 0
        curve.append(cash + pk * spy[t] + sum(p[2] * p[4] for p in pos))
    if rate:
        for p in pos: v = p[2] * p[4] * (1 - COST); cash += v; yg += v - p[1]
        if pk: sellpk(pk * spy[tEnd], tEnd)
        tax(tEnd); curve[-1] = cash
    return np.array(curve)
def st(cv, a=START, b=END):
    i0 = next(i for i, d in enumerate(D[t0:tEnd + 1]) if d >= a); i1 = max(i for i, d in enumerate(D[t0:tEnd + 1]) if d <= b)
    yrs = (pd.Timestamp(D[t0 + i1]) - pd.Timestamp(D[t0 + i0])).days / 365.25; seg = cv[i0:i1 + 1]
    return {"cagr": round(((seg[-1] / seg[0]) ** (1 / yrs) - 1) * 100, 1), "dd": round(float((seg / np.maximum.accumulate(seg) - 1).min()) * 100, 1)}
P = [("p2004_07", "2004-08-01", "2007-12-31"), ("p2008_09", "2008-01-01", "2009-12-31"), ("p2010_15", "2010-01-01", "2015-12-31")]
spyc = spy[t0:tEnd + 1] / spy[t0]
res = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "Johnbrick123/sp500-data snapshot-2026-11 + SEC 8-K 2.02", "window": [START, END], "log": LOG,
       "spy": {"all": st(spyc), **{k: st(spyc, a, b)["cagr"] for k, a, b in P}}, "rows": []}
curves = []
for th in [0.04, 0.05, 0.06]:
    for h in [50, 60, 70]:
        cv = sim(th, h); curves.append(cv)
        row = {"thr": int(th * 100), "hold": h, "all": st(cv), **{k: st(cv, a, b)["cagr"] for k, a, b in P}}
        row["beatsEveryPeriod"] = all(row[k] > res["spy"][k] for k, _, _ in P); res["rows"].append(row); print(row, flush=True)
bl = np.mean(curves, axis=0); res["blend"] = {"all": st(bl), **{k: st(bl, a, b)["cagr"] for k, a, b in P}}
res["blend"]["beatsEveryPeriod"] = all(res["blend"][k] > res["spy"][k] for k, _, _ in P)
yrs = (pd.Timestamp(D[tEnd]) - pd.Timestamp(D[t0])).days / 365.25
spyAT = round(((1 + (spy[tEnd] / spy[t0] - 1) * 0.85) ** (1 / yrs) - 1) * 100, 1)
res["afterTaxBlendPark"] = {}
for rate in [0, 0.12, 0.24]:
    fin = np.mean([sim(th, h, rate=rate, park=True)[-1] for th in [0.04, 0.05, 0.06] for h in [50, 60, 70]])
    res["afterTaxBlendPark"][str(int(rate * 100))] = {"blend": round((fin ** (1 / yrs) - 1) * 100, 1), "spy": spyAT if rate else res["spy"]["all"]["cagr"]}
# random picks for the 5%/60 rule: same signal days/counts, random point-in-time member
random.seed(11); memb = [(r.ticker, max(r.start, pd.Timestamp(START)), r.end if pd.notna(r.end) else pd.Timestamp("2100-01-01")) for r in mem.itertuples() if r.ticker in Ca]
actual = st(sim(0.05, 60))["cagr"]; rnd = []
dayMembers = {}
for k in signals:
    d = pd.Timestamp(D[k]); dayMembers[k] = [t for t, a, b in memb if a <= d < b]
for _ in range(300):
    sg = {k: [(r, random.choice(dayMembers[k])) for r, _ in v] for k, v in signals.items() if dayMembers[k]}
    rnd.append(st(sim(0.05, 60, sig=sg))["cagr"])
res["random"] = {"actual_5_60": actual, "runs": len(rnd), "beats_pct": round(sum(actual > x for x in rnd) / len(rnd) * 100, 1), "median": float(np.median(rnd)), "p95": float(np.percentile(rnd, 95))}
os.makedirs("data", exist_ok=True); json.dump(res, open("data/earnings_drift_2004_2015.json", "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in res.items() if k not in ("rows", "log")}, default=str)); print(json.dumps({k: v for k, v in LOG.items() if k != "coverage"}), json.dumps({k: v for k, v in LOG["coverage"].items() if k != "missing"}))
