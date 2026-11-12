# v3: same as v2 but a limit-order fill day cannot also take profit that day (no low-then-high assumption); fill needs 0.1% trade-through.

import numpy as np, pandas as pd, json, sys, time, os, urllib.request
# ATR swing test (research only): buy S&P 500 stocks with a direction filter at the next open, sell at a profit target of k x ATR(14),
# optional stop of s x ATR, else at the close after 1-2 days. 10 slots, 0.15% cost per side, point-in-time S&P 500 1998-2026.
REL="https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for fn in ["prices.parquet","membership_intervals.parquet"]:
    if not os.path.exists("/tmp/"+fn): urllib.request.urlretrieve(REL+fn,"/tmp/"+fn)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date","ticker","open","high","low","close","adj_close"])
px["date"]=pd.to_datetime(px.date); px=px[px.date>="1996-06-01"]
mem=pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"]=pd.to_datetime(mem.start); mem["end"]=pd.to_datetime(mem.end)
px=px[px.ticker.isin(set(mem.ticker)|{"SPY"})].copy()
f=px.adj_close/px.close
for c in ["open","high","low"]: px[c]=px[c]*f
dates=pd.DatetimeIndex(sorted(px[px.ticker=="SPY"].date.unique())); T=sorted(px.ticker.unique())
P=lambda v: px.pivot_table(index="date",columns="ticker",values=v).reindex(index=dates,columns=T)
C,O,H,L=P("adj_close"),P("open"),P("high"),P("low"); del px
tick=[t for t in T if t!="SPY"]
M=pd.DataFrame(False,index=dates,columns=tick)
for _,m in mem.iterrows():
    if m.ticker in M.columns:
        e=m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index>=m.start)&(M.index<e),m.ticker]=True
