"""Future leaders: can simple, no-hindsight rules catch big long-term winners (the next Nvidia)?
Universe: point-in-time S&P 500 members incl. later-delisted stocks (Johnbrick123/sp500-data), 1998-2026.
Strategies (long-only, decided at month-end close, realistic 0.10% cost per side):
  ew      equal weight all members, monthly rebalance (stock-level benchmark)
  mom     top-N by 12-1 month return, equal weight, monthly rebalance
  run     "let winners run": buy top-decile 12-1 momentum stocks within 5% of their 52-week high and above the
          200-day average; never trim winners; sell only on an exit rule (trailing stop from peak or month-end
          close below the 200-day average). New buys are 1/N of the account from cash.
Taxes: Texas, federal ST 24% (held <1 year) / LT 15%, losses offset gains, paid each year-end.
Not financial advice.
"""
import os, json, sys, urllib.request
import numpy as np, pandas as pd

OUT = sys.argv[1] if len(sys.argv) > 1 else "data/future_leaders.json"
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "adj_close"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1996-01-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); T = sorted(px.ticker.unique())
C = px.pivot_table(index="date", columns="ticker", values="adj_close").reindex(index=dates, columns=T); del px
valid = C.notna().values; Cf = C.ffill()
tick = [t for t in T if t != "SPY"]; ti = {t: i for i, t in enumerate(tick)}
M = np.zeros((len(dates), len(tick)), bool)
for _, m in mem.iterrows():
    if m.ticker in ti:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M[(dates >= m.start) & (dates < e), ti[m.ticker]] = True
P = Cf[tick].values; V = valid[:, [T.index(t) for t in tick]]; M &= V
spy = Cf["SPY"].values
mom = (Cf[tick].shift(21) / Cf[tick].shift(252) - 1).values          # 12-1 month momentum
hi52 = (Cf[tick] / Cf[tick].rolling(252, min_periods=200).max()).values
ma200 = (Cf[tick] / Cf[tick].rolling(200).mean()).values
spy_ma = spy / pd.Series(spy).rolling(200).mean().values
# last valid day per stock (delisting) -> forced exit
lastv = np.full(len(tick), len(dates) - 1)
for j in range(len(tick)):
    w = np.where(V[:, j])[0]
    if len(w): lastv[j] = w[-1]
D = len(dates); START = int(np.searchsorted(dates.values, np.datetime64("1998-01-01")))
mend = np.array([i == D - 1 or dates[i].month != dates[i + 1].month for i in range(D)])
COST = 0.001

