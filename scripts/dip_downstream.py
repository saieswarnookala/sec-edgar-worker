"""Dip bot 'upstream/downstream' export (Nov 27). v3.0 live-like daily rules (stock + ETF dips), point-in-time S&P 500, 1999-2026. Research only.
Writes data/dip_downstream.csv.gz, one row per day:
  dips   = daily return of the dip trades only, idle money earning 0 (trading costs included)
  idle   = share of the account NOT in dip trades that day (free slots)
  full   = today's full bot (dips + Clear Leader / IEF parking), for checking
  park_on, bond_ok, cl, ief, tbill, spy, qqq = parking inputs and plain ETF returns
Any downstream X then gives: dips + idle * X - switching costs. DRY=1: fake data."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/dip_downstream.csv.gz" if not S.DRY else "/tmp/dip_downstream_dry.csv.gz"
kw = dict(fill="close", park="cl", cs=0.0008, ce=0.0003, etf=True)
tr = []; dips, _ = S.sim(bond=False, parkx=np.zeros(len(S.dn), bool), cash_interest=False, trace=tr, **kw)
full, _ = S.sim(bond=True, **kw)
dn = pd.DatetimeIndex(S.dn); idle = pd.Series(1.0, index=dn)
for t, x in tr: idle.iloc[t] = x
q = S.yahoo("QQQ"); qqq = q.reindex(q.index.union(dn)).ffill(limit=5).reindex(dn).pct_change(fill_method=None).fillna(0) if q is not None else pd.Series(0.0, index=dn)
df = pd.DataFrame({"dips": pd.Series(dips, index=dn).pct_change().fillna(0), "idle": idle, "full": pd.Series(full, index=dn).pct_change().fillna(0),
                   "park_on": S.park_on.astype(int), "bond_ok": S.BOND_OK.astype(int), "cl": S.CLR, "ief": S.BOND_R, "tbill": S.TBILL_R, "spy": S.spyr, "qqq": qqq.values}, index=dn)
df = df[df.index >= "1999-01-01"]
chk = (1 + df.dips + df.idle.shift(0) * np.where(df.park_on == 1, df.cl, np.where(df.bond_ok == 1, df.ief, 0))).prod()
print("rows", len(df), "| avg idle", round(df.idle.mean(), 3), "| full bot growth", round((1 + df.full).prod(), 2), "| rebuilt from dips+idle", round(chk, 2), flush=True)
os.makedirs("data", exist_ok=True); df.round(7).to_csv(OUT, compression="gzip")
