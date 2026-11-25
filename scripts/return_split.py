"""Where does the dip bot's return come from? v3.0 daily rules, point-in-time S&P 500, 1999-2026. Research only.
A) full bot (dips + parking ETF / IEF)   B) dips only, idle money in T-bills   C) difference = what parking adds. DRY=1: fake data."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/return_split.json" if not S.DRY else "/tmp/return_split_dry.json"
OFF = np.zeros(S.D, bool) if hasattr(S, "D") else None
RES = {"note": __doc__}
for fname, fkw in (("live-like", dict(fill="close", park="cl", cs=0.0008, ce=0.0003)), ("realistic", dict(fill="open", park="cl", cs=0.0015, ce=0.0005))):
    full = S.summ(*S.sim(etf=True, bond=True, **fkw))
    off = np.zeros(len(S.dn), bool)
    dips = S.summ(*S.sim(etf=True, bond=False, parkx=off, cash_interest=True, **fkw))
    RES[fname] = {"full bot": full, "dips only, rest in T-bills": dips}
    for k, v in RES[fname].items(): print(fname, "|", k, {p: (x.get("per_year_pct"), x.get("worst_drop_pct")) for p, x in v.items() if isinstance(x, dict)}, flush=True)
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1)