def run(kind="run", N=20, exit_rule="trail30", trend=False, trend_exit=False, park=False, st=0.24, lt=0.15, start=START, end=D, mom_q=0.9, near_hi=0.95):
    cash = 1.0; lots = {}   # j -> [shares, cost_basis_total, entry_day, peak_price]
    curve = np.empty(end - start); yr_st = yr_lt = 0.0; carry = 0.0; trades = []; taxes_paid = 0.0
    pk = 1.0  # parking (SPY) holdings value when park=True, inside cash for simplicity
    def sell(j, t, frac=1.0):
        nonlocal cash, yr_st, yr_lt
        sh, cb, d0, peak = lots[j]
        price = P[min(t, lastv[j]), j]; q = sh * frac
        proceeds = q * price * (1 - COST); basis = cb * frac; g = proceeds - basis
        if t - d0 >= 252: yr_lt += g
        else: yr_st += g
        cash += proceeds
        if frac >= 0.999999: trades.append((tick[j], int(d0), int(t), proceeds / basis - 1 if basis else 0)); del lots[j]
        else: lots[j] = [sh - q, cb - basis, d0, peak]
    def buy(j, t, amt):
        nonlocal cash
        if amt <= 0: return
        price = P[t, j]; sh = amt * (1 - COST) / price
        if j in lots: s0, c0, d0, pk0 = lots[j]; lots[j] = [s0 + sh, c0 + amt, d0, max(pk0, price)]
        else: lots[j] = [sh, amt, t, price]
        cash -= amt
    for k, t in enumerate(range(start, end)):
        if park and k > 0 and cash > 0: cash *= spy[t] / spy[t - 1]
        # forced exits (delisted) + daily trailing stops
        for j in list(lots):
            price = P[t, j]; lots[j][3] = max(lots[j][3], price)
            if t >= lastv[j]: sell(j, t); continue
            if kind == "run" and exit_rule.startswith("trail") and price <= lots[j][3] * (1 - int(exit_rule[5:]) / 100): sell(j, t)
        if mend[t]:
            elig = M[t] & ~np.isnan(mom[t])
            if kind == "ew" or kind == "mom":
                if kind == "ew": tgt = np.where(elig)[0]
                else:
                    c = np.where(elig)[0]; tgt = c[np.argsort(-mom[t, c])][:N] if not (trend and spy_ma[t] < 1) else np.array([], int)
                eq = cash + sum(l[0] * P[t, j] for j, l in lots.items()); w = 1.0 / max(len(tgt), 1); ts = set(tgt.tolist())
                for j in list(lots):
                    if j not in ts: sell(j, t)
                for j in list(lots):
                    v = lots[j][0] * P[t, j]
                    if v > eq * w * 1.02: sell(j, t, (v - eq * w) / v)
                for j in tgt:
                    v = lots[j][0] * P[t, j] if j in lots else 0.0
                    if v < eq * w * 0.98: buy(j, t, min(eq * w - v, max(cash, 0)))
            else:
                if trend_exit and spy_ma[t] < 1:
                    for j in list(lots): sell(j, t)
                if exit_rule == "ma200":
                    for j in list(lots):
                        if ma200[t, j] < 1: sell(j, t)
                if not (trend and spy_ma[t] < 1):
                    c = np.where(elig)[0]
                    if len(c):
                        thr = np.nanquantile(mom[t, c], mom_q)
                        cand = [j for j in c[np.argsort(-mom[t, c])] if mom[t, j] >= thr and hi52[t, j] >= near_hi and ma200[t, j] > 1 and j not in lots]
                        eq = cash + sum(l[0] * P[t, j] for j, l in lots.items())
                        for j in cand[: max(0, N - len(lots))]:
                            amt = min(eq / N, cash)
                            if amt < eq / N * 0.25: break
                            buy(j, t, amt)
        if t == end - 1 or dates[t].year != dates[t + 1].year:     # year-end taxes
            net_st, net_lt = yr_st, yr_lt
            net = net_st + net_lt + carry
            if net > 0:
                # losses first offset ST then LT
                loss = -carry if carry < 0 else 0
                s = max(net_st - loss, 0); loss = max(loss - net_st, 0); l2 = max(net_lt - loss, 0)
                if net_st < 0: l2 = max(l2 + net_st, 0); s = 0
                if net_lt < 0: s = max(s + net_lt, 0); l2 = 0
                tax = s * st + l2 * lt
                eq = cash + sum(l[0] * P[t, j] for j, l in lots.items())
                if tax > 0 and eq > 0:     # pay tax by scaling everything (approximation)
                    f = 1 - tax / eq; cash *= f
                    for j in lots: lots[j][0] *= f; lots[j][1] *= f
                    taxes_paid += tax
                carry = 0.0
            else: carry = net
            yr_st = yr_lt = 0.0
        curve[k] = cash + sum(l[0] * P[t, j] for j, l in lots.items())
    yrs = (end - start) / 252
    cagr = curve[-1] ** (1 / yrs) - 1
    dd = float((curve / np.maximum.accumulate(curve) - 1).min())
    # liquidation value at end (pay remaining tax on unrealized gains, LT rate if held a year)
    unreal = sum((l[0] * P[end - 1, j] - l[1]) * (lt if end - 1 - l[2] >= 252 else st) for j, l in lots.items() if l[0] * P[end - 1, j] > l[1])
    liq = (curve[-1] - unreal) ** (1 / yrs) - 1 if st or lt else cagr
    tr = sorted(trades, key=lambda x: -x[3])
    return {"cagr": round(cagr * 100, 2), "cagr_liquidated": round(liq * 100, 2), "max_dd": round(dd * 100, 1), "final_x": round(float(curve[-1]), 2),
            "trades": len(trades), "avg_hold_days": round(float(np.mean([x[2] - x[1] for x in trades])) if trades else 0, 0),
            "win_rate": round(float(np.mean([x[3] > 0 for x in trades])) * 100, 1) if trades else None,
            "best": [(n, dates[a].strftime("%Y-%m"), dates[b].strftime("%Y-%m"), round(g * 100)) for n, a, b, g in tr[:8]],
            "open_now": sorted([(tick[j], dates[l[2]].strftime("%Y-%m"), round((l[0] * P[end - 1, j] / l[1] - 1) * 100)) for j, l in lots.items()], key=lambda x: -x[2])[:10]}, curve

def spy_stats(start=START, end=D, tax=0.15):
    c = spy[start:end] / spy[start]; yrs = (end - start) / 252
    return {"cagr": round((c[-1] ** (1 / yrs) - 1) * 100, 2), "cagr_after_tax_held": round(((1 + (c[-1] - 1) * (1 - tax)) ** (1 / yrs) - 1) * 100, 2), "max_dd": round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1)}

res = {"period": f"{dates[START].date()} to {dates[-1].date()}", "spy": spy_stats(), "pre_tax": {}, "after_tax": {}}
cfgs = {"ew": dict(kind="ew"), "mom10": dict(kind="mom", N=10), "mom20": dict(kind="mom", N=20), "mom30": dict(kind="mom", N=30), "mom20_trend": dict(kind="mom", N=20, trend=True)}
for N in (10, 20, 30):
    for ex in ("trail25", "trail35", "ma200"):
        cfgs[f"run{N}_{ex}"] = dict(kind="run", N=N, exit_rule=ex)
cfgs["run20_trail35_trend"] = dict(kind="run", N=20, exit_rule="trail35", trend=True)
cfgs["run20_trail35_park"] = dict(kind="run", N=20, exit_rule="trail35", park=True)
for name, c in cfgs.items():
    r0, _ = run(**c, st=0, lt=0); r1, _ = run(**c)
    res["pre_tax"][name] = r0; res["after_tax"][name] = {k: r1[k] for k in ("cagr", "cagr_liquidated", "max_dd", "final_x")}
    print(name, "pre", r0["cagr"], r0["max_dd"], "| after", r1["cagr"], r1["cagr_liquidated"], "| trades", r0["trades"], "hold", r0["avg_hold_days"], flush=True)
# split check: first half vs second half
MID = int(np.searchsorted(dates.values, np.datetime64("2012-01-01")))
res["halves"] = {"spy": [spy_stats(START, MID), spy_stats(MID, D)]}
for name in ["mom20", "run20_trail35", "run20_ma200", "run10_trail35", "run30_trail35", "ew"]:
    res["halves"][name] = [run(**cfgs[name], st=0, lt=0, start=START, end=MID)[0]["cagr"], run(**cfgs[name], st=0, lt=0, start=MID, end=D)[0]["cagr"]]
print(json.dumps(res["halves"]))
json.dump(res, open(OUT, "w"), indent=1, default=str)
