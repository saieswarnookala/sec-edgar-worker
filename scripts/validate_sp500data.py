# Validate Johnbrick123/sp500-data (survivorship-free S&P 500 prices) against our Alpaca data, 2016-2026.
import os, json, random, urllib.request, urllib.parse, time
import pandas as pd
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet")
mem = pd.read_parquet("/tmp/membership_intervals.parquet")
out = {"columns": list(px.columns), "rows": int(len(px)), "tickers": int(px["ticker"].nunique())}
px["date"] = pd.to_datetime(px["date"])
out["date_range"] = [str(px["date"].min().date()), str(px["date"].max().date())]
st, en = pd.to_datetime(mem.start), pd.to_datetime(mem.end).fillna(pd.Timestamp("2100-01-01"))
# coverage: members with prices during their membership, 2004-2015
cov = []
for _, r in mem[(en > "2004-08-01") & (st < "2016-01-01")].iterrows():
    s = px[(px.ticker == r.ticker) & (px.date >= max(pd.Timestamp(r.start), pd.Timestamp("2004-08-01"))) & (px.date < min(pd.Timestamp(r.end or "2100-01-01"), pd.Timestamp("2016-01-01")))]
    need = len(pd.bdate_range(max(pd.Timestamp(r.start), pd.Timestamp("2004-08-01")), min(pd.Timestamp(r.end) if pd.notna(r.end) else pd.Timestamp("2016-01-01"), pd.Timestamp("2016-01-01"))))
    cov.append((r.ticker, len(s), need))
out["coverage_2004_2015"] = {"members": len(cov), "with_90pct_days": sum(1 for _, k, n in cov if n and k >= 0.9 * n * 0.96), "missing_examples": [t for t, k, n in cov if n and k < 0.5 * n][:30]}
# compare daily adjusted returns vs Alpaca for a sample of tickers (current + removed since 2016)
H = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
plain = sorted(t for t in px.ticker.unique() if t.isalpha() and len(t) <= 5)
recent = set(px[px.date >= "2016-01-04"].ticker.unique())
random.seed(7); sample = random.sample([t for t in plain if t in recent], 60) + ["SPY", "AAPL", "JPM", "XOM", "GE"]
adj = "adj_close" if "adj_close" in px.columns else "close"
res = []
for i in range(0, len(sample), 30):
    chunk = sample[i:i + 30]; bars = {}; tok = None
    while True:
        q = {"symbols": ",".join(chunk), "timeframe": "1Day", "start": "2016-01-01", "end": "2026-10-30", "adjustment": "all", "feed": "sip", "limit": "10000"}
        if tok: q["page_token"] = tok
        url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(q)
        j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60))
        for s, a in (j.get("bars") or {}).items(): bars.setdefault(s, []).extend(a)
        tok = j.get("next_page_token")
        if not tok: break
        time.sleep(0.3)
    for t in chunk:
        if t not in bars: res.append({"t": t, "status": "not in alpaca"}); continue
        a = pd.Series({pd.Timestamp(b["t"][:10]): b["c"] for b in bars[t]}).sort_index().pct_change()
        o = px[(px.ticker == t) & (px.date >= "2016-01-01")].set_index("date")[adj].sort_index().pct_change()
        j2 = pd.concat([a, o], axis=1, join="inner").dropna(); j2.columns = ["alp", "theirs"]
        if len(j2) < 50: res.append({"t": t, "status": "few overlap", "n": len(j2)}); continue
        d = (j2.alp - j2.theirs).abs() * 100
        res.append({"t": t, "days": len(j2), "pct_days_off_0.5pp": round(float((d > 0.5).mean() * 100), 2), "max_pp": round(float(d.max()), 2),
                    "wealth_alp": round(float((1 + j2.alp).prod()), 3), "wealth_theirs": round(float((1 + j2.theirs).prod()), 3)})
ok = [r for r in res if "days" in r]
out["alpaca_compare"] = {"tickers": len(ok), "median_pct_days_off": float(pd.Series([r["pct_days_off_0.5pp"] for r in ok]).median()),
    "tickers_with_over_1pct_days_off": [r for r in ok if r["pct_days_off_0.5pp"] > 1], "wealth_diff_over_5pct": [r for r in ok if abs(r["wealth_alp"] / r["wealth_theirs"] - 1) > 0.05], "skipped": [r for r in res if "days" not in r]}
os.makedirs("data", exist_ok=True); json.dump(out, open("data/sp500data_validation.json", "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k != "alpaca_compare"}, default=str)); print(json.dumps(out["alpaca_compare"], default=str)[:3000])
