"""Volatile-stock bounce: every scenario in one run (Nov 14, 2026). Research only, not financial advice.
Question: after a big drop in a volatile stock, does buying and holding at most 3 days beat buying on a random day?
UNIVERSE=sp500 (default): point-in-time S&P 500 members 2004-2026 incl. companies that later failed/left (no hindsight),
  'volatile' = top 10% / 20% of members by 60-day volatility that day. Train 2004-2015, test 2016-2026.
UNIVERSE=popular: ~45 well-known volatile stocks, Alpaca daily 2016-2026 (HINDSIGHT BIAS: picked today). Train 2016-2022, test 2023-2026.
Scenario grid (~12k versions): trigger (1-day drop, drop vs SPY, 2-day drop, gap down at the open; several sizes) x universe
x volume (any / quiet < 2x normal / heavy >= 2x) x trend (any / above 200-day avg) x earnings (any / skip / only earnings drops,
SEC 8-K 2.02) x market (any / SPY above 100-day avg) x entry (that day's close / next open) x exit (close of day 1/2/3, or
'smart': first close back above the 5-day average, max 3 days).
Every trade is measured against the average member stock bought at the same time and held the same way that day
(excess = skill, not the market or the stock's drift). Cost 0.05% per side (stress 0.15%).
Top versions (picked on train only) also get a money simulation: 10 slots x 10%, idle cash earns nothing."""
import os, json, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

U = os.environ.get("UNIVERSE", "sp500")
OUT = f"data/volatile_bounce_{U}.json"
COST, STRESS = 0.0005, 0.0015
NY = ZoneInfo("America/New_York")

def fetch(url, dest):
    for i in range(6):
        try: urllib.request.urlretrieve(url, dest); return
        except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
    raise RuntimeError("download failed " + url)

def react_idx(dates, evs):
    """trading-day index of the price reaction: release before 9:30 ET -> same day, else next day"""
    out = []
    for d, mi in evs:
        k = int(np.searchsorted(dates, np.datetime64(d)))
        if k < len(dates) and dates[k] == np.datetime64(d) and mi >= 570: k += 1
        if k < len(dates): out.append(k)
    return out

# ---------------- data ----------------
if U == "sp500":
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f): fetch(REL + f, "/tmp/" + f)
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close", "volume"])
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "2002-06-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]; px["aopen"] = px.open * px.adj_close / px.close
    dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
    P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
    Cdf, Odf, Vdf = P("adj_close"), P("aopen"), P("volume"); del px
    tick = [t for t in ALLT if t != "SPY"]
    M = pd.DataFrame(False, index=dates, columns=tick)
    for _, m in mem.iterrows():
        if m.ticker in M.columns:
            e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
            M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
    SPYC = Cdf["SPY"].ffill().values
    C, O, V, MEM = Cdf[tick].values, Odf[tick].values, Vdf[tick].values, M.values
    ev = json.load(open("data/sec_events_sic.json"))["tickers"]
    EVS = {t: [(d, mi) for d, mi, *_ in ev.get(t, {}).get("events", [])] for t in tick}
    START, SPLIT = "2004-01-01", "2016-01-01"
