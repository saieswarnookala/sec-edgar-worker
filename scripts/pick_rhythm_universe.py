"""Pick ~100 stocks for the per-stock rhythm test by a FIXED rule (no hand-picking, no hindsight):
the most-traded US common stocks in 2022 (average daily dollar volume) that were NOT S&P 500 members on 2022-12-30,
priced >= $5 on average, traded >= 200 days in 2022. Chosen with 2022 data only, so stocks that later failed are kept.
Writes data/rhythm_universe.json with the list split into batches of 5. Alpaca calls are paced (RATE_PER_MIN)."""
import os, json, time, re, urllib.request, urllib.parse, urllib.error
import pandas as pd

N_PICK = int(os.environ.get("N_PICK", "100")); RATE = float(os.environ.get("RATE_PER_MIN", "150"))
H = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
_last = [0.0]
def get(url):
    for i in range(10):
        w = 60.0 / RATE - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = e.headers.get("Retry-After"); time.sleep(float(ra) if ra and ra.replace(".", "").isdigit() else min(120, 15 * (i + 1))); continue
            if e.code in (400, 403, 404, 422): print("HTTP", e.code, e.read()[:200], flush=True); return None
            time.sleep(5 * (i + 1))
        except Exception: time.sleep(3 * (i + 1))
    return None
FUND = re.compile(r"\b(ETF|ETN|FUND|TRUST|SHARES|PROSHARES|DIREXION|ISHARES|SPDR|INVESCO|VANGUARD|WISDOMTREE|GLOBAL X|ULTRA|LEVERAGED|INVERSE|BULL|BEAR|2X|3X|NOTES?|WARRANTS?|UNITS?|RIGHTS?|PREFERRED|DEPOSITARY|ACQUISITION)\b", re.I)
assets = {}
for st in ("active", "inactive"):
    for a in get("https://paper-api.alpaca.markets/v2/assets?" + urllib.parse.urlencode({"status": st, "asset_class": "us_equity"})) or []:
        if a.get("exchange") in ("NYSE", "NASDAQ", "AMEX", "ARCA", "BATS") and re.fullmatch(r"[A-Z]{1,5}", a["symbol"]) and not FUND.search(a.get("name") or ""):
            assets[a["symbol"]] = a.get("name") or ""
print("candidate symbols", len(assets), flush=True)
if len(assets) < 1000: raise SystemExit("asset list looks wrong (< 1000 symbols), stopping")
# S&P 500 members on 2022-12-30 (point-in-time membership file)
mf = "/tmp/membership_intervals.parquet"
if not os.path.exists(mf): urllib.request.urlretrieve("https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/membership_intervals.parquet", mf)
mem = pd.read_parquet(mf); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
d0 = pd.Timestamp("2022-12-30")
sp = set(mem[(mem.start <= d0) & ((mem.end.isna()) | (mem.end > d0))].ticker)
print("S&P 500 members on 2022-12-30:", len(sp), flush=True)
syms = sorted(s for s in assets if s not in sp)
stats = {}
def fetch(batch):
    p = {"symbols": ",".join(batch), "timeframe": "1Day", "start": "2022-01-01", "end": "2022-12-31", "adjustment": "split", "feed": "sip", "limit": "10000"}
    while True:
        js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p))
        if js is None:
            if len(batch) > 1: h = len(batch) // 2; fetch(batch[:h]); fetch(batch[h:])
            return
        for s, bl in (js.get("bars") or {}).items():
            st = stats.setdefault(s, [0, 0.0, 0.0])
            for b in bl: st[0] += 1; st[1] += b["c"] * b["v"]; st[2] += b["c"]
        if not js.get("next_page_token"): return
        p["page_token"] = js["next_page_token"]
for i in range(0, len(syms), 100):
    fetch(syms[i:i + 100])
    if i % 2000 == 0: print("fetched", i, "of", len(syms), "with data", len(stats), flush=True)
rows = [(s, st[1] / st[0], st[2] / st[0], st[0]) for s, st in stats.items() if st[0] >= 200 and st[2] / st[0] >= 5]
rows.sort(key=lambda x: -x[1])
pick = rows[:N_PICK]
print("eligible", len(rows), "picked", len(pick), flush=True)
if len(pick) < N_PICK * 0.8: raise SystemExit("too few eligible stocks, stopping")
batches = [[x[0] for x in pick[i:i + 5]] for i in range(0, len(pick), 5)]
json.dump({"rule": __doc__, "picked": [{"symbol": s, "name": assets.get(s, ""), "avg_dollar_volume_2022_m": round(dv / 1e6, 1), "avg_price_2022": round(px, 2), "days": n} for s, dv, px, n in pick],
           "batches": [",".join(b) for b in batches]}, open("data/rhythm_universe.json", "w"), indent=1)
print(json.dumps([",".join(b) for b in batches]))
