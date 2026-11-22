"""India momentum basket - VIRTUAL paper bot (from Nov 2026). Research only, not financial advice. India only: alerts go to NTFY_TOPIC_INDIA.
Rules = the version picked on 2009-2018 data in scripts/india_pit.py (survivorship-free NSE backtest 2009-2026: 30.6%/yr before tax,
worst -37.5%; 2019-2026 unseen check 28.4%; expect less live):
  * Universe: the 500 most-traded NSE stocks (120-day median traded value, ETFs excluded, price > Rs 20), re-picked in January and July.
  * Score: (6-month return + 12-month return) / annualised volatility of the last 120 days.
  * First trading day of each month, at the close: hold the top 20, equal weight. A held stock stays while it ranks in the top 30.
  * Crash filter at each reshuffle: if Nifty 50 is below its 100-day average (FILTER_MA; Nov 21 risk test: 100-day cut the worst drop
    from -37.5% to -23.8% and raised returns to 32.6%), sell everything; hold GOLDBEES while gold is above its 100-day average, else a
    liquid fund (~6%/yr). A twin with the original 200-day filter runs alongside (data/paper_india_mom200_state.json, no alerts).
  * Costs 0.30% per buy and per sell. Prices from NSE's daily archive (bhavcopy, cached in R2), splits/bonuses fixed as in the backtest.
Runs every weekday evening IST; catches up any missed days. Paper fills at the rebalance day's close (friends would place orders next day).
State: data/paper_india_mom_state.json. DRY=1: fake data (tests)."""
import os, sys, json, urllib.request
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DRY = os.environ.get("DRY") == "1"
import india_pit as IP
STATE = os.environ.get("STATE", "data/paper_india_mom_state.json")
N, BUF, K, COST, START_EQ = 20, 30, 500, 0.003, 1_000_000.0
FILTER_MA = int(os.environ.get("FILTER_MA", "100"))
LIQ = (1.06) ** (1 / 248) - 1
def load_recent():
    """last ~2.5 years of NSE daily data (C, PC, O, V) with today's days fetched into the R2 cache if missing"""
    if DRY: return fake()
    import r2cache
    days = [d for d in IP.yahoo("^NSEI", "2023-01-01").index]
    now = pd.Timestamp.today(); rows = {}
    for y in range(now.year - 2, now.year + 1):
        key = f"nse/bhav/{y}.json.gz"; cache = r2cache.load(key) or {}
        miss = [d for d in days if d.year == y and str(d.date()) not in cache and d >= now - pd.Timedelta(days=40)]
        for d in miss:
            x = IP.bhav(d)
            if x: cache[str(d.date())] = x
        if miss: r2cache.save(key, cache)
        rows.update({k: v for k, v in cache.items() if v})
    dates = sorted(rows); ix = pd.to_datetime(dates); syms = sorted({s for d in dates for s in rows[d]}); si = {s: i for i, s in enumerate(syms)}
    A = np.full((6, len(dates), len(syms)), np.nan, dtype=np.float64)
    for t, d in enumerate(dates):
        for s, v in rows[d].items(): A[:, t, si[s]] = v
    mk = lambda k: pd.DataFrame(A[k], index=ix, columns=syms)
    return mk(3), mk(4), mk(0), mk(5)
FAKE_SEED = int(os.environ.get("FAKE_SEED", "5"))
def fake(n=700):
    full = pd.bdate_range("2024-09-02", "2026-12-31"); ix = full[full <= pd.Timestamp(os.environ.get("FAKE_END", "2026-11-20"))]; days = len(ix)
    rng = np.random.default_rng(FAKE_SEED); syms = [f"S{i:03d}" for i in range(n)]
    drift = rng.normal(0.0004, 0.0008, n)
    C = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(drift, 0.02, (len(full), n)), axis=0))[:days], index=ix, columns=syms)
    PC = C.shift(1); O = PC * (1 + rng.normal(0, 0.005, (len(full), n))[:days]); V = pd.DataFrame(rng.lognormal(18, 1.0, (len(full), n))[:days], index=ix, columns=syms)
    return C, PC, O, V
