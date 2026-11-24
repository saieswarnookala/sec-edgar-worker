"""India bot (from Nov 18 2026), separate from the US bots. One bot: before-close orders at ~3:05 pm IST (MODE=close) plus an 8:15 am
IST status message (MODE=morning: holdings, watchlist, account; no orders). MODE=open (next-open variant) is kept only for manual tests. the best India dip strategy, virtual money, no broker. Research only, not financial advice.
Runs every NSE trading day after the close (GitHub Actions ~6 pm IST). Sends a phone alert (ntfy) with the orders to place
at the NEXT morning's open (9:15 am IST), so anyone can follow it by hand; the bot fills its own virtual orders at that open.

Rules (backtest 2008-2026, realistic next-open fills: ~16.3%/yr before tax, worst drop ~-21%, Nifty 50 9.3% / -59%):
- Universe: the 200 most-traded Nifty 500 stocks (120-session median traded value), re-picked every Jan and Jul; price > Rs 20.
- Buy: still above its 200-day average, fell 12%+ MORE than the Nifty 50 over 5 sessions, 5-day volume <= 2x normal,
  no 35%+ one-day jump in the last 6 sessions (data glitch / corporate action). Biggest falls first, 10 slots x 10%.
- Sell: close back above its 5-day average (after >= 1 session) or after 5 sessions.
- Idle money: NIFTYBEES while the Nifty 50 is above its 150-day average; else GOLDBEES if gold is above its 100-day
  average; else a liquid fund (LIQUIDBEES; modelled as cash earning ~6%/yr). 2% kept in cash.
- Costs (virtual): 0.30% per side for stocks (STT, stamp, brokerage, spread), 0.15% for ETFs. Whole shares only.
India Bot A = MODE=open (after-close run ~6 pm IST, orders for the next open; backtest 'realistic'
16.3%/yr); India Bot B = MODE=close (before-close run ~3:05 pm IST, orders filled at once at the latest price, like placing them before
the 3:30 pm close; backtest close fills 18.3%/yr before costs differences). Today's volume is partial in the before-close run. State: data/paper_india_state.json. DRY_FAKE=1 runs on made-up prices (tests)."""
import os, sys, io, json, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATE = os.environ.get("STATE", "data/paper_india_state.json")
START_CASH, SLOTS, W, BUFFER = 1_000_000.0, 10, 0.10, 0.02
DIP, TREND, LOOK, HOLD, VOLX, MINPX, TOP = 0.12, 200, 5, 5, 2.0, 20.0, 200
COST_S, COST_E, LIQ = 0.003, 0.0015, (1.06) ** (1 / 248) - 1
NIFTY_ETF, GOLD_ETF, LIQ_ETF = "NIFTYBEES", "GOLDBEES", "LIQUIDBEES"
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}

def get(url, tries=4):
    err = None
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("fail", url[:100], err, flush=True); return None
def yahoo(sym):
    b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=3y&interval=1d&events=div%2Csplit")
    if not b: return None
    try:
        j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]["quote"][0]
        adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
        idx = pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None).normalize()
        df = pd.DataFrame({"c": adj, "rc": q["close"], "o": q["open"], "v": q["volume"]}, index=idx)
        df = df[~df.index.duplicated(keep="last")].dropna(subset=["c", "rc"]); df = df[(df.c > 0) & (df.rc > 0)]
        df["o"] = df.o * df.c / df.rc
        df.attrs["quote_time"] = j.get("meta", {}).get("regularMarketTime")
        return df
    except Exception as e: print("parse", sym, e, flush=True); return None
def universe():
    for u in ["https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv", "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"]:
        b = get(u)
        if b:
            try:
                syms = sorted(set(pd.read_csv(io.BytesIO(b)).Symbol.dropna().astype(str)))
                if len(syms) >= 400: return syms
            except Exception as e: print("csv", e, flush=True)
    raise SystemExit("could not load the Nifty 500 list")

