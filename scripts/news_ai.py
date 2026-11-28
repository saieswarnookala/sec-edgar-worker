"""Job 7 (Nov 28): AI news check. For every dip-bot signal 2016-2026 that came within 5 trading days after a NON-earnings 8-K
(exhibit-only filings ignored), Claude reads the 8-K's main document and labels it BAD (material company-specific bad news),
NEUTRAL (routine) or GOOD. Then: do BAD-news dips bounce less? And the dip bot (v3.0 rules, live-like + realistic) with BAD-news dips skipped.
Only labels are saved (ticker, date, items, label) - no filing text. Needs SEC_USER_AGENT; ANTHROPIC_API_KEY for the labels
(without it: counts and the item-code baseline only). Caveat: the model may remember what happened to famous companies (look-ahead);
compare with the plain item-code filter (job 1) and with the months after the model's training data.
Env: MAX_LABELS (default 900), MODEL (default claude-haiku-5-5), START (default 2016-01-01). DRY=1: fake labels, no network."""
import os, sys, json, time, re, html, random, urllib.request, urllib.error
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
DRY = S.DRY; UA = os.environ.get("SEC_USER_AGENT", ""); KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("MODEL", "claude-haiku-5-5"); MAXL = int(os.environ.get("MAX_LABELS", "900")); START = os.environ.get("START", "2016-01-01")
OUT = "data/news_ai.json" if not DRY else "/tmp/news_ai_dry.json"
dn, t0, tick = S.dn, S.t0, S.tick; dstr = np.array([str(x)[:10] for x in dn]); T_START = time.time()
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003, etf=True, bond=True); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005, etf=True, bond=True)
ITEMS = json.load(open("data/sec_8k_items.json"))["tickers"]; META = json.load(open("data/sec_events_sic.json"))["tickers"]
BASE_ITEMS = {"9.01", "9", "7"}          # exhibits only (old-format 7 = exhibits) -> not news by itself
def eff_day(d, mins):
    i = int(np.searchsorted(dstr, d))
    if i < len(dstr) and dstr[i] == d and mins is not None and mins > 15 * 60 + 45: i += 1
    return i
# 1) news dips: signal day t, an 8-K with items beyond exhibits and NOT earnings, effective in [t-4, t]
t_start = int(np.searchsorted(dstr, START)); news = {}
for j, tk in enumerate(tick):
    for d, mins, it in ITEMS.get(tk) or []:
        its = set((it or "").split(",")) - {""}
        if not its or its <= BASE_ITEMS or its & {"2.02", "12"}: continue
        i = eff_day(d, mins)
        for t in range(i, min(i + 5, len(dn))):
            if t >= max(t0, t_start) and S.SIG[t, j]: news.setdefault((t, j), []).append((d, mins, ",".join(sorted(its - BASE_ITEMS))))
allsig = [(t, j) for t, j in zip(*np.nonzero(S.SIG)) if t >= max(t0, t_start)]
print(f"dip signals since {START}: {len(allsig)} | with a non-earnings 8-K in the 5 days before: {len(news)}", flush=True)
# trade return label for every dip (live-style: buy at the close, sell at the first close above the 5-day average or after 5 days)
C = S.S_C
def tret(t, j):
    e = None
    for k in range(1, 6):
        if t + k >= len(dn) or not np.isfinite(C[t + k, j]): break
        e = t + k
        if C[t + k, j] > S.S_M5[t + k, j]: break
    return (C[e, j] / C[t, j] - 1) if e is not None and C[t, j] > 0 else np.nan
