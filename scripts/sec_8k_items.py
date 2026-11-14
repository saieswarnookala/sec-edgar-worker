# Every 8-K filing (date, time, item numbers) for S&P 500 members since 2004, for "skip dips that came with news" tests.
# Reuses the ticker -> SEC CIK match in data/sec_events_sic.json. Output: data/sec_8k_items.json. Research only.
import os, json, re, time, urllib.request, urllib.error
UA = os.environ["SEC_USER_AGENT"]
def sec(url, tries=6):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
        except Exception: pass
        time.sleep(1.5 * 2 ** a)
    return None
tickers = json.load(open("data/sec_events_sic.json"))["tickers"]
bycik = {}
for t, v in tickers.items():
    if v.get("cik"): bycik.setdefault(int(v["cik"]), []).append(t)
out = {}; n = 0
for cik, tks in bycik.items():
    j = sec(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"); time.sleep(0.12)
    if not j: continue
    pages = [j["filings"]["recent"]]
    for f in j["filings"].get("files", []):
        if (f.get("filingTo") or "9999") < "2004-07-01": continue
        x = sec("https://data.sec.gov/submissions/" + f["name"]); time.sleep(0.12)
        if x: pages.append(x)
    ev = set()
    for r in pages:
        forms = r.get("form", []); items = r.get("items") or [""] * len(forms); acc = r.get("acceptanceDateTime") or [""] * len(forms)
        for i, form in enumerate(forms):
            if form not in ("8-K", "8-K/A") or not items[i]: continue
            a = acc[i] or ""; m = re.search(r"T(\d\d):(\d\d)", a)
            ev.add((a[:10] if m else r["filingDate"][i], int(m.group(1)) * 60 + int(m.group(2)) if m else 999, items[i].replace(" ", "")))
    for t in tks: out[t] = sorted(ev)
    n += 1
    if n % 100 == 0: print(n, "companies", flush=True)
os.makedirs("data", exist_ok=True)
json.dump({"built": time.strftime("%Y-%m-%d"), "tickers": out}, open("data/sec_8k_items.json", "w"))
print(len(out), "tickers,", sum(len(v) for v in out.values()), "8-K filings")
