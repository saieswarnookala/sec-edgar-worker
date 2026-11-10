# Builds a reusable cache for S&P 500 members since 1998 (point in time, incl. removed companies):
# SEC CIK, SIC industry code, and every 8-K Item 2.02 (earnings release) filing time. Output: data/sec_events_sic.json. Research only.
import os, json, re, time, urllib.request, urllib.error
import pandas as pd
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["membership_intervals.parquet", "members.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e); time.sleep(20 * (i + 1))
UA = os.environ["SEC_USER_AGENT"]
def sec(url, tries=6):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r: return json.load(r) if url.endswith(".json") else r.read().decode("latin-1")
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
        except Exception: pass
        time.sleep(1.5 * 2 ** a)
    return None
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
mem = mem[mem.end.isna() | (mem.end > "1998-01-01")].copy()
info = pd.read_parquet("/tmp/members.parquet")
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
tk = sec("https://www.sec.gov/files/company_tickers.json") or {}
byT = {v["ticker"].upper(): v["cik_str"] for v in tk.values()}
SUF = set("INC INCORPORATED CORP CORPORATION CO COMPANY COMPANIES LTD LIMITED PLC LLC LP HOLDINGS HOLDING GROUP THE NV SA AG SE TRUST BANCORP CLASS A B C DE NEW INTERNATIONAL INTL".split())
norm = lambda s: " ".join(w for w in re.sub(r"[^A-Z0-9 ]", " ", re.sub(r"\(.*?\)", " ", (s or "").upper().replace("&", " AND "))).split() if w not in SUF)
need = {norm(names[t]) for t in mem.ticker if t in names}; nameC = {}
lk = sec("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt") or ""
for line in lk.split("\n"):
    i = line.rfind(":", 0, len(line) - 1)
    if i < 0: continue
    k = norm(line[:i])
    if k in need:
        try: c = int(line[i + 1:].strip(":"))
        except Exception: continue
        if c not in nameC.setdefault(k, []) and len(nameC[k]) < 6: nameC[k].append(c)
cache = {}
def company(cik):
    if cik in cache: return cache[cik]
    j = sec(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"); time.sleep(0.12); pages = []; sic = None
    if j:
        sic = j.get("sic"); pages.append(j["filings"]["recent"])
        for f in j["filings"].get("files", []):
            if (f.get("filingTo") or "9999") < "2004-07-01": continue
            x = sec("https://data.sec.gov/submissions/" + f["name"]); time.sleep(0.12)
            if x: pages.append(x)
    ev = []
    for r in pages:
        for i, form in enumerate(r.get("form", [])):
            if form != "8-K" or not re.search(r"(^|,)\s*2\.02\s*(,|$)", (r.get("items") or [""] * 99)[i] or ""): continue
            fd = r["filingDate"][i]; a = (r.get("acceptanceDateTime") or [""] * 99)[i] or ""; m = re.search(r"T(\d\d):(\d\d)", a)
            ev.append((a[:10] if m else fd, int(m.group(1)) * 60 + int(m.group(2)) if m else 999))
    cache[cik] = (sic, sorted(set(ev))); return cache[cik]
out = {}; n = 0
for _, m in mem.iterrows():
    t = m.ticker; base = t.split("-")[0] if re.search(r"-\d{6}$", t) else t
    s0, e0 = str(max(m.start, pd.Timestamp("2004-08-01")).date()), str((m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")).date())
    cands = []
    if t in ciks: cands.append(ciks[t])
    for k in [base, base.replace(".", "-"), base.replace("-", ".")]:
        if k in byT and byT[k] not in cands: cands.append(byT[k])
    for c in nameC.get(norm(names.get(t, "")), []):
        if c not in cands: cands.append(c)
    best, bn = None, -1
    for c in cands[:6]:
        sic, ev = company(c); k = sum(1 for d, _ in ev if s0 <= d < e0)
        if k > bn: best, bn = c, k
    if best is None: continue
    sic, ev = company(best)
    prev = out.get(t, {"events": []})
    out[t] = {"cik": best, "sic": sic, "events": sorted(set(map(tuple, prev["events"])) | set(ev))}
    n += 1
    if n % 50 == 0: print(n, "tickers", flush=True)
os.makedirs("data", exist_ok=True)
json.dump({"tickers": out, "built": time.strftime("%Y-%m-%d"), "with_sic": sum(1 for v in out.values() if v["sic"]), "with_events": sum(1 for v in out.values() if v["events"])}, open("data/sec_events_sic.json", "w"))
print(len(out), "tickers saved")
