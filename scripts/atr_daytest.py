"""Research-only: PIT daily stock selection (1998+) and Alpaca 1-minute ATR exits (2016+).
No trading endpoints, no order submission, no secrets printed. Uses only yesterday's
completed daily bars to select today's stock. Ambiguous minute bars assume stop first.
"""
import argparse
import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from intraday_common import bars

SOURCE = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
CACHE = Path("/tmp")
OUT = Path("parts")
OUT.mkdir(exist_ok=True)
START = pd.Timestamp("1998-01-01")
INTRADAY_START = pd.Timestamp("2016-01-04")
END = pd.Timestamp("2026-11-13")
COSTS = [0.0, 0.0002, 0.0005, 0.001]
TARGETS = [0.5, 0.75, 1.0]
STOP_ATR = 0.5


def historical_picks():
    for name in ("prices.parquet", "membership_intervals.parquet"):
        f = CACHE / name
        if not f.exists():
            print("Downloading historical dataset:", name, flush=True)
            urllib.request.urlretrieve(SOURCE + name, str(f))
    p = pd.read_parquet(CACHE / "prices.parquet",
                        columns=["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"])
    p["date"] = pd.to_datetime(p["date"]).dt.tz_localize(None)
    p = p[(p.date >= "1996-01-01") & (p.date <= END)].copy()
    mem = pd.read_parquet(CACHE / "membership_intervals.parquet")
    mem["start"] = pd.to_datetime(mem["start"]).dt.tz_localize(None)
    mem["end"] = pd.to_datetime(mem["end"]).dt.tz_localize(None)
    p = p[p.ticker.isin(set(mem.ticker) | {"SPY"})].copy()
    f = p.adj_close / p.close
    for c in ("open", "high", "low"):
        p[c] = p[c] * f
    days = pd.DatetimeIndex(sorted(p.loc[p.ticker == "SPY", "date"].unique()))
    def pivot(field):
        return p.pivot_table(index="date", columns="ticker", values=field).reindex(days)
    c, o, h, l, v = (pivot(col) for col in ("adj_close", "open", "high", "low", "volume"))
    spy = c["SPY"].ffill()
    tick = c.columns.difference(["SPY"])
    c, o, h, l, v = (x.reindex(columns=tick) for x in (c, o, h, l, v))
    previous = c.shift(1)
    true_range = pd.concat([h-l, (h-previous).abs(), (l-previous).abs()]).groupby(level=0).max().reindex(days)
    atr = true_range.rolling(14, min_periods=14).mean()
    atr_pct = atr / c
    relative5 = c.pct_change(5, fill_method=None).sub(spy.pct_change(5), axis=0)
    mom = c.pct_change(5, fill_method=None)
    valid = ((c > 5) & (c > c.rolling(200, min_periods=200).mean()) &
             (v.rolling(20, min_periods=20).mean() >= 1000000) &
             (mom > 0) & (relative5 > 0) &
             ((atr_pct >= 0.005) & (atr_pct <= 0.10)))
    # Historical membership is evaluated at the signal close, NEVER using 2026 constituents.
    member = pd.DataFrame(False, index=days, columns=tick)
    for row in mem.itertuples(index=False):
        if row.ticker not in member.columns:
            continue
        until = row.end if pd.notna(row.end) else pd.Timestamp("2100-01-01")
        member.loc[(days >= row.start) & (days < until), row.ticker] = True
    score = ((0.7 * relative5) + (0.3 * atr_pct)).where(valid & member)
    best = score.fillna(-np.inf).idxmax(axis=1).where(score.notna().any(axis=1))
    # Signal after prior CLOSE; trade at NEXT day's 09:35 minute open (daily proxy uses next open).
    picks = []
    for i in range(1, len(days)):
        d, prev = days[i], days[i-1]
        if d < START or d > END:
            continue
        sym = best.iloc[i-1]
        if pd.isna(sym):
            continue
        # Membership on trade date also checked; no stock from future index constituents.
        if not member.at[d, sym]:
            continue
        a = atr.at[prev, sym]
        op, cl = o.at[d, sym], c.at[d, sym]
        if not (np.isfinite(a) and a > 0 and np.isfinite(op) and np.isfinite(cl) and op > 0):
            continue
        picks.append({"date": str(d.date()), "sym": sym, "atr": float(a),
                      "open": float(op), "close": float(cl), "prev_close": float(c.at[prev, sym])})
    return pd.DataFrame(picks), days[days >= START]


