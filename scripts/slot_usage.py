"""How often are all 10 dip slots full? v3.0 daily rules (the live bot's 3:47 run), point-in-time S&P 500, 1999-2026. Research only.
Slot count per day = dip positions (stock + ETF) held at that day's close, from the trade log. DRY=1: fake data."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/slot_usage.json" if not S.DRY else "/tmp/slot_usage_dry.json"
dn = pd.DatetimeIndex(S.dn); T = len(dn)
RES = {"note": __doc__}
for name, kw in (("live-like (v3.0, close fills)", dict(fill="close", park="cl", cs=0.0008, ce=0.0003, etf=True, bond=True)),):
    log = []; S.sim(log=log, **kw)
    occ = np.zeros(T, int)
    for k, j, a, b, *_ in log:
        if k in ("S", "E"): occ[a:b] += 1
    s = pd.Series(occ, index=dn); s = s[s.index >= "1999-06-01"]
    full = s >= 10; starts = full & ~full.shift(1, fill_value=False)
    yrs = len(s) / 252
    by = pd.DataFrame({"full_days": full.groupby(s.index.year).sum(), "full_spells": starts.groupby(s.index.year).sum(), "avg_slots": s.groupby(s.index.year).mean().round(1), "max": s.groupby(s.index.year).max()})
    spell_len = []; n = 0
    for f in full.values:
        if f: n += 1
        elif n: spell_len.append(n); n = 0
    if n: spell_len.append(n)
    RES[name] = {"years": round(yrs, 1), "avg_slots_used": round(float(s.mean()), 1), "pct_days_full": round(float(full.mean()) * 100, 1),
                 "full_days_per_year": round(float(full.sum()) / yrs, 1), "full_spells_per_year": round(float(starts.sum()) / yrs, 1),
                 "median_spell_days": float(np.median(spell_len)) if spell_len else 0, "longest_spell_days": int(max(spell_len)) if spell_len else 0,
                 "years_with_no_full_day": int((by.full_days == 0).sum()),
                 "distribution_pct": {str(i): round(float((s == i).mean()) * 100, 1) for i in range(11)},
                 "by_year": {str(y): {k: (int(v) if k != "avg_slots" else float(v)) for k, v in r.items()} for y, r in by.iterrows()}}
    print(json.dumps({k: v for k, v in RES[name].items() if k != "by_year"}, indent=1)); print(by.to_string(), flush=True)
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1)
