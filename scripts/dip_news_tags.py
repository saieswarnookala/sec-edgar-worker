"""WHY did the stock dip? Tag every dip-bot signal by cause and compare how each kind bounced (Nov 25 2026 "brain" research). Research only.
Engine: scripts/stack_and_rebound.py, dip bot v3.0 (point-in-time S&P 500, volume filter on), live-like fills, 2016-2026.
Causes (no LLM; the labels an LLM 'brain' would produce, made with plain rules so they can be backtested honestly):
  - headlines (Alpaca / Benzinga news, 7 days before the 3:45 pm decision, articles naming <= 3 tickers):
    downgrade, price-target cut, guidance cut / warning, earnings miss, legal / probe, short-seller report, FDA / trial, exec exit, share offering
  - SEC 8-K item codes filed in the 5 days before (2.02 earnings, 5.02 exec change, other)
  - peers: same SEC industry (2-digit SIC) S&P members' median 5-day move (sector-wide dip vs stock alone); SPY's 5-day move
Output: per-tag trade stats (n, avg %, win %, t) for 2016-20 / 2021-26, and the full bot with a tag's dips skipped.
Raw headlines are NOT saved (licence); only counts and tags. DRY=1: fake data + fake news."""
import os, sys, json, re, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/dip_news_tags.json" if not S.DRY else "/tmp/dip_news_tags_dry.json"
dn, D, tick = S.dn, S.D, S.tick
START = int(np.searchsorted(dn, np.datetime64("2016-01-04")))
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003, etf=True, bond=True)
CATS = {"downgrade": r"downgrad|cut to (sell|underperform|underweight|neutral|hold|market perform|equal.weight)|lowered to (sell|underperform|underweight|neutral|hold)",
        "price target cut": r"(lowers|cuts|slashes|trims|reduces) (its )?(price target|pt)|price target (lowered|cut|reduced)|pt (lowered|cut)",
        "guidance cut / warning": r"(cuts|lowers|slashes|withdraws|reduces|trims) .{0,25}(guidance|outlook|forecast)|(guidance|outlook|forecast) .{0,15}(below|cut|lowered)|profit warning|warns",
        "earnings miss": r"\bmiss(es|ed)?\b|below (estimates|expectations|consensus)|falls short",
        "legal / probe": r"lawsuit|\bsued\b|\bsues\b|probe|investigat|subpoena|class action|antitrust|\bdoj\b|\bftc\b|sec (charges|charged)|fraud|indict",
        "short-seller report": r"short.seller|short report|hindenburg|muddy waters|citron|spruce point|grizzly|culper",
        "FDA / trial": r"\bfda\b|clinical (trial|hold)|complete response|\bcrl\b|phase (1|2|3|i|ii|iii)\b",
        "exec exit": r"(ceo|cfo|chief executive|chief financial).{0,40}(resign|step(s|ping)? down|depart|exit|ousted|fired|leav|retir)",
        "share offering": r"(public |secondary |stock |share )offering|prices .{0,20}offering|dilut"}
FIRM_BAD = [c for c in CATS]
# ---------------------------------------------------------------- signals + trades
log = []; curve0, _ = S.sim(log=log, **LIVE)
trades = [(j, a, r) for k, j, a, b, u, r in log if k == "S" and a >= START]
sig_tj = [(t, j) for t in range(START, D) for j in np.flatnonzero(S.SIG[t])]
print(f"{len(trades)} stock trades and {len(sig_tj)} stock signals since 2016", flush=True)
# ---------------------------------------------------------------- news
KEY, SEC = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
news_ok, news_err = True, None
def news(sym, day):
    if S.DRY:
        rng = np.random.default_rng(abs(hash((sym, str(day)))) % 2**32); k = int(rng.integers(0, 5))
        pool = ["Analyst downgrades %s to neutral", "%s cuts full-year guidance", "%s shares slide", "%s faces class action lawsuit", "%s misses estimates", "Market wrap"]
        hs = [pool[int(rng.integers(0, len(pool)))] for _ in range(k)]
        return [{"headline": h % sym if "%s" in h else h, "summary": "", "symbols": [sym]} for h in hs]
    d = pd.Timestamp(day); start = (d - pd.Timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z"); end = (d + pd.Timedelta(hours=19, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://data.alpaca.markets/v1beta1/news?" + urllib.parse.urlencode({"symbols": sym.replace("-", "."), "start": start, "end": end, "limit": 50, "sort": "desc"})
    for a in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC}), timeout=30) as r: return json.load(r).get("news", [])
        except urllib.error.HTTPError as e:
            if e.code in (401, 403): raise
            time.sleep(2 * (a + 1))
        except Exception: time.sleep(2 * (a + 1))
    return None