def summarize(equity_returns):
    x = np.asarray(equity_returns, dtype=float)
    if not len(x):
        return {"trades": 0}
    wealth = np.cumprod(1 + x)
    years = len(x) / 252
    dd = wealth / np.maximum.accumulate(np.r_[1.0, wealth])[1:] - 1
    return {"annualized_pct": round(100 * (wealth[-1] ** (1 / years) - 1), 2),
            "max_drawdown_pct": round(100 * dd.min(), 2),
            "end_10000_usd": round(10000 * wealth[-1], 2)}


def collect(shard):
    picks, days = historical_picks()
    if shard == 0:
        # OPEN->CLOSE DAILY PROXY ONLY: does not simulate ATR target/stop ordering.
        base = picks.set_index("date")
        proxy = pd.Series(0.0, index=[str(d.date()) for d in days])
        proxy.loc[base.index] = base["close"].values / base["open"].values - 1 - 0.001
        data = {"method": "next-day open-to-close proxy; NOT an executable ATR backtest",
                "sample": "1998-2026; historical point-in-time S&P 500 membership",
                "selection": "prior close: 5d relative momentum positive, above 200d mean, ATR/price 0.5-10%, avg volume >=1m",
                "signals": len(picks), "days": len(days), **summarize(proxy.values)}
        (OUT / "daily_proxy.json").write_text(json.dumps(data, indent=2))
        picks.to_csv(OUT / "all_picks.csv.gz", index=False, compression="gzip")
        pd.DataFrame({"date": [str(d.date()) for d in days]}).to_csv(
            OUT / "trading_days.csv.gz", index=False, compression="gzip")
    picks["date"] = pd.to_datetime(picks.date)
    picks = picks[(picks.date >= INTRADAY_START) & (picks.date <= END)]
    picks = picks[picks.date.dt.year.mod(3) == shard]
    rows = []
    print("shard", shard, "days", len(picks), flush=True)
    for n, rec in enumerate(picks.itertuples(index=False)):
        date = pd.Timestamp(rec.date)
        begin = date.replace(hour=9, minute=30).tz_localize("America/New_York").tz_convert("UTC")
        finish = date.replace(hour=16).tz_localize("America/New_York").tz_convert("UTC")
        try:
            x = bars([rec.sym], "1Min", start=begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     end=finish.strftime("%Y-%m-%dT%H:%M:%SZ"))
            x = x[x.t.dt.date == date.date()]
            mins = x.t.dt.hour * 60 + x.t.dt.minute
            x = x[(mins >= 575) & (mins < 960)].sort_values("t")
            if len(x) < 100 or x.t.iloc[0].hour != 9 or x.t.iloc[0].minute > 40:
                continue
            entry = float(x.o.iloc[0])
            if entry <= 0:
                continue
            after = x.iloc[1:]
            if after.empty:
                continue
            for k in TARGETS:
                stop, target = entry - STOP_ATR * rec.atr, entry + k * rec.atr
                exit_price = float(after.c.iloc[-1])
                reason = "close"
                for bar in after.itertuples(index=False):
                    if bar.o <= stop:
                        exit_price, reason = float(bar.o), "gap_stop"
                        break
                    if bar.o >= target:
                        exit_price, reason = float(bar.o), "gap_target"
                        break
                    # When both target and stop occur in one bar, conservatively assume stop first.
                    if bar.l <= stop:
                        exit_price, reason = float(stop), "stop"
                        break
                    if bar.h >= target:
                        exit_price, reason = float(target), "target"
                        break
                rows.append({"date": str(date.date()), "sym": rec.sym, "target_atr": k,
                             "entry": entry, "exit": exit_price, "gross_ret": exit_price / entry - 1,
                             "reason": reason})
        except Exception as exc:
            # Never print request headers or API keys.
            print("data error", str(date.date()), rec.sym, type(exc).__name__, flush=True)
        if n % 100 == 0:
            print("shard", shard, "progress", n, "/", len(picks), "rows", len(rows), flush=True)
    if not rows:
        raise RuntimeError("No intraday trades collected; check Alpaca data access and coverage")
    pd.DataFrame(rows).to_csv(OUT / ("trades_shard_%d.csv.gz" % shard), index=False, compression="gzip")