# 2) fetch the filings' main documents and label them
def get(url, hdr=None, data=None, tries=4):
    for a in range(tries):
        try:
            rq = urllib.request.Request(url, data=data, headers=hdr or {"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(rq, timeout=60) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 400): return None
            time.sleep(1.5 * 2 ** a)
        except Exception: time.sleep(1.5 * 2 ** a)
    return None
SUBS = {}
def filings_of(cik):
    if cik in SUBS: return SUBS[cik]
    out = []
    js = get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"); time.sleep(0.12)
    if js:
        js = json.loads(js); pages = [js["filings"]["recent"]] + []
        for f in js["filings"].get("files", []):
            if f.get("filingTo", "9999") >= START:
                p = get("https://data.sec.gov/submissions/" + f["name"]); time.sleep(0.12)
                if p: pages.append(json.loads(p))
        for r in pages:
            for i, form in enumerate(r.get("form", [])):
                if form in ("8-K", "8-K/A") and r["filingDate"][i] >= START[:4]:
                    out.append((r["filingDate"][i], (r.get("acceptanceDateTime") or [""] * len(r["form"]))[i][:10], r["accessionNumber"][i], r.get("primaryDocument", [""] * len(r["form"]))[i], r.get("items", [""] * len(r["form"]))[i]))
    SUBS[cik] = out; return out
def doc_text(cik, acc, doc):
    if not doc: return ""
    raw = get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"); time.sleep(0.12)
    if not raw: return ""
    t = raw.decode("utf-8", "ignore"); t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t); t = re.sub(r"(?s)<[^>]+>", " ", t); t = html.unescape(t)
    t = re.sub(r"\s+", " ", t); k = t.find("Item "); t = t[k:] if 0 <= k < 4000 else t
    return t[:6000]
PROMPT = ("A stock just fell sharply over 5 days. In the days before, the company filed this SEC Form 8-K. Judge ONLY the filing's news for the stock over the "
          "next week. BAD = materially negative company-specific news (e.g. CEO/CFO abrupt exit or firing, guidance cut, restatement, impairment or write-down, "
          "layoffs from weakness, lost major customer or contract, investigation, delisting notice, default or financing stress, failed trial or product). "
          "NEUTRAL = routine (planned succession, board changes, annual meeting votes, routine debt or buyback, investor presentation, dividends, "
          "routine agreements). GOOD = clearly positive. Reply with JSON only: {\"label\": \"BAD\"|\"NEUTRAL\"|\"GOOD\", \"why\": \"<= 12 words\"}.\n\nFILING:\n")
def claude(text):
    if DRY: return random.choice(["BAD", "NEUTRAL", "NEUTRAL", "GOOD"])
    body = json.dumps({"model": MODEL, "max_tokens": 60, "messages": [{"role": "user", "content": PROMPT + text}]}).encode()
    for a in range(5):
        raw = get("https://api.anthropic.com/v1/messages", hdr={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}, data=body, tries=1)
        if raw:
            try:
                txt = json.loads(raw)["content"][0]["text"]; m = re.search(r"\b(BAD|NEUTRAL|GOOD)\b", txt); return m.group(1) if m else None
            except Exception: pass
        time.sleep(3 * 2 ** a)
    return None
RES = {"note": __doc__, "model": MODEL if KEY else None, "start": START, "dip_signals": len(allsig), "news_dips": len(news)}
keys = sorted(news); random.Random(7).shuffle(keys); keys = sorted(keys[:MAXL])
LAB = {}
if KEY or DRY:
    random.seed(3); done = 0
    for (t, j) in keys:
        tk = tick[j]; cik = (META.get(tk) or {}).get("cik")
        if not cik and not DRY: continue
        texts = []
        for d, mins, its in news[(t, j)][-2:]:                      # up to the 2 latest filings before the dip
            if DRY: texts.append(f"Item {its} sample"); continue
            m = [f for f in filings_of(cik) if f[0] == d or f[1] == d]
            for f in m[:1]: texts.append(doc_text(cik, f[2], f[3]))
        txt = " \n---\n ".join(x for x in texts if x)
        if not txt: continue
        lab = claude(txt[:9000])
        if lab: LAB[(t, j)] = lab; done += 1
        if done % 50 == 0 and done: print(f"labeled {done} ({int(time.time() - T_START)}s)", flush=True)
else:
    print("ANTHROPIC_API_KEY not set: no AI labels (add the repo secret to run this part)", flush=True)
RES["labeled"] = len(LAB)
# 3) outcomes
rows = [{"t": t, "j": j, "y": tret(t, j), "news": (t, j) in news, "label": LAB.get((t, j))} for t, j in allsig]
F = pd.DataFrame(rows); F = F[np.isfinite(F.y)]
def st(x): return {"n": int(len(x)), "avg_trade_pct": round(float(x.mean()) * 100, 2) if len(x) else None, "win_pct": round(float((x > 0).mean()) * 100, 1) if len(x) else None}
RES["dips without non-earnings 8-K news"] = st(F[~F.news].y); RES["dips after non-earnings 8-K news (all)"] = st(F[F.news].y)
for lab in ("BAD", "NEUTRAL", "GOOD"): RES[f"news dips labeled {lab}"] = st(F[F.label == lab].y)
print(json.dumps({k: v for k, v in RES.items() if k not in ("note",)}, default=float), flush=True)
# 4) the dip bot with BAD-labeled dips skipped (unlabeled dips kept); placebo = skip the same number of random news dips
def run(kw, sig=None):
    c, tr = S.sim(**kw, sig=sig); s = S.summ(c, tr); return {k: s[k] for k in ("1999-2026", "2013-2026") if k in s} | {"trades": len(tr)}
if LAB:
    bad = [k for k, v in LAB.items() if v == "BAD"]; sk = np.array(S.SIG, copy=True)
    for t, j in bad: sk[t, j] = False
    RES["engine: base"] = {"live": run(LIVE), "realistic": run(REAL)}
    RES["engine: skip BAD-labeled news dips"] = {"live": run(LIVE, sk), "realistic": run(REAL, sk), "skipped": len(bad)}
    pl = []
    for sd in range(4):
        rk = random.Random(100 + sd).sample(sorted(LAB), min(len(bad), len(LAB))); sp = np.array(S.SIG, copy=True)
        for t, j in rk: sp[t, j] = False
        pl.append(run(LIVE, sp)["2013-2026"]["per_year_pct"])
    RES["engine: placebo (skip as many random labeled news dips), live 2013-2026 per year"] = sorted(pl)
    print("engine", json.dumps({k: v for k, v in RES.items() if k.startswith("engine")}, default=float), flush=True)
    RES["labels"] = [{"ticker": tick[j], "date": dstr[t], "items": news[(t, j)][-1][2], "label": v} for (t, j), v in sorted(LAB.items())]
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1, default=float); print("DONE", int(time.time() - T_START), "s", flush=True)