TAG = {}   # (t, j) -> dict
miss = 0
for i, (t, j) in enumerate(sig_tj):
    if not news_ok: break
    try: arts = news(tick[j], str(dn[t])[:10])
    except urllib.error.HTTPError as e: news_ok, news_err = False, f"HTTP {e.code}: {e.read()[:200]!r}"; print("NEWS BLOCKED", news_err, flush=True); break
    if arts is None: miss += 1; continue
    own = [a for a in arts if len(a.get("symbols") or []) <= 3]
    txt = [((a.get("headline") or "") + " " + (a.get("summary") or "")).lower() for a in own]
    TAG[(t, j)] = {"n_all": len(arts), "n_own": len(own), **{c: any(re.search(p, x) for x in txt) for c, p in CATS.items()}}
    if not S.DRY: time.sleep(0.32)
    if i % 300 == 0: print(i, "signals checked", flush=True)
print("news tagged:", len(TAG), "missing:", miss, flush=True)
# ---------------------------------------------------------------- 8-K + peers
ITEMS = json.load(open("data/sec_8k_items.json"))["tickers"] if os.path.exists("data/sec_8k_items.json") else {}
SIC = {t: (v.get("sic") or "")[:2] for t, v in json.load(open("data/sec_events_sic.json"))["tickers"].items()} if os.path.exists("data/sec_events_sic.json") else {}
dstr = np.array([str(x)[:10] for x in dn])
def k8(t, j):
    lo = dstr[max(t - 4, 0)]; hi = dstr[t]; its = set()
    for d, mins, it in ITEMS.get(tick[j], []):
        if lo <= d <= hi and not (d == hi and mins > 15 * 60 + 45): its |= set((it or "").split(","))
    return its
r5 = S_C5 = np.vstack([np.full((5, len(tick)), np.nan), S.S_C[5:] / S.S_C[:-5] - 1])
spy5 = (S.spy / S.spy.shift(5) - 1).values
grp = {}
for j, t_ in enumerate(tick): grp.setdefault(SIC.get(t_, ""), []).append(j)
def peer(t, j):
    g = [x for x in grp.get(SIC.get(tick[j], ""), []) if x != j and S.M.values[t, x] and np.isfinite(r5[t, x])]
    return float(np.median(r5[t, g])) if len(g) >= 3 else np.nan
def tags(t, j):
    x = dict(TAG.get((t, j), {})); its = k8(t, j); pm = peer(t, j)
    x["8-K earnings (2.02)"] = "2.02" in its; x["8-K exec change (5.02)"] = "5.02" in its; x["8-K other company news"] = bool(its - {"2.02", "9.01", "5.02", "5.07", ""})
    x["peers down 5%+ too (sector-wide)"] = bool(np.isfinite(pm) and pm <= -0.05); x["peers flat, stock alone (peers > -2%)"] = bool(np.isfinite(pm) and pm > -0.02)
    x["market down 3%+ (SPY 5-day)"] = bool(spy5[t] <= -0.03)
    if (t, j) in TAG:
        x["no headlines at all"] = TAG[(t, j)]["n_all"] == 0; x["4+ own headlines (lots of attention)"] = TAG[(t, j)]["n_own"] >= 4
        x["ANY firm-specific bad news"] = any(TAG[(t, j)][c] for c in FIRM_BAD)
        x["firm bad news AND peers flat"] = x["ANY firm-specific bad news"] and x["peers flat, stock alone (peers > -2%)"]
    return x
