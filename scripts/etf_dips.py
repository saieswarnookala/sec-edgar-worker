"""ETF dip sleeve (Nov 14 2026). Research only, not financial advice.
Idea: run the dip bot's logic on ETFs (index, sector, country) to get MORE short trades without single-company blowups.
Rules tested (all need the ETF above its 200-day average; sells when the close gets back above the 5-day average,
or after max-hold days): Connors RSI(2) < 5/10 with close below the 5-day average; 3-day drop >= 3%/5%;
5-day drop >= 5%/8% (dip-bot style). Entry at that day's close (the live bot trades just before the close) or next open.
Money: up to 10 trades at a time, 10% each; idle money in SPY (like the dip bot's parking) or in cash (sleeve alone).
Early half 1999-2012 picks nothing: every version is reported on both halves so you can see what held up.
Cost 0.02% per side (stress 0.05%). Data: Yahoo daily, total-return adjusted."""
import json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd

GROUPS = {"index": ["SPY", "QQQ", "IWM", "DIA", "MDY"],
          "sectors": ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"],
          "countries": ["EFA", "EEM", "EWJ", "EWG", "EWU", "EWC", "EWA", "EWZ", "EWH", "EWT", "EWY", "INDA", "FXI"]}
GROUPS["all"] = GROUPS["index"] + GROUPS["sectors"] + GROUPS["countries"]
COST, STRESS = 0.0002, 0.0005

def yahoo(sym):
    for a in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            q = j["indicators"]["quote"][0]; adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            idx = pd.to_datetime([time.strftime("%Y-%m-%d", time.gmtime(t)) for t in j["timestamp"]])
            df = pd.DataFrame({"o": q["open"], "c": q["close"], "a": adj}, index=idx).dropna()
            df = df[(df.c > 0) & (df.o > 0)]; df = df[~df.index.duplicated()].sort_index()
            return df.a * df.o / df.c, df.a          # adjusted open, adjusted close
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("fail", sym, err, flush=True); return None, None

SYMS = GROUPS["all"]; O, C = {}, {}
for s in SYMS:
    o, c = yahoo(s); time.sleep(0.4)
    if c is not None: O[s], C[s] = o, c
SYMS = [s for s in SYMS if s in C]
dates = C["SPY"].index[C["SPY"].index >= "1999-01-01"]
Cm = pd.DataFrame({s: C[s] for s in SYMS}).reindex(dates); Om = pd.DataFrame({s: O[s] for s in SYMS}).reindex(dates)
print("ETFs", len(SYMS), dates[0].date(), dates[-1].date(), flush=True)
ma200, ma5 = Cm.rolling(200).mean(), Cm.rolling(5).mean()
d = Cm.diff(); up, dn = d.clip(lower=0), (-d).clip(lower=0)
rsi2 = 100 - 100 / (1 + up.ewm(alpha=0.5, adjust=False).mean() / dn.ewm(alpha=0.5, adjust=False).mean().replace(0, np.nan))
r3, r5 = Cm / Cm.shift(3) - 1, Cm / Cm.shift(5) - 1
uptrend = Cm > ma200
SIGS = {"RSI(2)<10 below 5-day avg": ((rsi2 < 10) & (Cm < ma5) & uptrend, rsi2),
        "RSI(2)<5 below 5-day avg": ((rsi2 < 5) & (Cm < ma5) & uptrend, rsi2),
        "3-day drop 3%+": ((r3 <= -0.03) & uptrend, r3), "3-day drop 5%+": ((r3 <= -0.05) & uptrend, r3),
        "5-day drop 5%+": ((r5 <= -0.05) & uptrend, r5), "5-day drop 8%+": ((r5 <= -0.08) & uptrend, r5)}
C_, O_, M5 = Cm.values, Om.values, ma5.values
spy = Cm["SPY"].values; spyr = np.r_[0, spy[1:] / spy[:-1] - 1]
HALF = np.datetime64("2013-01-01"); dn_ = dates.values

