"""India Alpha 50 (our version) - VIRTUAL paper bot 14 (from Nov 22 2026). Research only, not financial advice. India only: alerts go to NTFY_TOPIC_INDIA.
Rules = the rebuilt Alpha 50 tested in scripts/india_pit.py MODE=factor (survivorship-free NSE backtest 2009-2026: 22.0%/yr before tax, worst -47%;
NOTE the official Nifty Alpha 50 index earned less recently: 5y 11.6% vs our 18.2%; plan on 17-20%):
  * Universe: the 300 most-traded NSE stocks (120-day median traded value, ETFs excluded, price > Rs 20), re-picked in January and July.
  * Score: 1-year Jensen's alpha vs the Nifty 50 from daily returns (last 252 days, needs 200+ traded days), annualised.
  * First NSE trading day of January, April, July and October, at the close: hold the top 50, equal weight (2% each). No buffer.
  * No crash filter in the main bot. A twin WITH the 100-day Nifty crash filter (gold/liquid while out, checked at the quarterly reshuffle)
    runs alongside (data/paper_india_alpha_filter_state.json, no alerts) - that version is untested, it is here to compare.
  * Costs 0.30% per buy and per sell. Data: NSE daily archive (bhavcopy, cached in R2), splits/bonuses fixed as in the backtest.
Runs every weekday evening IST (same workflow as paper bot 13); catches up missed days. Paper fills at the reshuffle day's close.
State: data/paper_india_alpha_state.json. DRY=1: fake data (tests)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_india_mom as PM
STATE = os.environ.get("STATE", "data/paper_india_alpha_state.json")
N, K, COST, START_EQ = 50, 300, 0.003, 1_000_000.0
FILTER = os.environ.get("FILTER") == "1"; FILTER_MA = 100
LIQ = (1.06) ** (1 / 248) - 1
QMONTHS = (1, 4, 7, 10)
def alpha_scores(M, mret, t, cols):
    """annualised 1-year Jensen's alpha of each column vs Nifty, at row t (same math as india_pit.py factor mode)"""
    if t < 251: return pd.Series(np.nan, index=cols)
    X = M["R"].iloc[t - 251:t + 1][cols].values; m = mret[t - 251:t + 1]; good = np.isfinite(X).sum(0) >= 200
    Xf = np.where(np.isfinite(X), X, 0.0); mm = m - m.mean(); b = (mm[:, None] * (Xf - Xf.mean(0))).sum(0) / (mm ** 2).sum()
    a = (Xf.mean(0) - b * m.mean()) * 248; a[~good] = np.nan
    return pd.Series(a, index=cols)
def rebalance(st, M, mret, t, day, nifty_ok, gold_ok):
    C = M["C"]; eq0 = PM.equity(st)
    if not st.get("universe") or (day.month in (1, 7) and st.get("universe_asof", "")[:7] != str(day)[:7]):
        row = M["tv"].iloc[t - 1]; row = row[(C.iloc[t - 1] > 20)].dropna().sort_values(ascending=False)
        st["universe"] = list(row.index[:K]); st["universe_asof"] = str(day.date())
    st["inside"] = bool(nifty_ok) if FILTER else True; st["hide"] = "GOLDBEES" if gold_ok else "LIQUID"
    if st["inside"]:
        cols = [x for x in st["universe"] if x in C.columns and np.isfinite(C.iloc[t][x]) and not M["glitch"].iloc[t][x]]
        a = alpha_scores(M, mret, t, cols); a = a[np.isfinite(a)].sort_values(ascending=False)
        new = list(a.index[:N]); st["last_alpha"] = {x: round(float(a[x]) * 100, 1) for x in new}
    else: new = []
    tgt = {x: eq0 / N for x in new} if new else {}
    traded = sum(abs(tgt.get(x, 0) - st["holdings"].get(x, 0)) for x in set(tgt) | set(st["holdings"]))
    sells = sorted(x for x in st["holdings"] if x not in tgt); buys = sorted(x for x in tgt if x not in st["holdings"])
    st["holdings"] = tgt; st["cash"] = eq0 - sum(tgt.values()) - COST * traded
    px = {x: round(float(C.iloc[t][x]), 2) for x in tgt}
    rec = {"day": str(day.date()), "inside": st["inside"], "hide": None if st["inside"] else st["hide"], "sells": sells, "buys": buys, "hold": sorted(tgt),
           "turnover_pct": round(100 * traded / eq0, 1), "cost": round(COST * traded, 0), "equity": round(PM.equity(st), 0),
           "shares_per_5_lakh": {x: max(1, int(round((5e5 / N) / px[x]))) for x in buys}, "price": px, "alpha_pct": dict(st.get("last_alpha") or {}) if new else {}}
    st["rebalances"] = (st.get("rebalances") or [])[-24:] + [rec]; return rec
