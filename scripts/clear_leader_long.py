# Clear leader v2.0 extended back to ~1998 using mutual-fund/index stand-ins before each ETF existed. Research only.
# Rules identical to scripts/clear-leader.mjs: monthly; rank by 12-month return; buy #1 if it leads #2 by >= 15 pts,
# has been #1 for 3 month-ends and beats T-bills; keep while #1 and lead >= 7.5 pts; else SPY. Cost 0.05%/side.
# Difference: assets enter the pool only once they (or a stand-in) have 12 months of history.
import json, os, time, urllib.request
import numpy as np
UA = {"User-Agent": "Mozilla/5.0"}
def yahoo(sym):
    for a in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1mo&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40))["chart"]["result"][0]
            ts = j["timestamp"]; q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            out = {}
            for t, v in zip(ts, adj):
                if v and v > 0: out[time.strftime("%Y-%m", time.gmtime(t + 86400 * 3))] = v
            return out
        except Exception as e: err = e; time.sleep(2 * (a + 1))
    print("yahoo fail", sym, err); return {}
import urllib.parse
ASSETS = {  # ETF: [stand-ins in order of preference, used only before the ETF has data]
    "SPY": ["^SP500TR", "VFINX"], "QQQ": ["^NDX"], "IWM": ["NAESX"], "EFA": ["VGTSX", "VTMGX"], "EEM": ["VEIEX"],
    "VNQ": ["VGSIX"], "TLT": ["VUSTX"], "IEF": ["VFITX"], "GLD": ["GC=F"], "DBC": ["^SPGSCI", "PCRIX"]}
raw, src = {}, {}
for etf, alts in ASSETS.items():
    for s in [etf] + alts:
        if s not in raw: raw[s] = yahoo(s); time.sleep(0.5)
irx = yahoo("^IRX")
months = sorted(set(m for s in raw.values() for m in s) | set(irx))
months = [m for m in months if "1990-01" <= m <= time.strftime("%Y-%m")][:-1]  # drop current partial month
def chain(etf):
    seq = [etf] + ASSETS[etf]; idx, used, lv = {}, {}, None
    for i, m in enumerate(months):
        if i == 0: continue
        p = months[i - 1]; r = None
        for s in seq:
            a = raw.get(s, {})
            if p in a and m in a: r = a[m] / a[p] - 1; used[m] = s; break
        if r is None: lv = None; continue
        lv = (lv or 1.0) * (1 + r); idx[m] = lv
    return idx, used
SER, USED = {}, {}
for e in ASSETS: SER[e], USED[e] = chain(e)
bil, lv = {}, 1.0
for i, m in enumerate(months):
    if i and months[i - 1] in irx: lv *= 1 + irx[months[i - 1]] / 100 / 12; bil[m] = lv
POOL = list(ASSETS); ENTRY, EXIT, STREAK, COST = 0.15, 0.075, 3, 0.0005
def run(start="1990-01", crash=False):
    ms = [m for m in months if m >= start and m in SER["SPY"] and m in bil]
    def r12(s, i):
        a, b = ms[i], ms[i - 12]; S = bil if s == "BIL" else SER[s]
        return S[a] / S[b] - 1 if a in S and b in S else None
    lead = prev = hold = None; streak = 0; eq = spy = 1.0; out = []; held = {}; trades = 0
    for i in range(12, len(ms) - 1):
        avail = [s for s in POOL if r12(s, i) is not None and ms[i + 1] in SER[s]]
        if len(avail) < 2: continue
        rk = sorted(avail, key=lambda s: -r12(s, i)); top = rk[0]; gap = r12(rk[0], i) - r12(rk[1], i)
        streak = streak + 1 if top == prev else 1; prev = top
        trig = gap >= ENTRY and streak >= STREAK and r12(top, i) > (r12("BIL", i) or 0)
        stay = lead is not None and top == lead and gap >= EXIT
        lead = lead if stay else (top if trig else None)
        if crash and lead is None:
            sma = np.mean([SER["SPY"][ms[k]] for k in range(i - 9, i + 1)]); pos = "IEF" if SER["SPY"][ms[i]] < sma else "SPY"
        else: pos = lead or "SPY"
        cost = (2 if hold else 1) * COST if pos != hold else 0
        if pos != hold: trades += 1
        r = SER[pos][ms[i + 1]] / SER[pos][ms[i]] - 1 - cost; s = SER["SPY"][ms[i + 1]] / SER["SPY"][ms[i]] - 1
        eq *= 1 + r; spy *= 1 + s; hold = pos; held[pos] = held.get(pos, 0) + 1
        out.append({"m": ms[i + 1], "r": r, "s": s, "pos": pos, "proxy": {k: USED[k].get(ms[i + 1]) for k in avail if USED[k].get(ms[i + 1]) != k}})
    return out, trades, held
def stats(rows, a="0", b="9"):
    x = [r for r in rows if a <= r["m"] < b]
    if not x: return None
    def one(k):
        e = pk = 1.0; dd = 0
        for r in x: e *= 1 + r[k]; pk = max(pk, e); dd = max(dd, 1 - e / pk)
        return {"cagr": round((e ** (12 / len(x)) - 1) * 100, 1), "maxDD": round(dd * 100, 1), "growth_of_10k": round(10000 * e)}
    return {"from": x[0]["m"], "to": x[-1]["m"], "months": len(x), "strategy": one("r"), "spy": one("s")}
res = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "note": "Stand-ins before ETF launch: SPY<-S&P500 TR/VFINX, QQQ<-Nasdaq-100 price index, IWM<-NAESX, EFA<-VGTSX/VTMGX, EEM<-VEIEX, VNQ<-VGSIX, TLT<-VUSTX, IEF<-VFITX, GLD<-gold futures, DBC<-S&P GSCI/PCRIX; T-bills from ^IRX. Assets join the pool once they have 12 months of data.",
       "first_month_with_data": {e: (min(SER[e]) if SER[e] else None) for e in ASSETS}, "variants": {}}
for name, crash in [("clear_leader", False), ("clear_leader_crash_filter", True)]:
    rows, trades, held = run(crash=crash)
    res["variants"][name] = {"trades": trades, "months_held": held, "full": stats(rows), "p1998_2002_dotcom": stats(rows, "1998", "2003"), "p2003_2007": stats(rows, "2003", "2008"),
        "p2008_2009": stats(rows, "2008", "2010"), "p2010_now": stats(rows, "2010"), "check_since_2008_07": stats(rows, "2008-07"),
        "years": [{"y": y, "strategy": round((np.prod([1 + r["r"] for r in rows if r["m"][:4] == y]) - 1) * 100, 1), "spy": round((np.prod([1 + r["s"] for r in rows if r["m"][:4] == y]) - 1) * 100, 1),
                   "held": sorted({r["pos"] for r in rows if r["m"][:4] == y})} for y in sorted({r["m"][:4] for r in rows})]}
    print(name, json.dumps({k: v for k, v in res["variants"][name].items() if k != "years"}))
os.makedirs("data", exist_ok=True); json.dump(res, open("data/clear_leader_long.json", "w"), indent=1)
print(json.dumps(res["first_month_with_data"]))