else:
    LIST = ("NVDA TSLA AMD COIN PLTR MU SMCI MRNA ROKU SNAP PTON ZM SHOP NFLX META UBER LYFT DKNG RIOT MARA AFRM UPST CVNA "
            "ENPH PLUG NIO FSLR W ETSY TWLO DOCU CRWD MSTR SQ XYZ BABA SE NET SNOW RBLX HOOD SOFI LCID RIVN CHWY BYND").split()
    H = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
    def get(url, headers):
        for i in range(6):
            try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120))
            except urllib.error.HTTPError as e:
                if e.code in (400, 403, 404, 422): print("HTTP", e.code, e.read()[:300], flush=True); return None
                time.sleep(5 * (i + 1))
            except Exception: time.sleep(3 * (i + 1))
        return None
    rows = {}
    for s in LIST + ["SPY"]:
        p = {"symbols": s, "timeframe": "1Day", "start": "2015-01-01", "end": (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), "adjustment": "all", "feed": "sip", "limit": "10000"}
        while True:
            js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p), H) or {}
            if not js: print("no data", s, flush=True)
            for b in (js.get("bars") or {}).get(s, []): rows.setdefault(s, {})[b["t"][:10]] = (b["o"], b["c"], b["v"])
            if not js.get("next_page_token"): break
            p["page_token"] = js["next_page_token"]
    dates = pd.DatetimeIndex(sorted(rows["SPY"])); tick = [s for s in LIST if s in rows]
    ds = [d.strftime("%Y-%m-%d") for d in dates]
    arr = lambda s, k: np.array([rows[s].get(d, (np.nan,) * 3)[k] for d in ds], float)
    O = np.stack([arr(s, 0) for s in tick], 1); C = np.stack([arr(s, 1) for s in tick], 1); V = np.stack([arr(s, 2) for s in tick], 1)
    SPYC = pd.Series(arr("SPY", 1)).ffill().values; MEM = ~np.isnan(C)
    UA = os.environ.get("SEC_USER_AGENT") or "sentinel-research bot"
    def sec(url):
        time.sleep(0.15)
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60))
        except Exception: return None
    cik = {v["ticker"].upper(): v["cik_str"] for v in (sec("https://www.sec.gov/files/company_tickers.json") or {}).values()}
    EVS = {}
    for t in tick:
        c = cik.get(t); evs = []
        j = sec(f"https://data.sec.gov/submissions/CIK{c:010d}.json") if c else None
        pages = [j["filings"]["recent"]] if j else []
        for f in (j or {}).get("filings", {}).get("files", []):
            if (f.get("filingTo") or "9999") >= "2015-01-01": pages.append(sec("https://data.sec.gov/submissions/" + f["name"]) or {})
        for r in pages:
            for i, form in enumerate(r.get("form", [])):
                if form.startswith("8-K") and "2.02" in (r.get("items", [""] * (i + 1))[i] or ""):
                    a = datetime.fromisoformat(r["acceptanceDateTime"].replace("Z", "+00:00")).astimezone(NY)
                    evs.append((a.strftime("%Y-%m-%d"), a.hour * 60 + a.minute))
        EVS[t] = evs
    print("earnings events", sum(len(v) for v in EVS.values()), flush=True)
    START, SPLIT = "2016-01-01", "2023-01-01"
D, N = C.shape; dn = dates.values
print(U, "days", D, "stocks", N, dates[0].date(), dates[-1].date(), flush=True)

# ---------------- features (known at the signal time) ----------------
with np.errstate(all="ignore"):
    Cf = pd.DataFrame(C).ffill().values
    r = np.vstack([np.full(N, np.nan), C[1:] / C[:-1] - 1])
    spyr = np.r_[np.nan, SPYC[1:] / SPYC[:-1] - 1]
    vol60 = pd.DataFrame(r).rolling(60, min_periods=40).std().values
    rank = pd.DataFrame(np.where(MEM, vol60, np.nan)).rank(axis=1, pct=True).values
    vratio = V / pd.DataFrame(V).shift(1).rolling(50, min_periods=30).mean().values
    ma200 = pd.DataFrame(C).rolling(200, min_periods=150).mean().values
    ma5 = pd.DataFrame(C).rolling(5).mean().values
    spy100 = pd.Series(SPYC).rolling(100).mean().values
    r2 = np.vstack([np.full((2, N), np.nan), C[2:] / C[:-2] - 1])
    gap = np.vstack([np.full(N, np.nan), O[1:] / C[:-1] - 1])
EARN = np.zeros((D, N), bool)
for j, t in enumerate(tick):
    for k in react_idx(dn, EVS.get(t, [])): EARN[k, j] = True
ok = MEM.copy()
for k in range(1, 5): ok[:-k] &= ~np.isnan(C[k:]) & ~np.isnan(O[k:])
ok[-4:] = False