TT = {(t, j): tags(t, j) for t, j in set(sig_tj) | {(a, j) for j, a, _ in trades}}
names = sorted({k for v in TT.values() for k, b in v.items() if isinstance(b, (bool, np.bool_))})
def stats(rs):
    rs = np.array(rs) * 100
    if len(rs) < 5: return {"n": len(rs)}
    return {"n": len(rs), "avg_pct": round(float(rs.mean()), 2), "median_pct": round(float(np.median(rs)), 2), "win_pct": round(float((rs > 0).mean() * 100), 1), "t": round(float(rs.mean() / (rs.std(ddof=1) / np.sqrt(len(rs)))), 2)}
RES = {"note": __doc__, "news_ok": news_ok, "news_error": news_err, "signals": len(sig_tj), "trades": len(trades), "news_tagged_signals": len(TAG), "per_trade": {}}
half = lambda a: "2016-2020" if dn[a] < np.datetime64("2021-01-01") else "2021-2026"
allr = [r for _, _, r in trades]; RES["per_trade"]["ALL trades"] = {"all": stats(allr), **{h: stats([r for j, a, r in trades if half(a) == h]) for h in ("2016-2020", "2021-2026")}}
for nm in names:
    yes = [(a, r) for j, a, r in trades if TT[(a, j)].get(nm)]; no = [(a, r) for j, a, r in trades if (a, j) in TT and nm in TT[(a, j)] and not TT[(a, j)][nm]]
    RES["per_trade"][nm] = {"with": stats([r for _, r in yes]), "without": stats([r for _, r in no]),
                            **{f"with {h}": stats([r for a, r in yes if half(a) == h]) for h in ("2016-2020", "2021-2026")}}
    w = RES["per_trade"][nm]["with"]; print(f"{nm:45s} with: {w}  | without avg {RES['per_trade'][nm]['without'].get('avg_pct')}", flush=True)
# ---------------------------------------------------------------- full bot with a tag skipped (a skipped signal frees the slot for the next one)
def cagr(cv, a, b="2100-01-01"):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b))); c = cv[ix] / cv[ix[0] - 1]; return round((c[-1] ** (252 / len(ix)) - 1) * 100, 1)
def worst(cv, a="2016-01-01"):
    c = cv[np.flatnonzero(dn >= np.datetime64(a))]; return round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1)
def full(cv): return {"2016-2026": cagr(cv, "2016-01-04"), "2016-2020": cagr(cv, "2016-01-04", "2021-01-01"), "2021-2026": cagr(cv, "2021-01-01"), "worst_drop_2016+": worst(cv)}
RES["full_bot"] = {"TODAY (take every signal)": full(curve0)}
SKIP = ["ANY firm-specific bad news", "firm bad news AND peers flat", "downgrade", "guidance cut / warning", "legal / probe", "short-seller report", "earnings miss", "4+ own headlines (lots of attention)", "peers flat, stock alone (peers > -2%)", "no headlines at all"]
rng = np.random.default_rng(11)
for nm in SKIP:
    if not any(nm in v for v in TT.values()): continue
    m = np.zeros_like(S.SIG); k = 0
    for (t, j), v in TT.items():
        if v.get(nm) and S.SIG[t, j]: m[t, j] = True; k += 1
    cv, _ = S.sim(sig=S.SIG & ~m, **LIVE); RES["full_bot"][f"skip: {nm}"] = {**full(cv), "signals_skipped": k}
    # placebo: skip the same number of random signals (5 draws)
    pl = []
    idx = [(t, j) for t, j in sig_tj]
    for _ in range(5):
        mm = np.zeros_like(S.SIG)
        for q in rng.choice(len(idx), size=min(k, len(idx)), replace=False): mm[idx[q]] = True
        pl.append(full(S.sim(sig=S.SIG & ~mm, **LIVE)[0])["2016-2026"])
    RES["full_bot"][f"skip: {nm}"]["random_skip_same_count_2016-2026"] = [min(pl), float(np.median(pl)), max(pl)]
    print("FULL skip", nm, RES["full_bot"][f"skip: {nm}"], flush=True)
print("FULL today", RES["full_bot"]["TODAY (take every signal)"], flush=True)
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
