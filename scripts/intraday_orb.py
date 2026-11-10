# Strategy C: 5-minute Opening Range Breakout on "Stocks in Play" (Zarattini/Barbon/Aziz 2024). Research only.
# Universe: S&P 500 members (point in time, incl. later-removed names where Alpaca has data), 2016-now, 5-min bars.
# Filters: open > $5, 14-day avg volume >= 1M, 14-day ATR > $0.50, relative volume of the first 5 minutes >= 100% of its 14-day average.
# First 5-min candle up -> buy stop at its high; down -> sell stop at its low. Stop = 10% of ATR from entry. Exit at the close.
# Pick the top 20 by relative volume each day. Same-bar stop hit is counted as a loss (conservative).
import sys, os, traceback, urllib.request, time
import numpy as np, pandas as pd
sys.path.insert(0, "scripts"); from intraday_common import bars, stats, spy_daily_stats, save

def members():
    f = "/tmp/membership_intervals.parquet"
    if not os.path.exists(f):
        for i in range(6):
            try: urllib.request.urlretrieve("https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/membership_intervals.parquet", f); break
            except Exception as e: print("retry", e); time.sleep(20 * (i + 1))
    m = pd.read_parquet(f); m["start"] = pd.to_datetime(m.start); m["end"] = pd.to_datetime(m.end).fillna(pd.Timestamp("2100-01-01"))
    m = m[m.end >= "2016-01-01"].copy()
    def alp(t):
        b = t.rsplit("-", 1)
        t = b[0] if len(b) == 2 and b[1].isdigit() and len(b[1]) == 6 else t
        return t.replace("-", ".")
    m["sym"] = m.ticker.map(alp)
    return m

def per_symbol(df, m_sym):
    """df: 5-min bars for one symbol. Returns list of candidate trades (both directions computed as the rule says)."""
    df = df.copy(); df["d"] = df.t.dt.normalize(); df["mm"] = df.t.dt.hour * 60 + df.t.dt.minute
    g = df.groupby("d")
    day = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "v": g.v.sum()})
    first = df[df.mm == 570].set_index("d")[["o", "h", "l", "c", "v"]]
    day = day.join(first, rsuffix="_or")
    pc = day.c.shift(1)
    tr = pd.concat([day.h - day.l, (day.h - pc).abs(), (day.l - pc).abs()], axis=1).max(axis=1)
    day["atr"] = tr.rolling(14).mean().shift(1); day["avgv"] = day.v.rolling(14).mean().shift(1)
    day["rv"] = day.v_or / day.v_or.rolling(14).mean().shift(1)
    inmem = pd.Series(False, index=day.index)
    for _, r in m_sym.iterrows(): inmem |= (day.index >= r.start) & (day.index < r.end)
    ok = inmem & (day.o_or > 5) & (day.avgv >= 1e6) & (day.atr > 0.5) & (day.rv >= 1) & (day.c_or != day.o_or) & day.v_or.notna()
    out = []
    byday = dict(tuple(df[df.mm >= 575].groupby("d")))
    for d in day.index[ok.values]:
        r = day.loc[d]; b = byday.get(d)
        if b is None or b.empty: continue
        long = r.c_or > r.o_or; lvl = r.h_or if long else r.l_or; risk = 0.1 * r.atr
        entry = stop = None; ex = None
        for o, h, l, c in zip(b.o.values, b.h.values, b.l.values, b.c.values):
            if entry is None:
                if long and h >= lvl: entry = max(lvl, o); stop = entry - risk
                elif not long and l <= lvl: entry = min(lvl, o); stop = entry + risk
                else: continue
                if (long and l <= stop) or (not long and h >= stop): ex = stop; break
                continue
            if long:
                if o <= stop: ex = o; break
                if l <= stop: ex = stop; break
            else:
                if o >= stop: ex = o; break
                if h >= stop: ex = stop; break
        if entry is None: continue
        if ex is None: ex = b.c.values[-1]
        ret = (ex / entry - 1) if long else (entry / ex - 1)
        out.append((d, r.rv, int(long), ret, risk / entry))
    return out