# ---------------- returns matrices: entry x exit ----------------
def smart_exit(first=1, last_=3):
    """exit at the first close on day t+first..t+last_ back above the 5-day average, else the close of day t+last_"""
    out = np.full((D, N), np.nan)
    done = np.zeros((D, N), bool)
    for j in range(first, last_ + 1):
        sh = j
        cj = np.vstack([C[sh:], np.full((sh, N), np.nan)]); mj = np.vstack([ma5[sh:], np.full((sh, N), np.nan)])
        hit = (~done) & ((cj > mj) | (j == last_))
        out[hit] = cj[hit]; done |= hit
    return out
shift = lambda X, k: np.vstack([X[k:], np.full((k, N), np.nan)])
with np.errstate(all="ignore"):
    R = {}
    # close-signal day t: entry 'close' at C[t], entry 'open' at O[t+1]; exit 'k' = close of the k-th day after t
    for k in (1, 2, 3):
        R[("close", str(k))] = shift(C, k) / C - 1
        R[("open", str(k))] = shift(C, k) / shift(O, 1) - 1
    sm = smart_exit(1, 3)
    R[("close", "smart")] = sm / C - 1; R[("open", "smart")] = sm / shift(O, 1) - 1
    # gap at the open of day t: entry O[t], exit close of day t+k-1
    for k in (1, 2, 3): R[("gap", str(k))] = shift(C, k - 1) / O - 1
    R[("gap", "smart")] = smart_exit(0, 2) / O - 1
BASE = {key: np.array([np.nanmean(m[i][ok[i]]) if ok[i].any() else np.nan for i in range(D)]) for key, m in R.items()}

# ---------------- event table ----------------
period = np.where(dn < np.datetime64(START), -1, np.where(dn < np.datetime64(SPLIT), 0, 1))
mkt = SPYC > spy100
cand = ok & (period[:, None] >= 0) & ((r <= -0.03) | (r - spyr[:, None] <= -0.03) | (r2 <= -0.05) | (gap <= -0.03))
I, J = np.nonzero(cand)
print("candidate events", len(I), flush=True)
prev = np.maximum(I - 1, 0)
E = pd.DataFrame({"i": I, "j": J, "per": period[I], "r1": r[I, J], "rel": r[I, J] - spyr[I], "r2": r2[I, J], "gap": gap[I, J],
                  "rank": rank[I, J], "rank_prev": rank[prev, J], "vr": vratio[I, J], "vr_prev": vratio[prev, J],
                  "up": C[I, J] > ma200[I, J], "up_prev": C[prev, J] > ma200[prev, J], "earn": EARN[I, J] | EARN[prev, J], "earn_today": EARN[I, J],
                  "mkt": mkt[I], "mkt_prev": mkt[prev]})
for key, m in R.items():
    E["R_" + "_".join(key)] = m[I, J]; E["B_" + "_".join(key)] = BASE[key][I]

TRIG = [("1-day drop", x) for x in (0.03, 0.05, 0.07, 0.10)] + [("drop vs SPY", x) for x in (0.03, 0.05, 0.07, 0.10)] + \
       [("2-day drop", x) for x in (0.05, 0.08, 0.12)] + [("gap down at open", x) for x in (0.03, 0.05, 0.07)]
