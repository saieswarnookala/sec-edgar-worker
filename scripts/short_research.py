"""Short-selling research: price-based short anomalies from the literature, tested on point-in-time S&P 500 (1998-2026).
Monthly-rebalanced equal-weight short books (0.15% cost per side, 1%/yr borrow), optional market-regime gate,
long/short versions, and a market-neutral (beta-hedged) version of our live dip strategy. Not financial advice."""
import sys, json, numpy as np, pandas as pd
OUT0 = sys.argv[1] if len(sys.argv) > 1 else "data/short_research.json"
sys.argv = ["x", "/tmp/_ignore.json"]
exec(open("scripts/short_side.py").read().split("BEARS = {")[0])
exec("BEARS = {" + open("scripts/short_side.py").read().split("BEARS = {")[1].split("spyc = pd.Series")[0])
spyc = pd.Series(spy[START:] / spy[START], index=dates[START:])
ret = Cf[tick].pct_change().values
maxr = pd.DataFrame(ret).rolling(21).max().values                   # lottery / MAX effect
vol = pd.DataFrame(ret).rolling(63).std().values                    # high volatility
mom = (Cf[tick].shift(21) / Cf[tick].shift(252) - 1).values         # 12-1 momentum (losers)
lo52 = (Cf[tick] / Cf[tick].rolling(252, min_periods=200).min()).values   # near 52-week low
mend = np.array([i == D - 1 or dates[i].month != dates[i + 1].month for i in range(D)])

def book(score, N=20, side=-1, gate=None, start=START, long_score=None):
    """Monthly: short the N highest-score members (side -1). If long_score: also long N highest long_score (dollar-neutral)."""
    # positions are held (not re-weighted daily) between monthly rebalances: P&L = notional * (price / entry price - 1)
    eq = 1.0; base = 1.0; w = {}; p0 = {}; out = []
    for t in range(start, D):
        if w:
            pnl = sum(n * (P[min(t, lastv[j]), j] / p0[j] - 1) for j, n in w.items())
            base -= sum(-n for n in w.values() if n < 0) * FEE / 252 * (1 if base > 0 else 0)
            eq = base + pnl
        if mend[t]:
            new = {}
            if (gate is None or gate[t]) and eq > 0:
                c = np.where(M[t] & ~np.isnan(score[t]))[0]
                for j in c[np.argsort(-score[t, c])][:N]: new[j] = side * eq / N
                if long_score is not None:
                    c2 = np.where(M[t] & ~np.isnan(long_score[t]))[0]
                    for j in c2[np.argsort(-long_score[t, c2])][:N]: new[j] = new.get(j, 0) + eq / N
            cur = {j: n * P[min(t, lastv[j]), j] / p0[j] for j, n in w.items()}
            turn = sum(abs(new.get(j, 0) - cur.get(j, 0)) for j in set(new) | set(cur))
            eq -= turn * COST; base = eq; w = new; p0 = {j: P[t, j] for j in new}
        out.append(max(eq, 1e-6))
    return pd.Series(out, index=dates[start:])

R = {"SPY": stats(spyc)}
def add(name, c):
    R[name] = stats(c); print(name, R[name], flush=True); CUR[name] = c
CUR = {}
bear = ~spy200
add("MAX (lottery) short top 20", book(maxr))
add("MAX short top 20, only when SPY < 200d", book(maxr, gate=bear))
add("high-volatility short top 20", book(vol))
add("high-volatility short, only when SPY < 200d", book(vol, gate=bear))
add("momentum losers short bottom 20", book(-mom))
add("momentum losers short, only when SPY < 200d", book(-mom, gate=bear))
add("near 52w low & weak short 20", book(-lo52 + np.where(above200, -9, 0)))
add("long/short momentum (long top 20, short bottom 20)", book(-mom, long_score=mom))
add("long low-vol / short high-vol (20/20)", book(vol, long_score=-vol))
add("long/short momentum, only when SPY < 200d", book(-mom, long_score=mom, gate=bear))
# market-neutral live dip: dip strategy daily returns minus rolling beta * SPY returns (beta from the past year only)
dipc = pd.read_csv("data/dip_curve.csv", index_col=0, parse_dates=True)["realistic"].reindex(dates[START:]).ffill()
rd = dipc.pct_change().fillna(0); rs = spyc.pct_change().fillna(0)
beta = (rd.rolling(252).cov(rs) / rs.rolling(252).var()).shift(1).fillna(0.5).clip(0, 1.5)
R["live_dip_beta_avg"] = round(float(beta.mean()), 2)
add("live dip, market-neutral (short beta x SPY)", (1 + rd - beta * rs - beta * FEE / 252).cumprod())
add("live dip, hedged only when SPY < 200d", (1 + rd - np.where(pd.Series(spy200[START:], index=dates[START:]).shift(1, fill_value=True), 0, beta * (rs + FEE / 252))).cumprod())
add("live dip (unhedged, reference)", dipc / dipc.iloc[0])
json.dump(R, open(OUT0, "w"), indent=1, default=float)
