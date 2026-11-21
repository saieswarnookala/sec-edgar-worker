"""India strategies on SURVIVORSHIP-FREE data (Nov 21 2026). Research only, not financial advice.
Source: NSE daily bhavcopy archives (every stock traded each day, including ones later delisted / merged / suspended), 2006-2026,
cached privately in R2 (nse/bhav/<year>.json.gz). Daily return = CLOSE / PREVCLOSE - 1 (NSE adjusts PREVCLOSE on ex-dates for splits and
bonuses; checked below on known events). Prices exclude dividends (~1.3%/yr for Nifty), same for the Nifty 50 benchmark.
MODE fetch: download/cache missing days. MODE run: the tests (see run()). DRY=1: fake data."""
import os, sys, io, json, time, zipfile, urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DRY = os.environ.get("DRY") == "1"
if not DRY: import r2cache
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
SERIES = {"EQ", "BE", "BZ"}
def get(u, tries=4):
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(3 * (a + 1))
        except Exception: time.sleep(3 * (a + 1))
    return None
def yahoo(sym, start="2006-01-01"):
    p1 = int(pd.Timestamp(start).timestamp())
    b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1={p1}&period2={int(time.time())}&interval=1d")
    j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]["quote"][0]
    adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
    s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); return s[~s.index.duplicated(keep="last")]
def bhav(d):
    """{symbol: [open, high, low, close, prevclose, traded value Rs]} for EQ/BE/BZ series on date d"""
    if d < pd.Timestamp("2024-07-08"):
        u = f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{d.year}/{MON[d.month-1]}/cm{d.day:02d}{MON[d.month-1]}{d.year}bhav.csv.zip"
    else: u = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    b = get(u)
    if not b: return None
    z = zipfile.ZipFile(io.BytesIO(b)); df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    df.columns = [c.strip() for c in df.columns]
    if "TckrSymb" in df.columns:
        df = df.rename(columns={"TckrSymb": "SYMBOL", "SctySrs": "SERIES", "OpnPric": "OPEN", "HghPric": "HIGH", "LwPric": "LOW", "ClsPric": "CLOSE", "PrvsClsgPric": "PREVCLOSE", "TtlTrfVal": "TOTTRDVAL"})
    df = df[df.SERIES.astype(str).str.strip().isin(SERIES)]
    return {str(r.SYMBOL).strip(): [float(r.OPEN), float(r.HIGH), float(r.LOW), float(r.CLOSE), float(r.PREVCLOSE), float(r.TOTTRDVAL)] for r in df.itertuples()}
def fetch():
    days = [d for d in yahoo("^NSEI").index if d >= pd.Timestamp("2006-06-01")]
    for y in sorted({d.year for d in days}):
        key = f"nse/bhav/{y}.json.gz"; cache = r2cache.load(key) or {}; miss = [d for d in days if d.year == y and str(d.date()) not in cache]
        print(y, "cached", len(cache), "missing", len(miss), flush=True); n = 0
        for d in miss:
            x = bhav(d); cache[str(d.date())] = x or {}; n += 1; time.sleep(0.4)
            if n % 60 == 0: r2cache.save(key, cache); print(" ", y, n, "of", len(miss), flush=True)
        if miss: r2cache.save(key, cache)
        print(y, "done:", sum(1 for v in cache.values() if v), "days with data", flush=True)
def load():
    """daily DataFrames (dates x symbols): close, prevclose, open, high, low, traded value"""
    if DRY:
        rng = np.random.default_rng(2); ix = pd.bdate_range("2006-06-01", "2026-11-20"); syms = [f"S{i}" for i in range(300)]
        C = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.022, (len(ix), len(syms))), axis=0)), index=ix, columns=syms)
        for i in range(0, 300, 7): C.iloc[rng.integers(500, len(ix)):, i] = np.nan          # delistings
        PC = C.shift(1); O = PC * (1 + rng.normal(0, 0.006, C.shape)); V = pd.DataFrame(rng.lognormal(18, 1.0, C.shape), index=ix, columns=syms).where(C.notna())
        return C, PC, O, C * 1.01, C * 0.99, V
    rows = {}
    for y in range(2006, pd.Timestamp.today().year + 1):
        c = r2cache.load(f"nse/bhav/{y}.json.gz") or {}; rows.update({d: v for d, v in c.items() if v})
    dates = sorted(rows); ix = pd.to_datetime(dates); syms = sorted({s for d in dates for s in rows[d]}); si = {s: i for i, s in enumerate(syms)}
    A = np.full((6, len(dates), len(syms)), np.nan, dtype=np.float32)
    for t, d in enumerate(dates):
        for s, v in rows[d].items(): A[:, t, si[s]] = v
    mk = lambda k: pd.DataFrame(A[k], index=ix, columns=syms)
    return mk(3), mk(4), mk(0), mk(1), mk(2), mk(5)
if __name__ == "__main__" and (sys.argv[1:2] or ["run"])[0] == "fetch": fetch(); sys.exit(0)
