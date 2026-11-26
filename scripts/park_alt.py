"""Where should the dip bot park spare money when SPY is BELOW its 100-day average? (the Clear Leader leg above it is unchanged)
v3.0 daily rules, point-in-time S&P 500, 1999-2026. Research only, not financial advice.
 A today: IEF when IEF > its 100-day avg, else cash earning 0%
 B today + cash earns T-bill rate (= Robinhood Gold sweep, before its $5/month fee)
 C always T-bills (Gold sweep / SGOV / BIL), no bonds
 D always IEF (no trend filter)
 E TLT (long bonds; VUSTX before 2002) when above its 100-day avg, else T-bills
 F GLD (gold metal, from Nov 2004) when above its 100-day avg, else T-bills
 G IEF or GLD, whichever is above its 100-day avg (IEF first), else T-bills
DRY=1: fake data."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/park_alt.json" if not S.DRY else "/tmp/park_alt_dry.json"
def trend(r):
    lvl = (1 + r.fillna(0)).cumprod().where(r.notna().cumsum() > 0)
    return np.r_[False, (lvl > lvl.rolling(100, min_periods=100).mean()).fillna(False).values[:-1]]
IEF_R, IEF_OK = S.BOND_R.copy(), S.BOND_OK.copy()
tlt = S.chain("TLT", "VUSTX"); gld = S.chain("GLD")
TLT_R, TLT_OK = tlt.fillna(0).values, trend(tlt); GLD_R, GLD_OK = gld.fillna(0).values, trend(gld)
G_R = np.where(IEF_OK, IEF_R, GLD_R); G_OK = IEF_OK | GLD_OK
VARS = {"A today: IEF (filtered) else cash 0%": (IEF_R, IEF_OK, True, False),
        "B today + cash earns T-bills (Gold sweep, before fee)": (IEF_R, IEF_OK, True, True),
        "C always T-bills (Gold sweep / SGOV)": (IEF_R, IEF_OK, False, True),
        "D always IEF (no filter)": (IEF_R, np.ones(S.D if hasattr(S, 'D') else len(S.dn), bool), True, False),
        "E TLT (filtered) else T-bills": (TLT_R, TLT_OK, True, True),
        "F GLD gold (filtered) else T-bills": (GLD_R, GLD_OK, True, True),
        "G IEF or GLD (filtered) else T-bills": (G_R, G_OK, True, True)}
RES = {"note": __doc__}
for fname, fkw in (("live-like", dict(fill="close", park="cl", cs=0.0008, ce=0.0003)), ("realistic", dict(fill="open", park="cl", cs=0.0015, ce=0.0005))):
    RES[fname] = {}
    for nm, (br, ok, bond, ci) in VARS.items():
        S.BOND_R, S.BOND_OK = br, ok
        o = S.summ(*S.sim(etf=True, bond=bond, cash_interest=ci, **fkw)); RES[fname][nm] = o
        print(f"{fname:10s} {nm:58s} " + " | ".join(f"{k} {v.get('per_year_pct', v.get('return_pct'))}%/{v['worst_drop_pct']}" for k, v in o.items() if isinstance(v, dict) and k in ("1999-2026", "2013-2026", "2008 crash", "2022 bear")), flush=True)
    S.BOND_R, S.BOND_OK = IEF_R, IEF_OK
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1)