UNIV = [("top 10% most volatile", 0.9), ("top 20% most volatile", 0.8), ("all", 0.0)] if U == "sp500" else [("all", 0.0)]
results = []
for tn, x in TRIG:
    g = tn.startswith("gap")
    base = {"1-day drop": E.r1 <= -x, "drop vs SPY": E.rel <= -x, "2-day drop": E.r2 <= -x, "gap down at open": E.gap <= -x}[tn].values
    rk, vr, up, mk = (E.rank_prev, E.vr_prev, E.up_prev, E.mkt_prev) if g else (E["rank"], E.vr, E.up, E.mkt)
    earn = (E.earn_today if g else E.earn).values
    for un, uq in UNIV:
        m0 = base & (rk.values >= uq)
        for vn, vm in (("any volume", None), ("quiet (<2x volume)", vr.values < 2), ("heavy (>=2x volume)", vr.values >= 2)):
            m1 = m0 if vm is None else m0 & vm
            for trn, trm in (("any trend", None), ("above 200-day avg", up.values)):
                m2 = m1 if trm is None else m1 & trm
                for en, em in (("any", None), ("skip earnings drops", ~earn), ("only earnings drops", earn)):
                    m3 = m2 if em is None else m2 & em
                    for mn, mm in (("any market", None), ("SPY above 100-day", mk.values)):
                        m4 = m3 if mm is None else m3 & mm
                        if m4.sum() < 30: continue
                        for entry in (("gap",) if g else ("close", "open")):
                            for ex in ("1", "2", "3", "smart"):
                                key = entry + "_" + ex
                                raw = E["R_" + key].values; bas = E["B_" + key].values
                                sel = m4 & ~np.isnan(raw)
                                row = {"trigger": f"{tn} {x * 100:g}%+", "universe": un, "volume": vn, "trend": trn, "earnings": en, "market": mn,
                                       "entry": {"gap": "at the open (gap day)", "close": "that day's close", "open": "next open"}[entry],
                                       "exit": "smart (back above 5-day avg, max 3 days)" if ex == "smart" else f"close of day {ex}", "key": key,
                                       "sortcol": {"1-day drop": "r1", "drop vs SPY": "rel", "2-day drop": "r2", "gap down at open": "gap"}[tn]}
                                for pn, pv in (("train", 0), ("test", 1)):
                                    s = sel & (E.per.values == pv); rr = raw[s] - 2 * COST; ex_ = rr - bas[s]
                                    yrs = max((period == pv).sum() / 252, 1e-9)
                                    if s.sum() < 2: row[pn] = {"trades": int(s.sum())}; continue
                                    row[pn] = {"trades": int(s.sum()), "per_year": round(float(s.sum() / yrs), 1), "avg_bps": round(float(rr.mean()) * 1e4, 1),
                                               "excess_bps": round(float(ex_.mean()) * 1e4, 1), "win_pct": round(float((rr > 0).mean()) * 100, 1),
                                               "t": round(float(ex_.mean() / (ex_.std(ddof=1) or 1e-9) * np.sqrt(s.sum())), 2),
                                               "stress_avg_bps": round(float((raw[s] - 2 * STRESS).mean()) * 1e4, 1)}
                                row["_mask"] = sel
                                results.append(row)
print("versions", len(results), flush=True)

# ---------------- scoring ----------------
okr = [x for x in results if x["train"].get("trades", 0) >= 100 and x["test"].get("trades", 0) >= 30]
okr.sort(key=lambda x: -x["train"]["t"])
tr_ex, te_ex = np.array([x["train"]["excess_bps"] for x in okr]), np.array([x["test"]["excess_bps"] for x in okr])
rk = lambda a: a.argsort().argsort()
summary = {"universe": U, "train": f"{START} to {SPLIT}", "test": f"{SPLIT} to {dates[-1].date()}", "versions": len(results), "scored": len(okr),
           "cost_per_side_pct": COST * 100, "train_t_over_2": int((np.array([x['train']['t'] for x in okr]) > 2).sum()),
           "expected_by_luck": round(len(okr) * 0.023, 1),
           "test_excess_positive_pct": round(float((te_ex > 0).mean()) * 100, 1),
           "rank_corr_train_test": round(float(np.corrcoef(rk(tr_ex), rk(te_ex))[0, 1]), 3),
           "top20_by_train_positive_in_test": int(sum(x["test"]["excess_bps"] > 0 for x in okr[:20])),
           "top20_by_train_t_over_2_in_test": int(sum(x["test"]["t"] > 2 for x in okr[:20]))}