def fake_market(days=420, n=60, seed=1):
    """made-up prices for tests: random walks, a few planted dips"""
    rng = np.random.default_rng(seed); idx = pd.bdate_range(end=pd.Timestamp(os.environ.get("FAKE_TODAY", "2026-11-17")), periods=days)
    def walk(vol, drift=0.0004):
        c = 100 * np.exp(np.cumsum(rng.normal(drift, vol, days)));
        return pd.DataFrame({"c": c, "rc": c, "o": c * (1 + rng.normal(0, 0.003, days)), "v": rng.lognormal(13, 0.3, days)}, index=idx)
    px = {f"S{i:02d}": walk(0.018, 0.0012) for i in range(n)}
    for i in range(5):                                       # planted dips in the last 5 sessions on strong stocks
        d = px[f"S{i:02d}"]; d.iloc[-5:, 0] *= np.linspace(0.97, 0.84, 5); d.iloc[-5:, 1] = d.iloc[-5:, 0]
    return px, walk(0.009), walk(0.008), walk(0.0001, 0.0)

def load_market():
    if os.environ.get("DRY_FAKE"):
        px, nifty, nb, gb = fake_market(); return px, nifty, nb, gb, None
    syms = universe(); print(len(syms), "Nifty 500 symbols", flush=True)
    nifty = yahoo("^NSEI"); nb = yahoo(NIFTY_ETF + ".NS"); gb = yahoo(GOLD_ETF + ".NS")
    if nifty is None or nb is None or gb is None: raise SystemExit("could not load Nifty / NIFTYBEES / GOLDBEES from Yahoo")
    px, miss = {}, []
    for i, s in enumerate(syms):
        d = yahoo(s + ".NS")
        if d is not None and len(d) > 260: px[s] = d
        else: miss.append(s)
        time.sleep(0.25)
        if i % 100 == 0: print(i, "loaded", len(px), flush=True)
    print("stocks with 1y+ history:", len(px), "| missing:", len(miss), miss[:15], flush=True)
    if len(px) < 350: raise SystemExit(f"only {len(px)} stocks loaded - Yahoo problem, not trading on partial data")
    return px, nifty, nb, gb, miss

