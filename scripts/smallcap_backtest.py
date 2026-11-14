"""Does the "quality at a fair price" screener rule work on mid, small and micro caps too?
Universe: every SEC filer with a ticker in today's SEC ticker file and Alpaca price history (2016+), sized each May
by diluted shares x price. WARNING: companies that went bust or were acquired and lost their ticker are missing
(survivorship bias). To keep the comparison fair the main benchmark is "all liquid stocks in the same size group,
equal weight", which has the same blind spot; IWM / IJR (real index funds that did hold the losers) are shown too.
Each May: score with last calendar year's SEC numbers, buy top N equal weight, hold 12 months. 0.30% cost per side.
Not financial advice."""
import os, sys, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
UA = os.environ.get("SEC_USER_AGENT") or "sentinel-research bot"
H = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
OUT = "data/smallcap_backtest.json"
def get(url, headers):
    for i in range(6):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120))
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(min(60, 5 * (i + 1)) if e.code == 429 else 3 * (i + 1))
        except Exception: time.sleep(3 * (i + 1))
    return None
def sec(url): time.sleep(0.12); return get(url, {"User-Agent": UA})
FR = lambda tag, unit, per: f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/{unit}/{per}.json"
def frame(tags, per, unit="USD"):
    m = {}
    for tag in tags:
        for d in (sec(FR(tag, unit, per)) or {}).get("data", []): m.setdefault(d["cik"], d["val"])
    return m
