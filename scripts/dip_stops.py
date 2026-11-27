"""Stop-loss check for the dip bot (Nov 27). v3.0 daily rules, point-in-time S&P 500, 1999-2026. Research only.
A) per-position stop: sell a dip position at the close once it is down X% from its buy price (else the normal exits)
B) account breaker: when the whole account is X% below its peak, sell everything into T-bills, buy back in when
   (i) SPY closes back above its 100-day average, (ii) after 20 trading days, or (iii) the strategy (tracked on paper) recovers 10% from its low.
   The live bot today does NOT sell at its 35% breaker: it stops trading and alerts. DRY=1: fake data."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/dip_stops.json" if not S.DRY else "/tmp/dip_stops_dry.json"
dn = pd.DatetimeIndex(S.dn)
def st(curve):
    c = pd.Series(curve, index=dn); c = c[c.index >= "1999-01-01"]; r = c.pct_change().fillna(0)
    def cg(a, b):
        x = r.loc[a:b]; return round(((1 + x).prod() ** (365.25 / max((x.index[-1] - x.index[0]).days, 1)) - 1) * 100, 1)
    n = (1 + r).cumprod()
    return {"cagr": cg("1999", "2100"), "worst": round(float((n / n.cummax() - 1).min()) * 100, 1), "1999-2012": cg("1999", "2012"), "2013-2026": cg("2013", "2100")}
RES = {"note": __doc__}
for fname, kw in (("live-like", dict(fill="close", park="cl", cs=0.0008, ce=0.0003, etf=True, bond=True)), ("realistic", dict(fill="open", park="cl", cs=0.0015, ce=0.0005, etf=True, bond=True))):
    A = {}
    for x in (None, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.40):
        c, tr = S.sim(stop=x, **kw); row = st(c)
        rets = np.array([z[2] for z in tr]); row.update({"trades": len(tr), "win_pct": round(float((rets > 0).mean()) * 100, 1), "avg_trade_pct": round(float(rets.mean()) * 100, 2), "worst_trade_pct": round(float(rets.min()) * 100, 1)})
        A["no stop" if x is None else f"stop -{int(x*100)}%"] = row
        print(fname, "per-position", "none" if x is None else x, row, flush=True)
    base, _ = S.sim(**kw); c = pd.Series(base, index=dn); c = c[c.index >= "1999-01-01"]; r = c.pct_change().fillna(0).values
    idx = c.index; tb = pd.Series(S.TBILL_R, index=dn).reindex(idx).fillna(0).values; spy_ok = pd.Series(S.park_on, index=dn).reindex(idx).fillna(False).values
    B = {}
    for th in (0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40):
        for mode in ("SPY above 100-day avg", "after 20 trading days", "strategy recovers 10% from its low"):
            E, pk, out_, since, shadow, slow, trig, days_out = 1.0, 1.0, False, 0, 1.0, 1.0, 0, 0; nav = []
            for i in range(len(r)):
                shadow *= 1 + r[i]; slow = min(slow, shadow)
                if out_:
                    E *= 1 + tb[i]; since += 1; days_out += 1
                    back = spy_ok[i] if mode.startswith("SPY") else since >= 20 if mode.startswith("after") else shadow >= slow * 1.10
                    if back: out_ = False; pk = E                                  # restart the peak after buying back in
                else:
                    E *= 1 + r[i]; pk = max(pk, E)
                    if E <= pk * (1 - th): out_, since, trig = True, 0, trig + 1; shadow = slow = 1.0; E *= 1 - 0.001
                nav.append(E)
            n = pd.Series(nav, index=idx); rr = n.pct_change().fillna(nav[0] - 1)
            def cg(a, b):
                x = rr.loc[a:b]; return round(((1 + x).prod() ** (365.25 / max((x.index[-1] - x.index[0]).days, 1)) - 1) * 100, 1)
            B[f"breaker {int(th*100)}%, back in when {mode}"] = {"cagr": cg("1999", "2100"), "worst": round(float((n / n.cummax() - 1).min()) * 100, 1), "1999-2012": cg("1999", "2012"), "2013-2026": cg("2013", "2100"), "times_triggered": trig, "days_in_cash": days_out}
            print(fname, "breaker", th, mode, B[f"breaker {int(th*100)}%, back in when {mode}"], flush=True)
    B["no breaker"] = st(base)
    RES[fname] = {"per_position_stop": A, "account_breaker": B}
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1)