def collect(k, n):
    m = members(); syms = sorted(m.sym.unique())[k::n]; print(len(syms), "symbols in shard", k, flush=True)
    rows = []; t0 = time.time()
    for i in range(0, len(syms), 4):
        chunk = syms[i:i + 4]
        df = bars(chunk, "5Min")
        for s, g in df.groupby("sym"):
            for d, rv, lg, ret, rk in per_symbol(g, m[m.sym == s]): rows.append((d, s, rv, lg, ret, rk))
        del df
        print(i + len(chunk), "/", len(syms), "symbols", len(rows), "trades", round((time.time() - t0) / 60, 1), "min", flush=True)
    os.makedirs("parts", exist_ok=True)
    pd.DataFrame(rows, columns=["d", "sym", "rv", "long", "ret", "risk"]).to_csv(f"parts/orb_part_{k}.csv.gz", index=False)

def run():
    import glob
    T = pd.concat([pd.read_csv(f, parse_dates=["d"]) for f in glob.glob("parts/**/orb_part_*.csv.gz", recursive=True)])
    print(len(T), "candidate trades", T.sym.nunique(), "symbols", flush=True)
    os.makedirs("data", exist_ok=True); T.to_csv("data/intraday_orb_trades.csv.gz", index=False)
    days = pd.DatetimeIndex(sorted(bars(["SPY"], "1Day", regular=False).t.dt.normalize().unique()))
    res = {"results": [], "candidate_trades": len(T)}
    def port(topn=20, long_only=False, cost=0.001, sizing="equal", pdt=False):
        x = T[T.long == 1] if long_only else T
        x = x.sort_values(["d", "rv"], ascending=[True, False]).groupby("d").head(1 if pdt else topn)
        if pdt:
            wk = x.d.map(lambda d: d.isocalendar()[:2]); x = x[x.groupby(wk).cumcount() < 3]
        if sizing == "equal": w = pd.Series(1.0 if pdt else 1.0 / topn, index=x.index)
        else:  # paper style: risk 1% of money per trade, total leverage capped at 4x
            w = (0.01 / x.risk).clip(upper=4.0)
            tot = w.groupby(x.d).transform("sum"); w = w * np.minimum(1, 4.0 / tot)
        daily = (w * (x.ret - 2 * cost)).groupby(x.d).sum().reindex(days).fillna(0)
        st = stats(daily); st.update(trades=len(x), win_rate=round(100 * float((x.ret > 2 * cost).mean()), 1) if len(x) else None, avg_trade_pct=round(100 * float((x.ret - 2 * cost).mean()), 3) if len(x) else None)
        return st
    variants = [("top 20, long+short, equal 5% each", {}), ("top 20, long only, equal 5% each", dict(long_only=True)),
                ("top 20, long+short, paper sizing (1% risk, <=4x)", dict(sizing="risk")), ("top 5, long+short, equal 20% each", dict(topn=5)),
                ("1 stock/day, max 3/week, long only, 100% (PDT)", dict(pdt=True, long_only=True)), ("1 stock/day, max 3/week, long+short, 100% (PDT)", dict(pdt=True))]
    for name, kw in variants:
        for tag, cost in [("ideal 0.02%/side", 0.0002), ("realistic 0.10%/side", 0.001), ("harsh 0.20%/side", 0.002)]:
            st = port(cost=cost, **kw); st.update(variant=name, costs=tag); res["results"].append(st)
            print(name, tag, st.get("cagr"), st.get("dd"), st.get("sharpe"), st.get("trades"), st.get("avg_trade_pct"), flush=True)
    res["benchmark_SPY"] = spy_daily_stats()
    res["note"] = "Universe limited to S&P 500 names (paper used all ~7000 US stocks). Costs per side include slippage on stop entries."
    save("intraday_orb", res)

try:
    if sys.argv[1:2] == ["collect"]: collect(int(sys.argv[2]), int(sys.argv[3]))
    else: run()
except Exception:
    if sys.argv[1:2] == ["collect"]: raise
    save("intraday_orb", {"error": traceback.format_exc()}); print(traceback.format_exc()); sys.exit(1)