# what each choice adds: median test excess across all versions with that choice
effects = {}
for dim in ("trigger", "universe", "volume", "trend", "earnings", "market", "entry", "exit"):
    effects[dim] = {}
    for v in sorted({x[dim] for x in okr}):
        a = [x for x in okr if x[dim] == v]
        effects[dim][v] = {"versions": len(a), "median_train_excess_bps": round(float(np.median([x["train"]["excess_bps"] for x in a])), 1),
                           "median_test_excess_bps": round(float(np.median([x["test"]["excess_bps"] for x in a])), 1),
                           "median_test_avg_bps": round(float(np.median([x["test"]["avg_bps"] for x in a])), 1),
                           "test_positive_pct": round(100 * float(np.mean([x["test"]["excess_bps"] > 0 for x in a])), 0)}
# the 1% club: >= 1% average per trade after costs in BOTH periods, at least 10 trades a year
club = [x for x in okr if x["train"]["avg_bps"] >= 100 and x["test"]["avg_bps"] >= 100 and x["test"].get("per_year", 0) >= 10]
club.sort(key=lambda x: -x["train"]["t"])

# ---------------- money simulation for the top versions (chosen on train) ----------------
def money(x, slots=10, size=0.10, park=False):
    m = x["_mask"]; ent = E.i.values + (0 if x["key"].startswith(("gap", "close")) else 1)
    hold = {"1": 1, "2": 2, "3": 3, "smart": 3}[x["key"].split("_")[1]]
    ex_day = E.i.values + (hold - 1 if x["key"].startswith("gap") else hold)
    tr = pd.DataFrame({"ent": ent[m], "exd": ex_day[m], "ret": E["R_" + x["key"]].values[m] - 2 * COST, "sz": E[x["sortcol"]].values[m], "j": E.j.values[m]}).dropna()
    tr = tr.sort_values(["ent", "sz"])  # biggest drops first
    open_, eq, curve, held_days, taken = [], 1.0, {}, 0, 0
    for d in range(D):
        if period[d] < 0: continue
        if park and d > 0 and spyr[d] == spyr[d]: eq *= 1 + (1 - size * len(open_)) * spyr[d]   # idle money sits in SPY
        for p in [p for p in open_ if p[0] <= d]: eq *= 1 + size * p[1]; open_.remove(p)
        for _, t in tr[tr.ent == d].iterrows():
            if len(open_) >= slots or any(q[2] == t.j for q in open_): continue
            open_.append((int(t.exd), t.ret, t.j)); taken += 1
        held_days += len(open_) > 0; curve[d] = eq
    cv = pd.Series(curve); out = {"trades_taken": taken}
    for pn, pv in (("train", 0), ("test", 1)):
        c = cv[[d for d in cv.index if period[d] == pv]]
        if len(c) < 20: continue
        c = c / c.iloc[0]; yrs = len(c) / 252
        spy = SPYC[c.index[-1]] / SPYC[c.index[0]]
        out[pn] = {"per_year_pct": round((c.iloc[-1] ** (1 / yrs) - 1) * 100, 1), "worst_drop_pct": round(float((c / c.cummax() - 1).min()) * 100, 1),
                   "spy_per_year_pct": round((spy ** (1 / yrs) - 1) * 100, 1)}
    out["days_with_a_position_pct"] = round(100 * held_days / max(1, (period >= 0).sum()), 1)
    return out
for x in okr[:10] + club[:10]: x["money_10x10pct"] = money(x); x["money_idle_in_spy"] = money(x, park=True)
clean = lambda xs: [{k: v for k, v in x.items() if k not in ("_mask", "sortcol")} for x in xs]
json.dump({"summary": summary, "top20_by_train": clean(okr[:20]), "one_pct_club": clean(club[:30]), "one_pct_club_count": len(club),
           "effects": effects, "best_in_test_hindsight": clean(sorted(okr, key=lambda x: -x["test"]["t"])[:10]),
           "all": clean(okr), "note": __doc__}, open(OUT, "w"), indent=1, default=float)
print(json.dumps(summary, indent=1))
for x in okr[:20]: print(x["train"]["t"], x["train"]["excess_bps"], "->", x["test"]["excess_bps"], x["test"]["t"], x["test"]["avg_bps"], "|", x["trigger"], x["universe"], x["volume"], x["trend"], x["earnings"], x["market"], x["entry"], x["exit"])
print("1% club", len(club))
