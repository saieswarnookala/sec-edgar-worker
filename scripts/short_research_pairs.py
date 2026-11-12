import sys, numpy as np, pandas as pd
sys.argv=["x","/tmp/fl/s.json"]
exec(open("scripts/short_research.py").read().split('R = {"SPY"')[0])
rs = spyc.pct_change().fillna(0)
def cg(c): c=c/c.iloc[0]; return round((c.iloc[-1]**(252/len(c))-1)*100,1), round(float((c/c.cummax()-1).min())*100,1)
mid = spyc.index >= "2012-01-01"
for name, sc in [("MAX lottery", maxr), ("high volatility", vol), ("momentum losers", -mom), ("near 52w low & weak", -lo52 + np.where(above200, -9, 0))]:
    b = book(sc, side=1); rb = b.pct_change().fillna(0)
    pair = (1 + rs - rb - FEE / 252).cumprod()        # long SPY, short the anomaly basket (market-neutral)
    p = rs - rb - FEE/252
    h1 = (1+p[~mid]).cumprod(); h2 = (1+p[mid]).cumprod()
    print(f"{name:22s} basket {cg(b)}  long-SPY/short-basket {cg(pair)}  halves {cg(h1)[0]} / {cg(h2)[0]}")