def signals(px, nifty, nb, gb):
    dates = nifty.index; today = dates[-1]
    C = pd.DataFrame({s: d.c for s, d in px.items()}).reindex(dates); RC = pd.DataFrame({s: d.rc for s, d in px.items()}).reindex(dates)
    V = pd.DataFrame({s: d.v for s, d in px.items()}).reindex(dates); O = pd.DataFrame({s: d.o for s, d in px.items()}).reindex(dates)
    Cf = C.ffill(); n = nifty.c.reindex(dates).ffill()
    # members: top 200 by 120-session median traded value on the last session before this Jan/Jul
    half_start = pd.Timestamp(today.year, 1 if today.month < 7 else 7, 1); prev = dates[dates < half_start]
    tv = (RC * V).rolling(120, min_periods=60).median()
    ref = prev[-1] if len(prev) else dates[0]
    members = set(tv.loc[ref].dropna().sort_values(ascending=False).index[:TOP])
    last = {}
    for s in C.columns:
        c = Cf[s]
        if pd.isna(C[s].iloc[-1]): continue
        last[s] = {"close": float(c.iloc[-1]), "raw": float(RC[s].iloc[-1]), "open": float(O[s].iloc[-1]) if pd.notna(O[s].iloc[-1]) else None,
                   "ma5": float(c.iloc[-5:].mean()), "ma200": float(c.iloc[-TREND:].mean()) if c.notna().sum() >= TREND else None}
    r5 = Cf.iloc[-1] / Cf.iloc[-1 - LOOK] - 1; n5 = n.iloc[-1] / n.iloc[-1 - LOOK] - 1; rel = r5 - n5
    vr = V.iloc[-5:].mean() / V.iloc[-55:-5].mean()
    glitch = (Cf.pct_change().iloc[-6:].abs() > 0.35).any()
    dips = []
    for s in members:
        L = last.get(s)
        if not L or L["ma200"] is None: continue
        if L["close"] > L["ma200"] and rel[s] <= -DIP and L["raw"] > MINPX and not (vr[s] > VOLX) and not glitch[s]:
            dips.append({"symbol": s, "rel_pct": round(float(rel[s]) * 100, 1), "own_pct": round(float(r5[s]) * 100, 1), "close": round(L["close"], 2), "raw_close": round(L["raw"], 2)})
    dips.sort(key=lambda x: x["rel_pct"])
    watch = []
    for s in members:
        L = last.get(s)
        if L and L["ma200"] and L["close"] > L["ma200"] and -DIP < rel[s] <= -0.08 and L["raw"] > MINPX and not glitch[s]:
            watch.append({"symbol": s, "rel_pct": round(float(rel[s]) * 100, 1), "own_pct": round(float(r5[s]) * 100, 1)})
    watch.sort(key=lambda x: x["rel_pct"])
    ntrend = n.iloc[-1] > n.iloc[-150:].mean(); g = gb.c.reindex(dates).ffill(); gtrend = g.iloc[-1] > g.iloc[-100:].mean()
    park = NIFTY_ETF if ntrend else (GOLD_ETF if gtrend else LIQ_ETF)
    etf = {NIFTY_ETF: {"close": float(nb.c.reindex(dates).ffill().iloc[-1]), "raw": float(nb.rc.reindex(dates).ffill().iloc[-1]), "open": float(nb.o.reindex(dates).iloc[-1]) if pd.notna(nb.o.reindex(dates).iloc[-1]) else None},
           GOLD_ETF: {"close": float(g.iloc[-1]), "raw": float(gb.rc.reindex(dates).ffill().iloc[-1]), "open": float(gb.o.reindex(dates).iloc[-1]) if pd.notna(gb.o.reindex(dates).iloc[-1]) else None}}
    return {"today": str(today.date()), "dates": [str(d.date()) for d in dates[-10:]], "last": last, "etf": etf, "dips": dips, "watch": watch, "nifty5_pct": round(float(n5) * 100, 1),
            "nifty_close": round(float(n.iloc[-1]), 1), "nifty_trend": bool(ntrend), "gold_trend": bool(gtrend), "park": park, "members": len(members)}

def px_of(sig, s, field="close"):
    if s in sig["etf"]: return sig["etf"][s][field] or sig["etf"][s]["close"]
    L = sig["last"].get(s); return (L[field] or L["close"]) if L else None