def sim(sig, rankby, cols, entry, maxhold, park, cost=COST, slots=10, w=0.10):
    S, R = sig[cols].values, rankby[cols].values; ci = [SYMS.index(c) for c in cols]
    Cc, Oc, Mc = C_[:, ci], O_[:, ci], M5[:, ci]
    pos, pend, eq, curve, trades, held_days = {}, [], 1.0, np.ones(len(dates)), [], 0
    for t in range(1, len(dates)):
        r = 0.0
        for j, p in pos.items():
            r += w * ((Cc[t, j] / (Oc[t, j] if p["start"] == t else Cc[t - 1, j])) - 1)
        if park: r += (1 - w * len(pos)) * spyr[t]
        eq *= 1 + r
        # entries queued for this open were already counted via start==t
        for j in list(pos):
            p = pos[j]; age = t - p["day"]
            if age >= 1 and (Cc[t, j] > Mc[t, j] or age >= maxhold):
                ret = Cc[t, j] / p["px"] - 1 - 2 * cost; eq *= 1 - w * 2 * cost
                trades.append((p["day"], ret, ret - (spy[t] / p["spy"] - 1)))   # vs simply holding SPY over the same days
                del pos[j]
        cand = [j for j in np.flatnonzero(S[t]) if j not in pos and not np.isnan(Cc[t, j])]
        cand.sort(key=lambda j: R[t, j])
        for j in cand[:max(0, slots - len(pos))]:
            if entry == "close": pos[j] = {"day": t, "px": Cc[t, j], "start": -1, "spy": spy[t]}
            elif t + 1 < len(dates) and not np.isnan(Oc[t + 1, j]): pos[j] = {"day": t + 1, "px": Oc[t + 1, j], "start": t + 1, "spy": spy[t]}
        held_days += len(pos) > 0; curve[t] = eq
    out = {}
    for name, m in (("full", np.ones(len(dates), bool)), ("1999-2012", dn_ < HALF), ("2013-2026", dn_ >= HALF)):
        idx = np.flatnonzero(m); c = curve[idx] / curve[idx[0]]; yrs = len(idx) / 252
        s = spy[idx] / spy[idx[0]]
        tr = [x for x in trades if m[x[0]]]
        out[name] = {"per_year_pct": round((c[-1] ** (1 / yrs) - 1) * 100, 1), "worst_drop_pct": round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1),
                     "spy_per_year_pct": round((s[-1] ** (1 / yrs) - 1) * 100, 1), "spy_worst_drop_pct": round(float((s / np.maximum.accumulate(s) - 1).min()) * 100, 1),
                     "trades_per_month": round(len(tr) / (yrs * 12), 1), "win_pct": round(float(np.mean([x[1] > 0 for x in tr])) * 100, 1) if tr else None,
                     "avg_trade_pct": round(float(np.mean([x[1] for x in tr])) * 100, 2) if tr else None,
                     "avg_vs_spy_same_days_pct": round(float(np.mean([x[2] for x in tr])) * 100, 2) if tr else None}
    out["days_with_a_trade_pct"] = round(100 * held_days / len(dates), 1)
    return out

res = []
for g in ("index", "sectors", "countries", "all"):
    cols = [c for c in GROUPS[g] if c in SYMS]
    for sn, (sig, rk) in SIGS.items():
        for entry in ("close", "next open"):
            for mh in (5, 10):
                row = {"group": g, "signal": sn, "entry": entry, "max_hold": mh}
                row["idle_in_spy"] = sim(sig, rk, cols, entry, mh, True)
                row["idle_in_cash"] = sim(sig, rk, cols, entry, mh, False)
                if entry == "close" and mh == 5: row["idle_in_spy_stress_cost"] = sim(sig, rk, cols, entry, mh, True, STRESS)
                res.append(row)
                a = row["idle_in_spy"]
                print(g, sn, entry, mh, "| full", a["full"]["per_year_pct"], a["full"]["worst_drop_pct"], "| early", a["1999-2012"]["per_year_pct"], "late", a["2013-2026"]["per_year_pct"],
                      "| trades/mo", a["full"]["trades_per_month"], "win", a["full"]["win_pct"], "avg", a["full"]["avg_trade_pct"], "vsSPY", a["full"]["avg_vs_spy_same_days_pct"], flush=True)
json.dump({"note": __doc__, "etfs": SYMS, "results": res}, open("data/etf_dips.json", "w"), indent=1)
