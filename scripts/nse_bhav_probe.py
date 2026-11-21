"""Probe: can GitHub Actions download NSE daily bhavcopy archives (all listed stocks, incl. later-delisted) for 2008-2026?"""
import urllib.request, io, zipfile, json, time
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
T = [("old", "https://archives.nseindia.com/content/historical/EQUITIES/2008/JAN/cm01JAN2008bhav.csv.zip"),
     ("old", "https://archives.nseindia.com/content/historical/EQUITIES/2015/JUN/cm01JUN2015bhav.csv.zip"),
     ("old", "https://nsearchives.nseindia.com/content/historical/EQUITIES/2020/MAR/cm02MAR2020bhav.csv.zip"),
     ("new", "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip"),
     ("new", "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261120_F_0000.csv.zip"),
     ("idx", "https://archives.nseindia.com/content/indices/ind_close_all_01012010.csv"),
     ("mcap", "https://nsearchives.nseindia.com/archives/equities/mkt/MA010110.csv")]
out = []
for kind, u in T:
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()
        info = {"kind": kind, "url": u, "bytes": len(b)}
        if u.endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(b)); n = z.namelist()[0]; txt = z.read(n).decode(errors="ignore").splitlines()
            info.update(rows=len(txt), head=txt[0][:300], sample=txt[1][:200])
        else: info.update(head=b[:300].decode(errors="ignore"))
    except Exception as e: info = {"kind": kind, "url": u, "error": str(e)[:200]}
    print(json.dumps(info), flush=True); out.append(info); time.sleep(1.5)