def fill(st, sig, orders, field, today):
    """execute orders at today's open or close price (sells first); returns what happened"""
    done = []
    for o in sorted(orders, key=lambda x: x["side"] != "sell"):
        p = px_of(sig, o["symbol"], field)
        if p is None: done.append(f"NOT FILLED {o['side']} {o['symbol']}: no price today"); continue
        c = COST_E if o["symbol"] in (NIFTY_ETF, GOLD_ETF) else COST_S
        if o["side"] == "sell":
            if o["symbol"] in st["park"]:
                q = min(int(o.get("qty") or st["park"][o["symbol"]]), st["park"][o["symbol"]]); st["park"][o["symbol"]] -= q
                if st["park"][o["symbol"]] <= 0: st["park"].pop(o["symbol"])
                st["cash"] += q * p * (1 - c); done.append(f"SOLD {q} {o['symbol']} @ {p:.2f}"); continue
            for ps in [x for x in st["positions"] if x["symbol"] == o["symbol"]]:
                st["cash"] += ps["qty"] * p * (1 - c); st["positions"].remove(ps)
                st["trades"].append({"symbol": ps["symbol"], "entry_day": ps["entry_day"], "exit_day": today, "ret_pct": round((p * (1 - c) / (ps["entry_px"] * (1 + c)) - 1) * 100, 2), "why": o.get("why")})
                done.append(f"SOLD {ps['qty']} {ps['symbol']} @ {p:.2f}")
        elif o["symbol"] == LIQ_ETF:
            amt = min(o["inr"], st["cash"]); st["cash"] -= amt; st["liquid"] += amt; done.append(f"MOVED Rs {amt:,.0f} to liquid fund")
        elif o["symbol"] == "LIQUID_OUT":
            amt = min(o["inr"], st["liquid"]); st["liquid"] -= amt; st["cash"] += amt; done.append(f"TOOK Rs {amt:,.0f} out of liquid fund")
        else:
            q = int(min(o["inr"], st["cash"]) // (p * (1 + c)))
            if q < 1: done.append(f"NOT FILLED BUY {o['symbol']}: not enough cash"); continue
            st["cash"] -= q * p * (1 + c)
            if o["symbol"] in (NIFTY_ETF, GOLD_ETF): st["park"][o["symbol"]] = st["park"].get(o["symbol"], 0) + q
            else: st["positions"].append({"symbol": o["symbol"], "qty": q, "entry_px": p, "entry_day": today, "dip_pct": o.get("dip_pct")})
            done.append(f"BOUGHT {q} {o['symbol']} @ {p:.2f}")
    return done

def step(state, sig, mode="open"):
    """one trading day. mode 'open': fill yesterday's orders at today's open, value at close, plan orders for tomorrow's open.
    mode 'close': plan from the latest (pre-close) prices and fill at once at those prices, like a person placing orders at ~3:10 pm."""
    st = state or {"cash": START_CASH, "liquid": 0.0, "positions": [], "park": {}, "pending": [], "trades": [], "history": [], "started": sig["today"]}
    today, done = sig["today"], []
    if st["history"] and st["history"][-1]["day"] >= today: return st, None            # already ran for this session
    if st["liquid"]: st["liquid"] *= 1 + LIQ                                                # liquid fund accrual for the day
    if mode == "open": done = fill(st, sig, st.get("pending", []), "open", today); st["pending"] = []
    # 2) value at today's close
    val = lambda s, q: q * (px_of(sig, s) or 0)
    stock_val = sum(val(p["symbol"], p["qty"]) for p in st["positions"]); park_val = sum(val(s, q) for s, q in st["park"].items())
    equity = st["cash"] + st["liquid"] + stock_val + park_val
    # 3) plan for tomorrow's open
    orders, sdays = [], sig["dates"]
    keep = []
    for ps in st["positions"]:
        L = sig["last"].get(ps["symbol"]); age = len([d for d in sdays if d > ps["entry_day"]])
        if L is None: keep.append(ps); continue
        if age >= 1 and L["close"] > L["ma5"]: orders.append({"side": "sell", "symbol": ps["symbol"], "qty": ps["qty"], "why": f"bounced above its 5-day average (held {age} day{'s' if age != 1 else ''})"})
        elif age >= HOLD: orders.append({"side": "sell", "symbol": ps["symbol"], "qty": ps["qty"], "why": f"held {age} days (max {HOLD})"})
        else: keep.append(ps)
    held = {p["symbol"] for p in keep}; free = SLOTS - len(keep); buys = []
    for d in sig["dips"]:
        if free <= 0: d["skip"] = f"all {SLOTS} slots used"; continue
        if d["symbol"] in held: d["skip"] = "already own it"; continue
        q = int(W * equity // d["raw_close"])
        if q < 1: d["skip"] = "slot too small for 1 share"; continue
        buys.append({"side": "buy", "symbol": d["symbol"], "inr": W * equity, "approx_qty": q, "dip_pct": d["rel_pct"], "why": f"fell {abs(d['rel_pct'])}% more than Nifty in 5 days"}); free -= 1; d["skip"] = None
    orders += buys
    # parking target = what's left after stocks, minus a 2% buffer
    keep_val = sum(val(p["symbol"], p["qty"]) for p in keep); target = max(0.0, equity * (1 - BUFFER) - keep_val - sum(b["inr"] for b in buys))
    want = sig["park"]
    for s, q in list(st["park"].items()):
        if s != want: orders.append({"side": "sell", "symbol": s, "qty": q, "why": f"switch parking to {want}"})
    if want == LIQ_ETF:
        if abs(target - st["liquid"]) > 0.05 * equity:
            orders.append({"side": "buy", "symbol": LIQ_ETF, "inr": target - st["liquid"], "why": "park idle money in a liquid fund (Nifty and gold both below trend)"} if target > st["liquid"]
                          else {"side": "buy", "symbol": "LIQUID_OUT", "inr": st["liquid"] - target, "why": "take money out of the liquid fund for stock buys"})
    else:
        if st["liquid"] > 0: orders.append({"side": "buy", "symbol": "LIQUID_OUT", "inr": st["liquid"], "why": f"liquid fund -> {want}"})
        cur = val(want, st["park"].get(want, 0)); gap = target - cur; p = px_of(sig, want)
        if gap > 0.05 * equity: orders.append({"side": "buy", "symbol": want, "inr": gap, "approx_qty": int(gap // p), "why": "park idle money (" + ("Nifty above its 150-day average" if want == NIFTY_ETF else "Nifty below trend, gold above its 100-day average") + ")"})
        elif gap < -0.05 * equity and st["park"].get(want):
            q = min(st["park"][want], int(-gap // p) + 1); orders.append({"side": "sell", "symbol": want, "qty": q, "why": "free cash for stock buys", "partial": True})
    if mode == "close":
        now = fill(st, sig, orders, "close", today); done += now; st["pending"] = []
        stock_val = sum(val(p["symbol"], p["qty"]) for p in st["positions"]); park_val = sum(val(s_, q) for s_, q in st["park"].items())
        equity = st["cash"] + st["liquid"] + stock_val + park_val
    else: st["pending"] = orders
    st["history"].append({"day": today, "equity": round(equity, 2), "nifty": sig["nifty_close"], "cash": round(st["cash"], 2), "liquid": round(st["liquid"], 2),
                          "stocks": len(st["positions"]), "park": dict(st["park"]), "park_target": want, "dips": len(sig["dips"]), "filled": done, "orders": len(orders)})
    st["history"] = st["history"][-800:]; st["trades"] = st["trades"][-400:]
    return st, {"done": done, "orders": orders, "equity": equity, "stock_val": stock_val, "park_val": park_val}

def fmt(sig, st, r, mode="open", other=None):
    inr = lambda x: f"Rs {x:,.0f}"
    h0 = st["history"][0]; eq = r["equity"]; ret = (eq / START_CASH - 1) * 100; nret = (sig["nifty_close"] / h0["nifty"] - 1) * 100
    L = [f"1) STOCKS PICKED (top 200 NSE, down 12%+ vs Nifty in 5 days, still above 200-day trend)", f"   Nifty last 5 days: {sig['nifty5_pct']:+.1f}%"]
    if not sig["dips"]: L.append("   none today")
    for d in sig["dips"][:12]:
        L.append(f"   {d['symbol']} {d['own_pct']:+.1f}% (Nifty {sig['nifty5_pct']:+.1f}%) -> " + ("BUY" if not d.get("skip") else "skip: " + d["skip"]))
    L += ["", "2) ORDERS TO PLACE NOW (before the 3:30 pm IST close, at about these prices)" if mode == "close" else "2) ORDERS FOR TOMORROW'S OPEN (9:15 am IST)"]
    if not r["orders"]: L.append("   none: nothing to sell, no new dips, parking already right")
    for o in r["orders"]:
        if o["symbol"] == LIQ_ETF: L.append(f"   BUY liquid fund ({LIQ_ETF}) {inr(o['inr'])}\n     why: {o['why']}")
        elif o["symbol"] == "LIQUID_OUT": L.append(f"   SELL liquid fund {inr(o['inr'])}\n     why: {o['why']}")
        elif o["side"] == "sell": L.append(f"   SELL {o['qty']} {o['symbol']}\n     why: {o['why']}")
        else: L.append(f"   BUY ~{o.get('approx_qty', '?')} {o['symbol']} (~{inr(o['inr'])})\n     why: {o['why']}")
    L += ["", "3) RESULT (virtual Rs 10 lakh, started " + st["started"] + ")"]
    if r["done"]: L.append(("   Filled now: " if mode == "close" else "   Filled at today's open: ") + "; ".join(r["done"][:8]))
    L.append(f"   Dip stocks held: {len(st['positions'])} of {SLOTS} | parking: {', '.join(f'{q} {s}' for s, q in st['park'].items()) or 'none'}{' + liquid ' + inr(st['liquid']) if st['liquid'] > 1 else ''}")
    L.append(f"   Idle money rule now: {sig['park']} ({'Nifty above 150-day avg' if sig['nifty_trend'] else ('Nifty below trend, gold above 100-day avg' if sig['gold_trend'] else 'Nifty and gold below trend')})")
    L.append(f"   Account: {inr(eq)} ({ret:+.2f}%) vs Nifty 50 {nret:+.2f}% since start | cash {inr(st['cash'])}")
    if other: L.append(f"   {other['name']}: {inr(other['equity'])} ({(other['equity'] / START_CASH - 1) * 100:+.2f}%)")
    L.append(f"   Data: NSE {'prices at ' + sig['quote_ist'] + ' IST' if mode == 'close' else 'close ' + sig['today']}")
    title = f"{'INDIA BOT' if mode == 'close' else 'INDIA BOT (next-open test)'} {sig['today']}: {len(r['orders'])} order{'s' if len(r['orders']) != 1 else ''} {'- place before 3:30 pm IST' if mode == 'close' else 'for tomorrow'} | buys {', '.join(o['symbol'] for o in r['orders'] if o['side'] == 'buy' and o['symbol'] not in (LIQ_ETF, 'LIQUID_OUT', NIFTY_ETF, GOLD_ETF)) or 'none'}"
    return title, "\n".join(L)

def notify(title, body):
    topic = os.environ.get("NTFY_TOPIC_INDIA")               # India alerts only: never the US topic
    if not topic or os.environ.get("NO_NOTIFY"): print("[no ntfy: set the NTFY_TOPIC_INDIA secret]" if not topic else "[no ntfy]", title); return
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), headers={"Title": title.encode("ascii", "ignore").decode(), "Priority": "high", "Tags": "india,chart_with_upwards_trend"}), timeout=30)
        print("ntfy sent", flush=True)
    except Exception as e: print("ntfy failed", e, flush=True)

def morning(sig, st):
    """8:15 am IST status from the India bot: holdings, account vs Nifty, watchlist. No orders - those come at ~3:05 pm."""
    inr = lambda x: f"Rs {x:,.0f}"
    L = ["1) HOLDING NOW"]
    for p in (st or {}).get("positions", []):
        c = px_of(sig, p["symbol"]); L.append(f"   {p['symbol']}: {p['qty']} bought {p['entry_day']} @ {p['entry_px']:.2f}, now {c:.2f} ({(c / p['entry_px'] - 1) * 100:+.1f}%)" if c else f"   {p['symbol']}: {p['qty']} (no price)")
    if not (st or {}).get("positions"): L.append("   no dip stocks")
    park = (st or {}).get("park", {}); L.append(f"   parking: {', '.join(f'{q} {s_}' for s_, q in park.items()) or 'none'}{' + liquid fund ' + inr(st['liquid']) if st and st.get('liquid', 0) > 1 else ''}")
    L += ["", "2) WATCHLIST (8-12% worse than Nifty over 5 days, above 200-day trend; becomes a buy if it reaches 12% worse by ~3 pm)"]
    watch = sig.get("watch", [])
    for w in watch[:10]: L.append(f"   {w['symbol']} {w['own_pct']:+.1f}% (Nifty {sig['nifty5_pct']:+.1f}%), {abs(w['rel_pct'])}% worse than Nifty")
    if not watch: L.append("   none close to the trigger")
    L += ["", "3) ACCOUNT"]
    if st and st.get("history"):
        h = st["history"]; eq = h[-1]["equity"]; nret = (sig["nifty_close"] / h[0]["nifty"] - 1) * 100
        L.append(f"   {inr(eq)} ({(eq / START_CASH - 1) * 100:+.2f}%) vs Nifty 50 {nret:+.2f}% since {st['started']}")
        if len(h) > 1: L.append(f"   last change: {(h[-1]['equity'] / h[-2]['equity'] - 1) * 100:+.2f}% ({h[-1]['day']})")
    else: L.append("   not started yet (first trading run today at ~3:05 pm IST)")
    L.append(f"   Idle money rule: {sig['park']} | Data: NSE close {sig['today']}")
    L += ["", "Orders (if any) come at ~3:05 pm IST, to place before the 3:30 pm close."]
    n = len((st or {}).get("positions", []))
    return f"INDIA BOT morning: holding {n} stock{'s' if n != 1 else ''}, {len(watch)} on watch", "\n".join(L)

STATE_CLOSE = os.environ.get("STATE_CLOSE", "data/paper_india_close_state.json")
def main():
    mode = os.environ.get("MODE", "open")            # open = after-close run (orders for next open); close = before-close run (~3:05 pm IST)
    px, nifty, nb, gb, miss = load_market()
    sig = signals(px, nifty, nb, gb)
    now_ist = datetime.now(IST); tday = now_ist.strftime("%Y-%m-%d")
    qt = nifty.attrs.get("quote_time"); qdt = datetime.fromtimestamp(qt, IST) if qt else None
    sig["quote_ist"] = qdt.strftime("%H:%M") if qdt else "?"
    if mode == "morning":
        if now_ist.weekday() >= 5 and not os.environ.get("FORCE"): print("weekend - no morning message", flush=True); return
        if not os.environ.get("FORCE") and now_ist.hour >= 10: print(f"morning message started late ({now_ist:%H:%M} IST) - skipped (the market is already open)", flush=True); return
        if not os.environ.get("FORCE") and os.path.exists(STATE_CLOSE) and json.load(open(STATE_CLOSE)).get("morning_sent") == tday: print("morning message already sent today", flush=True); return
        st = json.load(open(STATE_CLOSE)) if os.path.exists(STATE_CLOSE) else None
        title, body = morning(sig, st); print(title); print(body, flush=True); notify(title, body)
        if st is not None: st["morning_sent"] = tday; json.dump(st, open(STATE_CLOSE, "w"), indent=1, default=float)
        return
    if not os.environ.get("DRY_FAKE") and not os.environ.get("FORCE"):
        early = mode == "open" and now_ist.hour < 9 and sig["today"] < tday       # Bot A backup run before the 9:15 open: yesterday's close is right
        if sig["today"] != tday and not early: print(f"no NSE session today ({tday}); latest data {sig['today']} - nothing to do", flush=True); return
        if mode == "close":
            mins = now_ist.hour * 60 + now_ist.minute
            if not (14 * 60 + 45 <= mins <= 15 * 60 + 25): print(f"before-close run only between 2:45 and 3:25 pm IST (now {now_ist:%H:%M}) - skipping", flush=True); return
            if not qdt or (now_ist - qdt).total_seconds() > 20 * 60: print(f"prices are stale (quote {sig['quote_ist']} IST) - not trading on old prices", flush=True); return
    path = STATE_CLOSE if mode == "close" else STATE
    st = json.load(open(path)) if os.path.exists(path) else None
    st, r = step(st, sig, mode)
    if r is None: print("already ran for", sig["today"], flush=True); return
    st["missing_symbols"] = miss
    op = STATE if mode == "close" else STATE_CLOSE; other = None
    if os.path.exists(op):
        o = json.load(open(op))
        if o.get("history"): other = {"name": "India Bot A, next open" if mode == "close" else "India Bot B, before close", "equity": o["history"][-1]["equity"]}
    title, body = fmt(sig, st, r, mode, other); print(title); print(body, flush=True)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True); json.dump(st, open(path, "w"), indent=1, default=float)
    notify(title, body)

if __name__ == "__main__":
    main()