def market(C, PC, O, V):
    keep = [s for s in C.columns if not pd.Series([s]).str.contains(IP.ETF_RX, regex=True).iloc[0]]
    C, PC, O, V = (x[keep] for x in (C, PC, O, V))
    R = (C / PC - 1).where(C.notna() & PC.notna() & (PC > 0))
    gap = (O / PC - 1).where((O > 0) & (PC > 0)); ca = ((gap <= -0.18) | (gap >= 0.8) | (R <= -0.30) | (R >= 0.8)).fillna(False)
    R = R.mask(ca, ((C / O - 1).where(O > 0)).clip(-0.2, 0.2)).where(lambda x: x.abs() < 0.6)
    P = (1 + R.fillna(0)).cumprod().where(C.notna()).ffill()
    vol = R.rolling(120, min_periods=80).std() * np.sqrt(248)
    score = (P.pct_change(126) + P.pct_change(252)) / vol
    glitch = (R.abs() > 0.35).rolling(6, min_periods=1).max().fillna(0).astype(bool)
    tv = V.rolling(120, min_periods=60).median()
    return dict(C=C, R=R, score=score, glitch=glitch, tv=tv)
def ext(dates):
    if DRY:
        rng = np.random.default_rng(FAKE_SEED + 9); L = 600; n = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.011, L)))[:len(dates)], index=dates)
        g = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.009, L)))[:len(dates)], index=dates)
        if os.environ.get("FAKE_CRASH"): n.iloc[-60:] = n.iloc[-61] * np.linspace(1, 0.7, 60)
        return n, g
    n = IP.yahoo("^NSEI", "2023-01-01").reindex(dates).ffill(); g = IP.yahoo("GOLDBEES.NS", "2023-01-01").reindex(dates).ffill()
    return n, g
def notify(title, body):
    topic = os.environ.get("NTFY_TOPIC_INDIA")
    if not topic or os.environ.get("NO_NOTIFY"): print("[no ntfy]", title, "\n" + body); return
    try: urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), headers={"Title": title.encode("ascii", "ignore").decode(), "Priority": "high", "Tags": "india,rocket"}), timeout=30); print("ntfy sent")
    except Exception as e: print("ntfy failed", e)
def equity(st): return st["cash"] + sum(st["holdings"].values())
def rebalance(st, M, t, day, nifty_ok, gold_ok):
    C, sc = M["C"], M["score"]; eq0 = equity(st)
    if not st.get("universe") or (day.month in (1, 7) and st.get("universe_asof", "")[:7] != str(day)[:7]):
        row = M["tv"].iloc[t - 1]; row = row[(C.iloc[t - 1] > 20)].dropna().sort_values(ascending=False)
        st["universe"] = list(row.index[:K]); st["universe_asof"] = str(day.date())
    st["inside"] = bool(nifty_ok); st["hide"] = "GOLDBEES" if gold_ok else "LIQUID"
    if st["inside"]:
        s = sc.iloc[t][[x for x in st["universe"] if x in sc.columns]]
        ok = s[np.isfinite(s) & C.iloc[t][s.index].notna() & (C.iloc[t][s.index] > 20) & ~M["glitch"].iloc[t][s.index]].sort_values(ascending=False)
        rank = {x: i for i, x in enumerate(ok.index)}
        kept = [x for x in st["holdings"] if rank.get(x, 1e9) < BUF][:N]
        new = kept + [x for x in ok.index if x not in kept][: N - len(kept)]
    else: new = []
    tgt = {x: eq0 / N for x in new}
    traded = sum(abs(tgt.get(x, 0) - st["holdings"].get(x, 0)) for x in set(tgt) | set(st["holdings"]))
    sells = sorted(x for x in st["holdings"] if x not in tgt); buys = sorted(x for x in tgt if x not in st["holdings"])
    st["holdings"] = tgt; st["cash"] = eq0 - sum(tgt.values()); st["cash"] -= COST * traded
    px = {x: round(float(C.iloc[t][x]), 2) for x in tgt}
    rec = {"day": str(day.date()), "inside": st["inside"], "hide": None if st["inside"] else st["hide"], "sells": sells, "buys": buys, "hold": sorted(tgt),
           "turnover_pct": round(100 * traded / eq0, 1), "cost": round(COST * traded, 0), "equity": round(equity(st), 0),
           "shares_per_1_lakh": {x: max(1, int(round((1e5 / N) / px[x]))) for x in buys}, "price": {x: px[x] for x in tgt}}
    st["rebalances"] = (st.get("rebalances") or [])[-36:] + [rec]; return rec