def analyze():
    files = list(Path("parts").rglob("trades_shard_*.csv.gz"))
    if len(files) != 3:
        raise RuntimeError("Expected exactly 3 shard artifacts; refuse to report partial performance")
    t = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    t["date"] = pd.to_datetime(t.date)
    if t.empty:
        raise RuntimeError("No trades to analyze")
    if t.duplicated(["date", "target_atr"]).any():
        raise RuntimeError("Duplicate day/target, invalid simulation")
    # Include every SPY market session, including no-signal days and missing Alpaca fills.
    # This avoids artificially annualizing only days on which the strategy traded.
    calendar = pd.read_csv(next(Path("parts").rglob("trading_days.csv.gz")))
    all_dates = calendar.loc[(calendar.date >= "2016-01-04") &
                             (calendar.date <= str(END.date())), "date"].tolist()
    if not all_dates:
        raise RuntimeError("Empty trading calendar")
    result = {"method": "Alpaca 1-minute data; prior-close signal, next-session ~09:35 entry, stop-first ambiguous bars",
              "caution": "Selection/execution are research approximations. Missing minute bars are treated as no-trade, which can bias results. No live trading.",
              "eligible_days_including_flat": len(all_dates),
              "data_start": str(t.date.min().date()), "data_end": str(t.date.max().date()),
              "targets_atr": TARGETS, "stop_atr": STOP_ATR, "trades_collected": len(t),
              "cost_per_side": COSTS, "variants": []}
    for k in TARGETS:
        tr = t[t.target_atr == k].sort_values("date").copy()
        for cost in COSTS:
            for mode in ("cash_Tplus1_reinvest_next_day", "illustrative_max3_per_week"):
                z = tr.copy()
                if mode == "illustrative_max3_per_week":
                    week = z.date.dt.strftime("%G-%V")
                    z = z[z.groupby(week).cumcount() < 3]
                # Illustrative cash account: day trades use settled proceeds no earlier than next session.
                # Real-world restrictions depend on broker/account type; not compliance advice.
                returns = pd.Series(0.0, index=all_dates)
                dates = z.date.dt.strftime("%Y-%m-%d").values
                returns.loc[dates] = z.gross_ret.values - 2 * cost
                metrics = summarize(returns.values)
                result["variants"].append({"target_atr": k, "cost_per_side": cost,
                                           "mode": mode, "trade_count": len(z),
                                           "win_rate_pct": round(100 * ((z.gross_ret - 2 * cost) > 0).mean(), 2)
                                           if len(z) else None,
                                           **metrics})
    out = Path("data")
    out.mkdir(exist_ok=True)
    (out / "atr_daytest.json").write_text(json.dumps(result, indent=2))
    proxy = next(Path("parts").rglob("daily_proxy.json"))
    (out / "atr_daytest_daily_proxy.json").write_bytes(proxy.read_bytes())
    print(json.dumps({"collected": len(t), "variants": result["variants"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["collect", "analyze"])
    parser.add_argument("--shard", type=int, choices=[0, 1, 2], default=0)
    args = parser.parse_args()
    if args.mode == "collect":
        collect(args.shard)
    else:
        analyze()
