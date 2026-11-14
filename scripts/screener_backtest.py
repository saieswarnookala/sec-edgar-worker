"""Screener rules backtest: which "good company" rules would have picked stocks that beat the market?
Point-in-time S&P 500 incl. later-delisted stocks (Johnbrick123/sp500-data). Fundamentals: SEC XBRL frames.
Every year on the first trading day of May (last year's 10-K is out), score members with last calendar year's
numbers, buy the top N equal-weight, hold 12 months. 0.10% cost per side. Not financial advice.
Caveat: SEC ticker map is today's, so companies whose ticker disappeared can't be scored; the fair benchmark is
"equal weight of all scorable members" (same blind spot), shown beside SPY."""
import os, sys, json, time, urllib.request, re
import numpy as np, pandas as pd
UA = os.environ.get("SEC_USER_AGENT") or "sentinel-research bot"
OUT = sys.argv[1] if len(sys.argv) > 1 else "data/screener_backtest.json"
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
def sec(url):
    for i in range(5):
        try:
            time.sleep(0.12)
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120))
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(3 * (i + 1))
        except Exception: time.sleep(3 * (i + 1))
    return None
FR = lambda tax, tag, unit, per: f"https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{unit}/{per}.json"
def frame(tags, per, unit="USD", tax="us-gaap"):
    m = {}
    for tag in tags:
        for d in (sec(FR(tax, tag, unit, per)) or {}).get("data", []):
            m.setdefault(d["cik"], d["val"])
    return m