def alert(rec, st):
    if rec["inside"]:
        lines = [f"Monthly reshuffle ({rec['day']}): hold {len(rec['hold'])} stocks, equal amounts (5% each).",
                 "SELL: " + (", ".join(rec["sells"]) or "none"),
                 "BUY:" + ("".join(f"\n  {x}: ~{rec['shares_per_1_lakh'][x]} shares per Rs 1 lakh (Rs {rec['price'][x]})" for x in rec["buys"]) or " none"),
                 "KEEP: " + (", ".join(x for x in rec["hold"] if x not in rec["buys"]) or "none"),
                 "Then top up / trim so each is ~5% of the momentum money."]
    else: lines = [f"Crash filter ON ({rec['day']}): Nifty is below its {FILTER_MA}-day average.", "SELL all momentum stocks: " + (", ".join(rec["sells"]) or "(already out)"),
                   f"Park the money in {'GOLDBEES (gold is trending up)' if rec['hide'] == 'GOLDBEES' else 'a liquid fund'} until Nifty recovers."]
    h = st.get("history") or []; base = h[0] if h else None
    if base: lines.append(f"Paper account: Rs {rec['equity']:,.0f} (start Rs {START_EQ:,.0f} on {st['start']}); Nifty {h[-1]['nifty'] / base['nifty'] * 100 - 100:+.1f}% since start.")
    lines.append("Place orders next trading day around 3 pm. Paper bot only, not advice.")
    notify(f"India momentum: {'reshuffle' if rec['inside'] else 'CRASH FILTER - go to ' + rec['hide']}", "\n".join(lines))
def run():
    C, PC, O, V = load_recent(); M = market(C, PC, O, V); dates = M["C"].index
    n, g = ext(dates)
    nifty_ok = (n > n.rolling(FILTER_MA).mean()).shift(1, fill_value=False); gold_ok = (g > g.rolling(100).mean()).shift(1, fill_value=False)
    gr = g.pct_change().fillna(0).where(lambda x: x.abs() < 0.15, 0)
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if not st:
        t = len(dates) - 1; day = dates[t]
        st = {"start": str(day.date()), "filter_ma": FILTER_MA, "cash": START_EQ, "holdings": {}, "history": [], "last_day": str(day.date())}
        rec = rebalance(st, M, t, day, nifty_ok.iloc[t], gold_ok.iloc[t]); st["history"].append({"day": str(day.date()), "equity": round(equity(st), 2), "nifty": float(n.iloc[t])})
        print("started:", json.dumps(rec)[:600]); alert(rec, st)
    else:
        last = pd.Timestamp(st["last_day"]); todo = [i for i, d in enumerate(dates) if d > last]
        for t in todo:
            day = dates[t]; R = M["R"].iloc[t]
            for x in list(st["holdings"]):
                r = R.get(x)
                if r is not None and np.isfinite(r): st["holdings"][x] *= 1 + r
                elif M["C"].iloc[max(0, t - 5):t + 1][x].isna().all(): st["cash"] += st["holdings"].pop(x) * (1 - COST)   # not traded for a week: out at last price
            hide_r = LIQ if st.get("inside", True) or st.get("hide") != "GOLDBEES" else float(gr.iloc[t])
            st["cash"] *= 1 + hide_r
            if day.month != pd.Timestamp(st["last_day"]).month:
                rec = rebalance(st, M, t, day, nifty_ok.iloc[t], gold_ok.iloc[t]); print("reshuffle:", json.dumps(rec)[:600]); alert(rec, st)
            st["last_day"] = str(day.date()); st["history"] = (st.get("history") or [])[-800:] + [{"day": str(day.date()), "equity": round(equity(st), 2), "nifty": float(n.iloc[t])}]
        print("processed", len(todo), "new day(s); equity", round(equity(st)), "holdings", len(st["holdings"]))
    st["updated"] = str(pd.Timestamp.now("UTC"))
    if not os.environ.get("NO_SAVE"):
        os.makedirs(os.path.dirname(STATE) or ".", exist_ok=True); json.dump(st, open(STATE, "w"), indent=1, default=float)
    return st
if __name__ == "__main__": run()