REV_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]
F = {}
for y in range(2012, 2026):
    F[y] = {"ni": frame(["NetIncomeLoss"], f"CY{y}"), "rev": frame(REV_TAGS, f"CY{y}"),
            "ocf": frame(["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], f"CY{y}"),
            "capex": frame(["PaymentsToAcquirePropertyPlantAndEquipment"], f"CY{y}"),
            "eq": frame(["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], f"CY{y}Q4I"),
            "debt": frame(["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"], f"CY{y}Q4I"),
            "sh": frame(["WeightedAverageNumberOfDilutedSharesOutstanding"], f"CY{y}", unit="shares")}
    print("frames", y, {k: len(v) for k, v in F[y].items()}, flush=True)
tk = sec("https://www.sec.gov/files/company_tickers.json")
cik_of = {}
for r in tk.values():
    t = r["ticker"].upper()
    if "-" in t and t.split("-")[-1] in ("WT", "WS", "U", "R"): continue
    cik_of.setdefault(t, r["cik_str"])
# only tickers that have SEC numbers in some year (skips funds etc.)
have = set().union(*[set(F[y]["ni"]) for y in F])
syms = sorted([t for t, c in cik_of.items() if c in have and t.isascii()]) + ["SPY", "IWM", "IJR", "MDY"]
print("symbols", len(syms), flush=True)
def bars(adj):
    C, Vv = {}, {}
    for i in range(0, len(syms), 100):
        p = {"symbols": ",".join(syms[i:i + 100]), "timeframe": "1Day", "start": "2016-10-01", "end": "2026-11-13", "adjustment": adj, "feed": "sip", "limit": "10000"}
        while True:
            js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p), H) or {}
            for s, bl in (js.get("bars") or {}).items():
                for b in bl: C.setdefault(s, {})[b["t"][:10]] = b["c"]; Vv.setdefault(s, {})[b["t"][:10]] = b["v"]
            if not js.get("next_page_token"): break
            p["page_token"] = js["next_page_token"]
        if i % 1000 == 0: print(adj, i, len(C), flush=True)
    return pd.DataFrame(C), pd.DataFrame(Vv)
A, VOL = bars("all"); RAW, _ = bars("raw")
A.index = pd.to_datetime(A.index); RAW.index = pd.to_datetime(RAW.index); VOL.index = pd.to_datetime(VOL.index)
A = A.sort_index(); RAW = RAW.reindex(A.index).sort_index(); VOL = VOL.reindex(A.index).sort_index()
dates = A.index; D = len(dates); Af = A.ffill(); Rf = RAW.ffill()
lastv = {s: (np.where(A[s].notna().values)[0][-1] if A[s].notna().any() else D - 1) for s in A.columns}
DV = (RAW * VOL).rolling(20, min_periods=10).mean()
BUCKETS = [("Large+", 10e9, 1e18), ("Mid", 2e9, 10e9), ("Small", 300e6, 2e9), ("Micro", 50e6, 300e6)]
forms = [int(np.searchsorted(dates.values, np.datetime64(f"{y}-05-01"))) for y in range(2017, 2027)]
forms = [f for f in forms if f < D - 5] + [D - 1]
COST = 0.003
def table(t0, Y):
    f, f1, f3 = F[Y], F[Y - 1], F[Y - 3]
    dec = int(np.searchsorted(dates.values, np.datetime64(f"{Y}-12-31"), side="right")) - 1
    rows = []; seen = set()
    for s in A.columns:
        if s in ("SPY", "IWM", "IJR", "MDY"): continue
        c = cik_of.get(s)
        if not c or c in seen or c not in f["ni"] or c not in f["sh"]: continue
        if pd.isna(A[s].iloc[t0]) or pd.isna(Rf[s].iloc[dec]) or pd.isna(Af[s].iloc[dec]) or Af[s].iloc[dec] <= 0: continue
        dv = DV[s].iloc[t0]
        if not (dv >= 5e5) or Rf[s].iloc[t0] < 2: continue
        mcap = f["sh"][c] * Rf[s].iloc[dec] * Af[s].iloc[t0] / Af[s].iloc[dec]
        b = next((n for n, lo, hi in BUCKETS if lo <= mcap < hi), None)
        if not b: continue
        seen.add(c)
        ni, rev, eq = f["ni"][c], f["rev"].get(c), f["eq"].get(c)
        ocf, capex, debt = f["ocf"].get(c), f["capex"].get(c, 0.0), f["debt"].get(c, 0.0)
        ni1, rev1, rev3 = f1["ni"].get(c), f1["rev"].get(c), f3["rev"].get(c)
        g = lambda a, b_, n: (a / b_) ** (1 / n) - 1 if a and b_ and a > 0 and b_ > 0 else np.nan
        rows.append(dict(t=s, bucket=b, mcap=mcap, ni=ni, ni1=ni1, rev=rev, pe=mcap / ni if ni and ni > 0 else np.nan,
            roe=ni / eq if eq and eq > 0 else np.nan, de=debt / eq if eq and eq > 0 else np.nan, ocf=ocf if ocf is not None else np.nan,
            fcf=(ocf - capex) if ocf is not None else np.nan, margin=ni / rev if rev and rev > 0 else np.nan, sg1=g(rev, rev1, 1), sg3=g(rev, rev3, 3)))
    return pd.DataFrame(rows).set_index("t")
pr = lambda x: x.rank(pct=True)
def pick(s, N, demax=1.0, roe=0.12, pemax=40, sg3=0.05):
    q = s[(s.ni > 0) & (s.ni1 > 0) & (s.sg1 >= 0) & (s.sg3 >= sg3) & (s.roe >= roe) & (s.fcf > 0) & (s.ocf >= 0.8 * s.ni) & (s.de.fillna(0) <= demax) & (s.pe > 0) & (s.pe <= pemax)]
    if q.empty: return [], 0
    sc = ((pr(q.roe) + pr(q.margin) + pr(q.fcf / q.rev)) / 3 + (pr(1 / q.pe) + pr(q.fcf / q.mcap)) / 2) / 2
    return list(sc.sort_values(ascending=False).index[:N]), len(q)
CACHE = {}
def run(bucket, rule, N=15, **kw):
    eq = 1.0; curve = []; log = []
    for k in range(len(forms) - 1):
        t0, t1 = forms[k], forms[k + 1]; Y = dates[t0].year - 1
        if (Y, t0) not in CACHE: CACHE[(Y, t0)] = table(t0, Y)
        df = CACHE[(Y, t0)]; s = df[df.bucket == bucket]
        if rule in ("SPY", "IWM", "IJR", "MDY"): names, npass = [rule], None
        elif rule == "ew": names, npass = list(s.index), len(s)
        else: names, npass = pick(s, N, **kw)
        log.append({"year": int(dates[t0].year), "universe": len(s), "passed": npass, "picks": names[:N] if rule == "rule" else None})
        if not names: names = ["SPY"]
        w = 1 / len(names); eq *= 1 - COST
        base = {t: Af[t].iloc[t0] for t in names}
        for d in range(t0, t1 + 1):
            v = sum(w * Af[t].iloc[min(d, lastv[t])] / base[t] for t in names)
            curve.append((dates[d], eq * v))
        eq *= v * (1 - COST)
    c = pd.Series([x[1] for x in curve], index=[x[0] for x in curve]); c = c[~c.index.duplicated(keep="last")]
    return c, log
def stats(c):
    cg = lambda s: (s.iloc[-1] / s.iloc[0]) ** (365.25 / max((s.index[-1] - s.index[0]).days, 1)) - 1
    a, b = c[c.index <= "2021-05-03"], c[c.index >= "2021-05-03"]
    return {"cagr": round(cg(c) * 100, 1), "max_dd": round(float((c / c.cummax() - 1).min()) * 100, 1), "2017_2021": round(cg(a) * 100, 1), "2021_2026": round(cg(b) * 100, 1)}
R = {"period": f"{dates[forms[0]].date()} to {dates[forms[-1]].date()}, rebalanced each May", "warning": __doc__, "buckets": {}}
for etf in ["SPY", "IWM", "IJR", "MDY"]:
    c, _ = run("Small", etf); R[etf] = stats(c); print(etf, R[etf], flush=True)
for b, _, _ in BUCKETS:
    o = {}
    c, lg = run(b, "rule"); o["rule_top15"] = stats(c); o["log"] = lg
    c, _ = run(b, "ew"); o["all_equal_weight"] = stats(c)
    for name, kw in [("top10", {"N": 10}), ("top25", {"N": 25}), ("no_debt_rule", {"demax": 99}), ("roe10", {"roe": 0.10}), ("pe30", {"pemax": 30}), ("sales3y_0", {"sg3": 0.0})]:
        N = kw.pop("N", 15); c, _ = run(b, "rule", N, **kw); o[name] = stats(c)
    R["buckets"][b] = o
    print(b, {k: v for k, v in o.items() if k != "log"}, flush=True)
json.dump(R, open(OUT, "w"), indent=1, default=str)
