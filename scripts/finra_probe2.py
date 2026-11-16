"""Probe free OLD short data sources (no trading logic)."""
import urllib.request, time, json
UA = {"User-Agent": "Mozilla/5.0 sentinel-research"}
def get(u, n=None):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60); b = r.read(n) if n else r.read(); return r.status, b
    except urllib.error.HTTPError as e: return e.code, b""
    except Exception as e: return str(e)[:60], b""
for d in ["20090803", "20100104", "20120601", "20150105", "20170601", "20180801"]:
    for pre in ["FNSQshvol", "FNYXshvol", "CNMSshvol"]:
        for host in ["https://cdn.finra.org/equity/regsho/daily/", "http://regsho.finra.org/"]:
            s, b = get(f"{host}{pre}{d}.txt", 3000); t = b.decode("latin1", "ignore").splitlines()
            print("DAILY", d, pre, host[:28], s, "|", t[0][:90] if t else "", "| AAPL:", next((x for x in t if "|AAPL|" in x), None) if t else None, flush=True); time.sleep(0.4)
for u in ["http://regsho.finra.org/FNYXsh200912.txt.zip", "https://cdn.finra.org/equity/regsho/monthly/FNYXsh200912.txt.zip", "http://regsho.finra.org/FNYXsh201506.txt.zip"]:
    s, b = get(u, 2000); print("MONTHLY", u, s, len(b), flush=True); time.sleep(0.5)
for ds in ["edarchimbaud/short-interest-sp500", "edarchimbaud/short-interest-stocks", "paperswithbacktest/Stocks-Weekly-ShortVolume"]:
    s, b = get(f"https://huggingface.co/api/datasets/{ds}")
    try: j = json.loads(b); print("HF", ds, s, j.get("cardData", {}).get("license"), [x.get("rfilename") for x in j.get("siblings", [])][:8], (j.get("description") or "")[:200], flush=True)
    except Exception as e: print("HF", ds, s, str(e)[:80])
    s, b = get(f"https://datasets-server.huggingface.co/first-rows?dataset={ds}&config=default&split=train")
    print("HF rows", ds, s, b[:700], flush=True)