def alert(rec, st):
    if FILTER: return                                              # the twin never alerts
    lines = [f"Quarterly reshuffle ({rec['day']}): hold {len(rec['hold'])} stocks, equal amounts (2% each).",
             f"SELL ({len(rec['sells'])}): " + (", ".join(rec["sells"]) or "none"),
             f"BUY ({len(rec['buys'])}): " + (", ".join(f"{x} ~{rec['shares_per_5_lakh'][x]}/5L" for x in rec["buys"]) or "none"),
             f"KEEP: {len(rec['hold']) - len(rec['buys'])} stocks", "Then top up / trim so each is ~2%. Full list + share calculator on the Sentinel dashboard.",
             "Place orders next trading day. Paper bot only, not advice."]
    PM.notify("India Alpha 50: quarterly reshuffle", "\n".join(lines))
def run():
    C, PC, O, V = PM.load_recent(); M = PM.market(C, PC, O, V); dates = M["C"].index
    n, g = PM.ext(dates); mret = n.pct_change().fillna(0).values
    nifty_ok = (n > n.rolling(FILTER_MA).mean()).shift(1, fill_value=False); gold_ok = (g > g.rolling(100).mean()).shift(1, fill_value=False)
    gr = g.pct_change().fillna(0).where(lambda x: x.abs() < 0.15, 0)
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if not st:
        t = len(dates) - 1; day = dates[t]
        st = {"start": str(day.date()), "crash_filter": FILTER, "cash": START_EQ, "holdings": {}, "history": [], "last_day": str(day.date())}
        rec = rebalance(st, M, mret, t, day, nifty_ok.iloc[t], gold_ok.iloc[t]); st["history"].append({"day": str(day.date()), "equity": round(PM.equity(st), 2), "nifty": float(n.iloc[t])})
        print("started:", json.dumps(rec)[:500]); alert(rec, st)
    else:
        last = pd.Timestamp(st["last_day"]); todo = [i for i, d in enumerate(dates) if d > last]
        for t in todo:
            day = dates[t]; R = M["R"].iloc[t]
            for x in list(st["holdings"]):
                r = R.get(x)
                if r is not None and np.isfinite(r): st["holdings"][x] *= 1 + r
                elif M["C"].iloc[max(0, t - 5):t + 1][x].isna().all(): st["cash"] += st["holdings"].pop(x) * (1 - COST)
            hide_r = LIQ if st.get("inside", True) or st.get("hide") != "GOLDBEES" else float(gr.iloc[t])
            st["cash"] *= 1 + hide_r
            if day.month != pd.Timestamp(st["last_day"]).month and day.month in QMONTHS:
                rec = rebalance(st, M, mret, t, day, nifty_ok.iloc[t], gold_ok.iloc[t]); print("reshuffle:", json.dumps(rec)[:500]); alert(rec, st)
            st["last_day"] = str(day.date()); st["history"] = (st.get("history") or [])[-800:] + [{"day": str(day.date()), "equity": round(PM.equity(st), 2), "nifty": float(n.iloc[t])}]
        print("processed", len(todo), "new day(s); equity", round(PM.equity(st)), "holdings", len(st["holdings"]))
    st["updated"] = str(pd.Timestamp.now("UTC"))
    if not os.environ.get("NO_SAVE"):
        os.makedirs(os.path.dirname(STATE) or ".", exist_ok=True); json.dump(st, open(STATE, "w"), indent=1, default=float)
    return st
if __name__ == "__main__": run()
