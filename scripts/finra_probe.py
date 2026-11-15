"""Probe which free FINRA short data exists (prints status, size, header, an AAPL row). No trading logic."""
import urllib.request, json, time
UA = {"User-Agent": "Mozilla/5.0 sentinel-research"}
def get(u, data=None, hdr=None):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, data=data, headers={**UA, **(hdr or {})}), timeout=60); b = r.read(); return r.status, b
    except urllib.error.HTTPError as e: return e.code, e.read()[:300]
    except Exception as e: return str(e)[:80], b""
for d in ["20140115", "20170615", "20190614", "20210615", "20210630", "20210715", "20220114", "20261015"]:
    s, b = get(f"https://cdn.finra.org/equity/otcmarket/biweekly/shrt{d}.csv"); t = b.decode("latin1", "ignore").splitlines()
    print("SI", d, s, len(b), "|", t[0][:200] if t else "", "| AAPL:", next((x[:200] for x in t if "|AAPL|" in x or ",AAPL," in x), None), "| rows", len(t), flush=True); time.sleep(1)
for d in ["20090803", "20100104", "20150105", "20200102", "20261030"]:
    s, b = get(f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"); t = b.decode("latin1", "ignore").splitlines()
    print("SHVOL", d, s, len(b), "|", t[0][:200] if t else "", "| AAPL:", next((x for x in t if "|AAPL|" in x), None), flush=True); time.sleep(1)
for ds in ["consolidatedShortInterest", "equityShortInterest"]:
    for grp in ["otcMarket"]:
        s, b = get(f"https://api.finra.org/data/group/{grp}/name/{ds}", data=json.dumps({"limit": 3, "compareFilters": [{"compareType": "equal", "fieldName": "symbolCode", "fieldValue": "AAPL"}], "sortFields": ["settlementDate"]}).encode(), hdr={"Content-Type": "application/json", "Accept": "application/json"})
        print("API", ds, s, b[:600], flush=True); time.sleep(1)
s, b = get("https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest?limit=2", hdr={"Accept": "application/json"}); print("API GET", s, b[:600])
