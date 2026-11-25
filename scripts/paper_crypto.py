"""Paper bot 15: crypto trend (Nov 25 2026). Virtual $10,000, no broker. Research only, not financial advice.
Rules (crypto lab rounds 1-3, data/crypto_lab3.json):
  - Two halves: Bitcoin via IBIT, Ether via ETHA ($5,000 each at the start, no rebalancing between halves).
  - Each weekday after the US close: if the coin's price is above its 50-day average of daily closes -> it should be held, else T-bills.
  - A change is decided today and traded at the NEXT US trading day's close (as tested). 0.05% cost per trade.
  - Backtest 2018-2026 (both halves, weekdays only): ~56%/yr, worst drop -57% vs holding both 23%/yr, -77%.
Alerts only to NTFY_TOPIC_CRYPTO, only when something changes (plus a short Friday summary).
Env: STATE (default data/paper_crypto_state.json), NO_SAVE=1, NO_NOTIFY=1, DRY=1 (fake prices, nothing saved), FORCE_DAY=YYYY-MM-DD (tests)."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"
STATE = os.environ.get("STATE", "data/paper_crypto_state.json")
START_CASH, COST, MA = 10000.0, 0.0005, 50
SLEEVES = [("BTC", "IBIT"), ("ETH", "ETHA")]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.date_range("2024-01-11", os.environ.get("FORCE_DAY", "2026-11-25"))
        if sym in ("IBIT", "ETHA", "^IRX"): ix = ix[ix.weekday < 5]
        if sym == "^IRX": return pd.Series(3.6, index=ix)
        return pd.Series(50 * np.exp(np.cumsum(rng.normal(0.001, 0.03, len(ix)))), index=ix)
    for a in range(4):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d", headers=UA), timeout=60).read())["chart"]["result"][0]
            s = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s").normalize(), dtype=float).dropna()
            return s[~s.index.duplicated(keep="last")]
        except Exception as e: print("retry", sym, str(e)[:80], flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data for " + sym)
def notify(title, body):
    topic = os.environ.get("NTFY_TOPIC_CRYPTO")
    if not topic or os.environ.get("NO_NOTIFY") or DRY: print("[no ntfy]", title, "\n" + body); return
    try: urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), headers={"Title": title.encode("ascii", "ignore").decode(), "Priority": "default", "Tags": "coin"}), timeout=20)
    except Exception as e: print("ntfy failed", e)
def load():
    if os.path.exists(STATE) and not DRY: return json.load(open(STATE))
    return {"start": None, "start_cash": START_CASH, "sleeves": {c: {"etf": e, "cash": START_CASH / 2, "units": 0.0, "pending": None} for c, e in SLEEVES},
            "last_day": None, "history": [], "trades": [], "hold_units": None}
def main():
    st = load(); coins = {c: yahoo(f"{c}-USD") for c, _ in SLEEVES}; etfs = {e: yahoo(e) for _, e in SLEEVES}; irx = yahoo("^IRX")
    days = etfs["IBIT"].index.intersection(etfs["ETHA"].index)                         # US trading days with both ETF closes
    if os.environ.get("FORCE_DAY"): days = days[days <= pd.Timestamp(os.environ["FORCE_DAY"])]
    else:                                                                                  # never record today's bar before the US close (a manual run during the day)
        now_et = pd.Timestamp.now(tz="America/New_York")
        if now_et.hour * 60 + now_et.minute < 16 * 60 + 15: days = days[days < pd.Timestamp(now_et.date())]
    last = pd.Timestamp(st["last_day"]) if st["last_day"] else None
    new = [d for d in days if last is None or d > last]
    if last is None: new = new[-1:]                                                      # first run: start today, no back-filling
    if not new: print("no new US trading day since", st["last_day"]); return
    msgs, changed = [], False
    for d in new:
        prev = st["last_day"]; gap = (d - pd.Timestamp(prev)).days if prev else 0
        rate = float(irx.asof(d)) / 100 if len(irx) else 0.0
        for c, e in SLEEVES:
            s = st["sleeves"][c]; px = float(etfs[e].loc[d])
            s["cash"] *= (1 + rate) ** (gap / 365)                                          # idle money earns T-bills
            if s["pending"] == "buy" and s["cash"] > 1:
                u = s["cash"] * (1 - COST) / px; s["units"] += u; st["trades"].append({"day": str(d.date()), "symbol": e, "side": "buy", "px": round(px, 2), "usd": round(s["cash"], 2)}); s["cash"] = 0.0; s["entry_px"] = px
                msgs.append(f"BOUGHT {e} (virtual) at ${px:.2f}"); changed = True
            elif s["pending"] == "sell" and s["units"] > 0:
                usd = s["units"] * px * (1 - COST); ret = (px / s.get("entry_px", px) - 1) * 100
                st["trades"].append({"day": str(d.date()), "symbol": e, "side": "sell", "px": round(px, 2), "usd": round(usd, 2), "ret_pct": round(ret, 1)}); s["cash"] += usd; s["units"] = 0.0
                msgs.append(f"SOLD {e} (virtual) at ${px:.2f} ({ret:+.1f}% on this hold)"); changed = True
            s["pending"] = None
            # today's signal: coin price vs its 50-day average of daily closes (Yahoo crypto day = UTC day; latest close on or before today)
            cp = coins[c][coins[c].index <= d]; ma = float(cp.iloc[-MA:].mean()); p_ = float(cp.iloc[-1])
            want = p_ > ma; held = s["units"] > 0
            s.update({"coin_px": round(p_, 2), "ma50": round(ma, 2), "pct_vs_ma": round((p_ / ma - 1) * 100, 1), "signal": "hold" if want else "cash"})
            if want and not held: s["pending"] = "buy"; msgs.append(f"{c} is {s['pct_vs_ma']:+.1f}% vs its 50-day average -> BUY {e} at the next US close"); changed = True
            if not want and held: s["pending"] = "sell"; msgs.append(f"{c} is {s['pct_vs_ma']:+.1f}% vs its 50-day average -> SELL {e} at the next US close"); changed = True
        if st["start"] is None:
            st["start"] = str(d.date()); st["hold_units"] = {e: (START_CASH / 2) / float(etfs[e].loc[d]) for _, e in SLEEVES}
        eq = sum(s["cash"] + s["units"] * float(etfs[s["etf"]].loc[d]) for s in st["sleeves"].values())
        hold = sum(u * float(etfs[e].loc[d]) for e, u in st["hold_units"].items())
        st["history"].append({"day": str(d.date()), "equity": round(eq, 2), "hold_both": round(hold, 2)}); st["last_day"] = str(d.date())
    st["updated"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()); h = st["history"][-1]
    lines = [f"{c}: {s['signal'].upper()} ({s['pct_vs_ma']:+.1f}% vs 50-day avg) | {s['etf']}: {'held' if s['units'] > 0 else 'cash'}{' -> ' + s['pending'].upper() + ' next close' if s['pending'] else ''}" for c, s in st["sleeves"].items()]
    summary = "\n".join(lines) + f"\nAccount ${h['equity']:,.0f} vs holding both ${h['hold_both']:,.0f} (start ${START_CASH:,.0f}, {st['start']})"
    print("\n".join(msgs)); print(summary)
    if changed: notify("Crypto trend: " + ("; ".join(m.split(" -> ")[-1] if "->" in m else m for m in msgs))[:120], "\n".join(msgs) + "\n\n" + summary + "\nPaper bot 15, virtual money. Trade IBIT/ETHA near the US close.")
    elif pd.Timestamp(st["last_day"]).weekday() == 4: notify("Crypto trend: weekly check, no change", summary)
    if not (os.environ.get("NO_SAVE") or DRY):
        st["history"] = st["history"][-1500:]; st["trades"] = st["trades"][-400:]; json.dump(st, open(STATE, "w"), indent=1, default=float)
if __name__ == "__main__": main()