valid=C[tick].notna(); M&=valid&valid.shift(-1,fill_value=False)&valid.shift(-2,fill_value=False)
spy=C["SPY"].ffill(); spyr=spy.pct_change().fillna(0).values
c=C[tick]; pc=c.shift(1)
tr=pd.concat([H[tick]-L[tick],(H[tick]-pc).abs(),(L[tick]-pc).abs()]).groupby(level=0).max().reindex(dates)
atr=tr.rolling(14).mean()
above200=c>c.rolling(200).mean()
rel5=c.pct_change(5).sub(spy.pct_change(5),axis=0)
near20=c>=c.rolling(20).max()*0.98
up_day=c.pct_change()>0
FILT={"dip10 (live dip signal)":(above200&(rel5<=-0.10)).values,"trend+pullback":(above200&(rel5<=-0.05)).values,"trend+momentum":(above200&near20).values,"trend only, down day":(above200&~up_day).values}
SC={"dip10 (live dip signal)":(-rel5).values,"trend+pullback":(-rel5).values,"trend+momentum":rel5.values,"trend only, down day":(-c.pct_change()).values}
Mv=M.values; A=(atr/c).values; Cv,Ov,Hv,Lv=c.values,O[tick].values,H[tick].values,L[tick].values
D=len(dates); START=int(np.searchsorted(dates.values,np.datetime64("1998-01-01"))); SPLIT=int(np.searchsorted(dates.values,np.datetime64("2012-01-01")))
def sim(fk,k,stop,hold,park,COST=0.0015,entry="open"):
    S=FILT[fk]&Mv&np.isfinite(A)&(A>0); R=np.nan_to_num(SC[fk],nan=-9)
    eq=1.0;curve=np.ones(D);pos=[];trs=[]
    for t in range(START,D-1):
        day=0.0;keep=[]
        used=sum(p["w"] for p in pos)
        for p in pos:
            j=p["j"]
            if p["age"]==0:
                ent=Ov[t,j]
                if not np.isfinite(ent) or ent<=0: eq*=1+COST*p["w"]; continue
                if entry=="limit":
                    lim=Cv[t-1,j]*(1-0.5*p["a"])
                    if not (Lv[t,j]<=lim*0.999): eq*=1+COST*p["w"]; continue   # limit filled only if price traded 0.1% through it
                    p["filled_today"]=True
                    ent=min(ent,lim)
                p["e"]=ent;p["tg"]=ent*(1+k*p["a"]);p["st"]=ent*(1-stop*p["a"]) if stop else -1;base=ent
            else: base=Cv[t-1,j]
            hi,lo,cl,op=Hv[t,j],Lv[t,j],Cv[t,j],Ov[t,j]
            ex=None
            if not np.isfinite(cl): ex=base
            else:
                if p["age"]>0 and op>=p["tg"]: ex=op
                elif p["age"]>0 and p["st"]>0 and op<=p["st"]: ex=op
                elif p["st"]>0 and lo<=p["st"]: ex=p["st"]
                elif hi>=p["tg"] and not p.pop("filled_today",False): ex=p["tg"]   # no same-day profit exit on a limit fill (daily bars cannot tell if the high came first)
                elif p["age"]+1>=hold: ex=cl
                p.pop("filled_today",None)
            px_=ex if ex is not None else cl
            g=px_/base-1; day+=p["w"]*g; p["w"]*=(1+g); p["age"]+=1
            if ex is not None: trs.append(px_/p["e"]-1-2*COST); eq_cost=COST*p["w"]; p["done"]=eq_cost
            keep.append(p)
        day+=max(0,1-used)*(park[t])
        eq*=1+day
        newpos=[]
        for p in keep:
            p["w"]/= (1+day)
            if "done" in p: eq*=1-p["done"]
            else: newpos.append(p)
        pos=newpos; used=sum(p["w"] for p in pos); free=10-len(pos)
        if free>0:
            cand=np.where(S[t])[0]
            if len(cand):
                held={p["j"] for p in pos}
                cand=[x for x in cand[np.argsort(-R[t,cand])] if x not in held][:free]
                w=min(0.1,max(0,1-used)/max(len(cand),1))
                for x in cand: pos.append({"j":x,"age":0,"w":w,"a":A[t,x]}); eq*=1-COST*w
        curve[t]=eq
    cv=pd.Series(curve[START:D-1],index=dates[START:D-1])
    cg=lambda s:round(100*((s.iloc[-1]/s.iloc[0])**(252/len(s))-1),1)
    trs=np.array(trs)
    return dict(cagr=cg(cv),dd=round(100*float((cv/cv.cummax()-1).min()),1),A=cg(cv.iloc[:SPLIT-START]),B=cg(cv.iloc[SPLIT-START:]),trades_yr=round(len(trs)/(len(cv)/252)),win=round(100*float((trs>0).mean()),1),avg=round(100*float(trs.mean()),2))
park={"cash":np.zeros(D),"spy":spyr}
sp=pd.Series(spy.values[START:],index=dates[START:]); cg=lambda s:round(100*((s.iloc[-1]/s.iloc[0])**(252/len(s))-1),1)
print("SPY",cg(sp),cg(sp.iloc[:SPLIT-START]),cg(sp.iloc[SPLIT-START:]),flush=True)
res=[]
for fk in FILT:
  for k in [0.25,0.5,1.0,1.5]:
    for stop in [0,2.0]:
      for hold in [1,2,3]:
        for cost in [0.0005,0.0015]:
          for ent in ["open","limit"]:
            r=sim(fk,k,stop,hold,park["spy"],cost,ent); r.update(filter=fk,target_atr=k,stop_atr=stop,hold=hold,cost=cost,entry=ent,park="spy"); res.append(r)
            print(json.dumps(r),flush=True)
os.makedirs("data",exist_ok=True); json.dump({"SPY":{"full":cg(sp),"A_1998_2011":cg(sp.iloc[:SPLIT-START]),"B_2012_2026":cg(sp.iloc[SPLIT-START:])},"results":res},open("data/atr_swing3.json","w"),indent=1)
