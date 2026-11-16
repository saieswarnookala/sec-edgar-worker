"""Two SPY timing ideas (Nov 15 2026). Research only, not financial advice.
1) Overnight effect: hold SPY from the close to the next open only (cash during the day) vs intraday only vs buy & hold.
   Costs: 2 trades a day; tested at 0, 0.01% and 0.02% per side.
2) Pre-Fed-meeting drift (Lucca & Moench 2015): SPY tends to rise into scheduled FOMC announcements.
   Measured close-to-close on the announcement day (day A, statement at 2 pm) and the day before (A-1); compared with all
   other days; split 1999-2011 (the paper's sample) vs 2012-2026 (after it was published).
   Meeting dates: federalreserve.gov (fomchistorical<year>.htm parsed for 1999-2016, 2017+ listed from the Fed calendar); scheduled meetings
   only; each year must have 7-9 or the run stops."""
import os, re, json, time, urllib.request, html as H
import numpy as np, pandas as pd
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
if not os.path.exists("/tmp/prices.parquet"): urllib.request.urlretrieve(REL + "prices.parquet", "/tmp/prices.parquet")
p = pd.read_parquet("/tmp/prices.parquet", filters=[("ticker", "==", "SPY")]).sort_values("date"); p["date"] = pd.to_datetime(p.date)
s = p.set_index("date"); s = s[s.index >= "1995-01-01"]
f = s.adj_close / s.close; o, c = s.open * f, s.adj_close
ret = c.pct_change(); on = o / c.shift(1) - 1; intra = c / o - 1
ann = lambda r: round(((1 + r.dropna()).prod() ** (252 / max(1, r.notna().sum())) - 1) * 100, 1)
def dd(r):
    cv = (1 + r.fillna(0)).cumprod(); return round(float((cv / cv.cummax() - 1).min()) * 100, 1)
OVN = {}
for per, a, b in (("1995-2026", "1995", "2100"), ("1995-2010", "1995", "2011"), ("2011-2026", "2011", "2100")):
    m = (c.index >= a) & (c.index < b)
    OVN[per] = {"buy_and_hold_pct": ann(ret[m]), "buy_and_hold_worst": dd(ret[m]), "overnight_only_pct": ann(on[m]), "overnight_worst": dd(on[m]),
                "intraday_only_pct": ann(intra[m]), "overnight_cost_0.01pct_side": ann(on[m] - 0.0002), "overnight_cost_0.02pct_side": ann(on[m] - 0.0004)}
    print("OVERNIGHT", per, OVN[per], flush=True)

# ---------------- FOMC dates
MON = "January|February|March|April|May|June|July|August|September|October|November|December"
def get(u):
    for a in range(4):
        try: return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 sentinel-research"}), timeout=60).read().decode("utf-8", "ignore")
        except Exception as e: print("retry", u, str(e)[:80], flush=True); time.sleep(5 * (a + 1))
    return ""
dates = []
for y in range(1999, 2017):
    t = H.unescape(re.sub(r"<[^>]+>", " ", get(f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm"))); t = re.sub(r"\s+", " ", t); time.sleep(0.5)
    found = []
    for m in re.finditer(rf"({MON}) (\d{{1,2}})(?:\s*[-\u2013\u2014]\s*(?:({MON}) )?(\d{{1,2}}))? (?:FOMC )?Meeting\s*[-\u2013\u2014]\s*{y}", t):
        mon2 = m.group(3) or m.group(1); day2 = m.group(4) or m.group(2)
        found.append(pd.Timestamp(f"{mon2} {day2} {y}"))
    found = sorted(set(found)); found = [d for i, d in enumerate(found) if i + 1 == len(found) or (found[i + 1] - d).days > 3]   # same meeting listed twice -> keep last day
    print(y, len(found), [d.strftime("%m-%d") for d in found], flush=True)
    if not 7 <= len(found) <= 9: raise SystemExit(f"FOMC parse check failed for {y}: {len(found)} meetings")
    dates += found
recent = {2017: "February 1; March 15; May 3; June 14; July 26; September 20; November 1; December 13",   # 2017-2020 pages use another layout; dates from the Fed calendar
          2018: "January 31; March 21; May 2; June 13; August 1; September 26; November 8; December 19",
          2019: "January 30; March 20; May 1; June 19; July 31; September 18; October 30; December 11",
          2020: "January 29; April 29; June 10; July 29; September 16; November 5; December 16",   # March 2020 meetings were emergency moves, left out
          2021: "January 27; March 17; April 28; June 16; July 28; September 22; November 3; December 15",
          2022: "January 26; March 16; May 4; June 15; July 27; September 21; November 2; December 14",
          2023: "February 1; March 22; May 3; June 14; July 26; September 20; November 1; December 13",
          2024: "January 31; March 20; May 1; June 12; July 31; September 18; November 7; December 18",
          2025: "January 29; March 19; May 7; June 18; July 30; September 17; October 29; December 10",
          2026: "January 28; March 18; April 29; June 17; July 29; September 16; October 28"}           # federalreserve.gov/monetarypolicy/fomccalendars.htm
for y, txt in recent.items(): dates += [pd.Timestamp(f"{x.strip()} {y}") for x in txt.split(";")]
dates = sorted(d for d in set(dates) if d <= c.index[-1])
idx = c.index; A = [int(np.searchsorted(idx, d)) for d in dates if d in idx]
print("FOMC announcement days found in price data:", len(A), "of", len(dates), flush=True)
isA = np.zeros(len(idx), bool); isA[A] = True
isPre = np.zeros(len(idx), bool); isPre[[a - 1 for a in A if a > 0]] = True
r = ret.values; FED = {}
for per, a, b in (("1999-2026", "1999", "2100"), ("1999-2011", "1999", "2012"), ("2012-2026", "2012", "2100")):
    m = (idx >= a) & (idx < b) & np.isfinite(r)
    def st(mask):
        x = r[m & mask]; return {"days": int(len(x)), "avg_pct": round(float(np.mean(x)) * 100, 3), "up_pct": round(float(np.mean(x > 0)) * 100, 1),
                                 "t_vs_other": round(float((np.mean(x) - np.mean(r[m & ~isA & ~isPre])) / np.sqrt(np.var(x) / len(x) + np.var(r[m & ~isA & ~isPre]) / (m & ~isA & ~isPre).sum())), 2)}
    FED[per] = {"announcement day": st(isA), "day before": st(isPre), "all other days": {"days": int((m & ~isA & ~isPre).sum()), "avg_pct": round(float(np.mean(r[m & ~isA & ~isPre])) * 100, 3)}}
    yrs = (m.sum()) / 252
    FED[per]["share_of_spy_gain_from_fed_days_pct"] = round(float(np.log1p(r[m & (isA | isPre)]).sum() / np.log1p(r[m]).sum()) * 100, 1)
    FED[per]["fed_days_only_strategy_pct_per_year"] = round(float(np.expm1(np.log1p(r[m & (isA | isPre)] - 0.0002).sum() / yrs)) * 100, 1)
    print("FED", per, json.dumps(FED[per]), flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "overnight": OVN, "fomc": FED, "fomc_dates": [d.strftime("%Y-%m-%d") for d in dates]},
          open("data/calendar_effects.json", "w"), indent=1, default=float)
print("wrote data/calendar_effects.json")