REV_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]
Y0, Y1 = 2009, 2025
F = {}
for y in range(Y0, Y1 + 1):
    F[y] = {"ni": frame(["NetIncomeLoss"], f"CY{y}"), "rev": frame(REV_TAGS, f"CY{y}"),
            "ocf": frame(["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], f"CY{y}"),
            "capex": frame(["PaymentsToAcquirePropertyPlantAndEquipment"], f"CY{y}"),
            "eq": frame(["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], f"CY{y}Q4I"),
            "debt": frame(["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"], f"CY{y}Q4I"),
            "sh": frame(["WeightedAverageNumberOfDilutedSharesOutstanding"], f"CY{y}", unit="shares")}
    print("frames", y, {k: len(v) for k, v in F[y].items()}, flush=True)
tick2cik = {r["ticker"].upper().replace(".", "-"): r["cik_str"] for r in sec("https://www.sec.gov/files/company_tickers.json").values()}

px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close"]); px["date"] = pd.to_datetime(px.date); px = px[px.date >= "2008-01-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); T = sorted(px.ticker.unique())
A = px.pivot_table(index="date", columns="ticker", values="adj_close").reindex(index=dates, columns=T)
Rw = px.pivot_table(index="date", columns="ticker", values="close").reindex(index=dates, columns=T); del px
V = A.notna(); Af = A.ffill(); Rf = Rw.ffill()
tick = [t for t in T if t != "SPY"]; D = len(dates)
lastv = {t: (np.where(V[t].values)[0][-1] if V[t].any() else D - 1) for t in tick}
def member(t, d):
    m = mem[mem.ticker == t]
    return ((m.start <= d) & (m.end.isna() | (m.end > d))).any()
memb = {t: mem[mem.ticker == t][["start", "end"]].values for t in tick}
def is_member(t, d):
    return any(s <= d and (pd.isna(e) or e > d) for s, e in memb[t])
ma200 = Af.rolling(200).mean()
COST = 0.001
forms = [int(np.searchsorted(dates.values, np.datetime64(f"{y}-05-01"))) for y in range(2013, 2027)]
forms = [f for f in forms if f < D - 5] + [D - 1]

def table(t0, Y):
    """Feature table for S&P members at formation day t0 using calendar-year Y fundamentals."""
    rows = []
    d0 = dates[t0]; dec = int(np.searchsorted(dates.values, np.datetime64(f"{Y}-12-31"), side="right")) - 1
    f, f1, f4 = F[Y], F.get(Y - 1, {}), F.get(Y - 3, {})
    for t in tick:
        if not is_member(t, d0) or not V[t].iloc[max(0, t0 - 5):t0 + 1].any(): continue
        cik = None if re.search(r"-\d{6}$", t) else tick2cik.get(t)
        r = {"t": t, "scorable": False}
        if cik and cik in f["ni"] and cik in f["sh"] and pd.notna(Rf[t].iloc[dec]):
            ni, rev, sh = f["ni"][cik], f["rev"].get(cik), f["sh"][cik]
            mcap = sh * Rf[t].iloc[dec] * (Af[t].iloc[t0] / Af[t].iloc[dec])
            eq, debt = f["eq"].get(cik), f["debt"].get(cik, 0.0)
            ocf, capex = f["ocf"].get(cik), f["capex"].get(cik, 0.0)
            ni1, rev1, rev4, ni4 = f1.get("ni", {}).get(cik), f1.get("rev", {}).get(cik), f4.get("rev", {}).get(cik), f4.get("ni", {}).get(cik)
            g = lambda a, b, n: (a / b) ** (1 / n) - 1 if a and b and a > 0 and b > 0 else np.nan
            r.update(scorable=mcap > 0, ni=ni, ni1=ni1, rev=rev, mcap=mcap, pe=mcap / ni if ni and ni > 0 else np.nan,
                     roe=ni / eq if eq and eq > 0 else np.nan, de=debt / eq if eq and eq > 0 else np.nan,
                     fcf=(ocf - capex) if ocf is not None else np.nan, ocf=ocf if ocf is not None else np.nan,
                     margin=ni / rev if rev and rev > 0 else np.nan, sg1=g(rev, rev1, 1), sg3=g(rev, rev4, 3), pg1=g(ni, ni1, 1), pg3=g(ni, ni4, 3))
        a0, a1, a2 = Af[t].iloc[t0], Af[t].iloc[max(0, t0 - 21)], Af[t].iloc[max(0, t0 - 252)]
        r["mom"] = a1 / a2 - 1 if a2 and a2 > 0 else np.nan
        r["trend"] = bool(a0 > ma200[t].iloc[t0]) if pd.notna(ma200[t].iloc[t0]) else False
        rows.append(r)
    return pd.DataFrame(rows).set_index("t")

pr = lambda s: s.rank(pct=True)
def pick(df, rule, N):
    s = df[df.scorable]
    if rule == "old_high_pe":
        q = s[(s.ni > 0) & (s.ni1 > 0) & (s.sg1 >= 0.05) & (s.pg1 > 0) & (s.margin >= 0.03) & (s.pe <= 200)]
        return list(q.sort_values("pe", ascending=False).index[:N])
    gate = (s.ni > 0) & (s.ni1 > 0) & (s.sg1 >= 0) & (s.sg3 >= 0.05) & (s.roe >= 0.12) & (s.fcf > 0) & (s.ocf >= 0.8 * s.ni) & (s.de.fillna(0) <= 1.0) & (s.pe > 0) & (s.pe <= 40)
    q = s[gate] if not rule.startswith("score_only") else s[(s.ni > 0)]
    if "trend" in rule: q = q[q.trend]
    fy = q.fcf / q.mcap; ey = 1 / q.pe
    parts = {"quality": [pr(q.roe), pr(q.margin), pr(q.fcf / q.rev.where(q.rev > 0))],
             "value": [pr(ey), pr(fy)], "growth": [pr(q.sg3), pr(q.pg3.fillna(q.pg3.min()))], "mom": [pr(q.mom)]}
    use = {"gate_quality": ["quality"], "gate_qv": ["quality", "value"], "gate_qvg": ["quality", "value", "growth"],
           "gate_qvgm": ["quality", "value", "growth", "mom"], "gate_qvgm_trend": ["quality", "value", "growth", "mom"],
           "gate_qvg_trend": ["quality", "value", "growth"], "score_only_qvgm": ["quality", "value", "growth", "mom"]}[rule]
    # each family weighs the same, whatever its number of parts
    sc = sum(sum(p.fillna(0.5) for p in parts[k]) / len(parts[k]) for k in use) / len(use)
    return list(sc.sort_values(ascending=False).index[:N])

def run(rule, N=15, trend_cash=False):
    eq = 1.0; curve = []; picks_log = []
    for k in range(len(forms) - 1):
        t0, t1 = forms[k], forms[k + 1]; Y = dates[t0].year - 1
        df = table(t0, Y) if (Y, t0) not in CACHE else CACHE[(Y, t0)]; CACHE[(Y, t0)] = df
        if rule == "spy": names = ["SPY"]
        elif rule == "ew_scorable": names = list(df[df.scorable].index)
        elif rule == "ew_all": names = list(df.index)
        else: names = pick(df, rule, N)
        picks_log.append({"year": int(dates[t0].year), "n": len(names), "picks": names[:N] if rule not in ("ew_all", "ew_scorable") else None})
        if not names: names = ["SPY"]
        w = 1 / len(names); eq *= 1 - COST
        base = {t: Af[t].iloc[t0] for t in names}
        for d in range(t0, t1 + 1):
            v = sum(w * Af[t].iloc[min(d, lastv.get(t, D - 1))] / base[t] for t in names)
            curve.append((dates[d], eq * v))
        eq *= v * (1 - COST)
    c = pd.Series([x[1] for x in curve], index=[x[0] for x in curve]); c = c[~c.index.duplicated(keep="last")]
    return c, picks_log
CACHE = {}
def stats(c):
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    mid = c[c.index <= "2019-05-01"]; late = c[c.index >= "2019-05-01"]
    cg = lambda s: (s.iloc[-1] / s.iloc[0]) ** (365.25 / max((s.index[-1] - s.index[0]).days, 1)) - 1
    yr = c.resample("YE").last().pct_change().dropna()
    return {"cagr": round(cg(c) * 100, 1), "max_dd": round(float((c / c.cummax() - 1).min()) * 100, 1),
            "2013_2019": round(cg(mid) * 100, 1), "2019_2026": round(cg(late) * 100, 1), "worst_year": round(float(yr.min()) * 100, 1)}
R = {"period": "May 2013 to Oct 2026, rebalanced each May", "results": {}, "picks": {}}
for rule in ["spy", "ew_all", "ew_scorable", "old_high_pe", "gate_quality", "gate_qv", "gate_qvg", "gate_qvgm", "gate_qvg_trend", "gate_qvgm_trend", "score_only_qvgm"]:
    c, lg = run(rule); R["results"][rule] = stats(c); R["picks"][rule] = lg; print(rule, R["results"][rule], flush=True)
R["robust_N"] = {}
for rule in ["gate_qvg", "gate_qvgm", "gate_qvgm_trend"]:
    for N in (10, 25):
        c, _ = run(rule, N); R["robust_N"][f"{rule}_top{N}"] = stats(c); print(rule, N, R["robust_N"][f"{rule}_top{N}"], flush=True)
R["gate_pass_counts"] = {str(dates[f].year): int(len(pick(CACHE[(dates[f].year - 1, f)], "gate_qvgm", 999))) for f in forms[:-1]}
json.dump(R, open(OUT, "w"), indent=1, default=str)
