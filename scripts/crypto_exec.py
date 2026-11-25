"""Crypto execution check (Nov 25 2026): how close can real ETF orders get to the backtest? Research only, not financial advice.
Real prices: IBIT / ETHA daily closes (Yahoo), BTC / ETH hourly (Yahoo, last ~730 days) and daily. Window = the last ~2 years (hourly data limit).
Same rule everywhere: coin above its 50-day average of daily closes -> hold, else T-bills (cash earns ^IRX).
  A) backtest: coin prices, UTC daily closes, trade the next day (what rounds 1-4 used)
  B) paper bot today: decide after the US close (coin price at 4 pm ET), buy/sell the ETF at the NEXT US close
  C) same-day: decide at 3 pm ET with the live coin price, buy/sell the ETF at TODAY's close (market-on-close / ~3:55 pm order)
  D) hold the ETF
Costs: 0.05%/side on ETF trades (spread + slippage); the ETF fee is already in its price. Also: how often B and C agree with A's signal,
and the ETF's daily tracking gap vs the coin (4 pm to 4 pm). DRY=1: fake prices."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/crypto_exec.json" if not DRY else "/tmp/crypto_exec_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym, interval="1d", rng="max"):
    if DRY:
        g = np.random.default_rng(abs(hash(sym)) % 2**32)
        if interval == "1h": ix = pd.date_range("2024-11-26", "2026-11-25 20:00", freq="h", tz="UTC"); return pd.Series(60000 * np.exp(np.cumsum(g.normal(0, 0.006, len(ix)))), index=ix)
        ix = pd.date_range("2022-01-01", "2026-11-25", tz="UTC"); ix = ix[ix.weekday < 5] if sym in ("IBIT", "ETHA", "^IRX") else ix
        if sym == "^IRX": return pd.Series(4.0, index=ix)
        return pd.Series(50 * np.exp(np.cumsum(g.normal(0.001, 0.03, len(ix)))), index=ix)
    for a in range(4):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request((f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={interval}" if interval != "1d" else f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1400000000&period2={int(time.time())}&interval=1d")   # range=max can return weekly bars, headers=UA), timeout=60).read())["chart"]["result"][0]
            s = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s", utc=True), dtype=float).dropna()
            return s[~s.index.duplicated(keep="last")]
        except Exception as e: print("retry", sym, interval, str(e)[:60], flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data " + sym)
irx = yahoo("^IRX"); irx.index = irx.index.tz_convert(None).normalize()
RES = {"note": __doc__, "results": {}}
for coin, etf in (("BTC", "IBIT"), ("ETH", "ETHA")):
    cd = yahoo(f"{coin}-USD"); cd.index = cd.index.tz_convert(None).normalize(); cd = cd[~cd.index.duplicated(keep="last")]
    ch = yahoo(f"{coin}-USD", "1h", "730d"); ch.index = ch.index.tz_convert("America/New_York")
    ef = yahoo(etf); ef.index = ef.index.tz_convert("America/New_York").normalize().tz_localize(None); ef = ef[~ef.index.duplicated(keep="last")]
    start = max(ch.index[0].tz_localize(None).normalize() + pd.Timedelta(days=2), ef.index[0] + pd.Timedelta(days=1)); days = ef.index[ef.index >= start]
    def coin_at(d, hh):                                       # last hourly close at or before d hh:00 ET (bar labelled hh-1 closes at hh)
        x = ch[ch.index <= pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(hours=hh)]
        return float(x.iloc[-1]) if len(x) else np.nan
    def ma_with(d, px):                                       # 50-day average of daily (UTC) closes before d, with today's live price as the latest
        past = cd[cd.index < pd.Timestamp(d)].iloc[-49:]; return (past.sum() + px) / 50
    sigB, sigC = {}, {}
    for d in days:
        pB = coin_at(d, 16); pC = coin_at(d, 15)
        sigB[d] = float(pB > ma_with(d, pB)) if np.isfinite(pB) else np.nan; sigC[d] = float(pC > ma_with(d, pC)) if np.isfinite(pC) else np.nan
    def etf_curve(sig, same_day):
        e, w, out, n_tr, prev = 1.0, 0.0, [], 0, None
        for i, d in enumerate(days):
            px = float(ef.loc[d]); r = (px / float(ef.loc[prev]) - 1) if prev is not None else 0.0
            gap = (d - prev).days if prev is not None else 0; cr = (1 + float(irx.asof(d)) / 100) ** (gap / 365) - 1
            e *= 1 + w * r + (1 - w) * cr
            tgt = sig.get(d) if same_day else (sig.get(days[i - 1]) if i > 0 else None)
            if tgt is not None and np.isfinite(tgt) and tgt != w: e *= 1 - 0.0005; w = tgt; n_tr += 1
            out.append(e); prev = d
        return pd.Series(out, index=days), n_tr
    # A) backtest on coin daily closes over the same window
    cal = pd.date_range(days[0], days[-1]); cp = cd.reindex(cal).ffill(); ma = cd.rolling(50).mean().reindex(cal).ffill()
    sA = (cp > ma).astype(float); rA = cp.pct_change().fillna(0); cr = ((1 + irx.reindex(cal).ffill().bfill() / 100) ** (1 / 365) - 1)
    e, w, A = 1.0, 0.0, []
    for i, t in enumerate(cal):
        e *= 1 + w * rA.iloc[i] + (1 - w) * cr.iloc[i]
        tgt = sA.iloc[i - 1] if i else 0.0
        if tgt != w: e *= 1 - 0.0005; w = tgt
        A.append(e)
    A = pd.Series(A, index=cal)
    B, nB = etf_curve(sigB, False); C, nC = etf_curve(sigC, True); Hd = pd.Series(ef.loc[days].values / float(ef.loc[days[0]]), index=days)
    yrs = (days[-1] - days[0]).days / 365
    st = lambda s: {"per_year_pct": round(((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1) * 100, 1), "worst_drop_pct": round(float((s / s.cummax() - 1).min()) * 100, 1)}
    sa = sA.reindex(days); agreeB = float((pd.Series(sigB) == sa).mean()) * 100; agreeC = float((pd.Series(sigC) == sa).mean()) * 100
    rat = pd.Series([float(ef.loc[d]) / coin_at(d, 16) for d in days], index=days)
    print(coin, "ETF/coin ratio quantiles", rat.quantile([0, 0.01, 0.5, 0.99, 1]).round(7).to_dict(), "| hourly bars", len(ch), ch.index[0], ch.index[-1], "| etf rows", len(ef), ef.index[0], ef.index[-1], flush=True)
    print(coin, "sample", [(str(d.date()), round(float(ef.loc[d]), 2), round(coin_at(d, 16), 0), sigB.get(d), float(sA.reindex(days).loc[d])) for d in days[::40]], flush=True)
    print(coin, "A switches", int(sA.diff().abs().sum()), "B signal switches", int(pd.Series(sigB).diff().abs().sum()), flush=True)
    trk = (ef.loc[days].pct_change() - pd.Series([coin_at(d, 16) for d in days], index=days).pct_change()).dropna()
    RES["results"][coin] = {"window": f"{days[0].date()} to {days[-1].date()}", "A backtest (coin, next day)": st(A), "B paper bot (ETF, next US close)": st(B) | {"trades": nB},
                            "C same day (3 pm decision, ETF at today's close)": st(C) | {"trades": nC}, f"D hold {etf}": st(Hd),
                            "signal agreement with backtest: B / C (%)": [round(agreeB, 1), round(agreeC, 1)], "ETF vs coin daily tracking gap, std (%)": round(float(trk.std()) * 100, 3)}
    print(coin, json.dumps(RES["results"][coin]), flush=True)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
