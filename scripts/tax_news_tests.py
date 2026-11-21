"""Two tests from the Nov 20 2026 deep research. Research only, not tax or financial advice.
Engine: scripts/stack_and_rebound.py (point-in-time S&P 500, 1999-2026), Dip bot v3.0 (stock dips + ETF dips + IEF/Clear Leader parking),
live-like fills (3:45 pm ~ close, 0.08%/side stocks) and realistic fills (next open, 0.15%).

1) WASH-SALE REPLAY (with an extra conservative figure that also taxes every year's parking-ETF gains as short-term). Every closed dip trade is replayed through a simple wash-sale engine: a losing sale is "washed" when the same ticker
   is bought again within 30 calendar days AFTER the sale (the bot holds one lot per ticker; earlier-bought lots are already sold, so
   buys before the sale are not counted). The disallowed loss moves into the new lot's cost, so it is taken when that lot is sold
   (and can be washed again, or slide into the next tax year). Federal tax 24% on each year's net short-term gain; net losses carry
   forward. Parking ETF gains (SPY/IEF/Clear Leader, held for months) are left out, as in earlier after-tax figures.
   Versions: no wash-sale rule (what earlier after-tax numbers assumed) | with the rule | + 31-day cooldown (never re-buy a ticker within
   31 days of selling it at a loss) | + December-only cooldown (same, only for losing sales from Dec 1).
2) NEWS vs NO-NEWS DIPS (no news data is free, so proxies): (a) trading volume over the 5 days vs normal (the bot already skips > 2x),
   (b) share of the 5-day drop that came from overnight gaps (open vs prior close) vs during trading hours, (c) "market up, stock down":
   SPY's own 5-day move up or down. For each: per-trade averages by group, and the full bot with that group skipped / only that group,
   over 1999-2026 and both halves (1999-2012 / 2013-2026).
DRY=1: fake ETF data (code test)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/tax_news_tests.json" if not S.DRY else "/tmp/tax_news_tests_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True)
dn, t0, D = S.dn, S.t0, S.D
YEAR = pd.DatetimeIndex(dn).year.values
def cagr(cv, a="1999-01-01", b="2100-01-01"):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
    c = cv[ix] / cv[max(ix[0] - 1, t0)]; return round((c[-1] ** (252 / len(ix)) - 1) * 100, 1)
def worst(cv):
    c = cv[t0:]; return round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1)
# ---------------------------------------------------------------- 1) wash sales
def wash(log, rule=True):
    """log rows (kind, j, entry_t, exit_t, dollars_in, net_ret) -> realized gain per tax year (dollars in curve units) + stats"""
    rows = sorted([dict(k=k, j=j, e=e, x=x, usd=u, g=u * r) for k, j, e, x, u, r in log], key=lambda r: (r["x"], r["e"]))
    byt = {}
    for i, r in enumerate(rows): byt.setdefault((r["k"], r["j"]), []).append(i)
    for r in rows: r["adj"] = 0.0
    gains, washed, n_loss, carried_dec = {}, 0, 0, 0.0
    for i, r in enumerate(rows):
        g = r["g"] + r["adj"]                                  # deferred losses from earlier washes ride on this lot
        if g < 0 and rule:
            n_loss += 1
            rep = next((q for q in byt[(r["k"], r["j"])] if rows[q]["e"] > r["x"] and (dn[rows[q]["e"]] - dn[r["x"]]) <= np.timedelta64(30, "D")), None)
            if rep is not None:
                rows[rep]["adj"] += g; washed += 1
                if YEAR[rows[rep]["x"]] > YEAR[r["x"]]: carried_dec += -g
                continue
        elif g < 0: n_loss += 1
        y = YEAR[r["x"]]; gains[y] = gains.get(y, 0.0) + g
    return gains, {"losing_sales": n_loss, "washed": washed, "washed_pct": round(100 * washed / max(1, n_loss), 1), "losses_pushed_into_next_year_pct_of_equity_total": round(carried_dec * 100, 2)}
def after_tax(cv, gains, rate=0.24):
    """pay rate x each year's net gain (with loss carry-forward) out of the account at year end"""
    out = cv.copy(); k = 1.0; carry = 0.0; taxes = {}
    yrs = sorted(set(YEAR[t0:]))
    for y in yrs:
        ix = np.flatnonzero((YEAR == y) & (np.arange(D) >= t0)); last = ix[-1]
        out[ix] = cv[ix] * k
        net = gains.get(y, 0.0) + carry
        if net > 0: tax = rate * net; carry = 0.0
        else: tax = 0.0; carry = net
        tax_scaled = tax * k; taxes[int(y)] = round(tax / cv[last] * 100, 2)
        k = (cv[last] * k - tax_scaled) / cv[last]; out[last] = cv[last] * k
    return out, taxes
RES = {"wash_sales": {}, "news_proxies": {}, "per_trade_groups": {}}
for cname, cost in (("live-like", LIVE), ("realistic", REAL)):
    for vname, cool in (("v3.0", None), ("v3.0 + 31-day cooldown", "31d"), ("v3.0 + December cooldown", "dec")):
        log = []; cv, tr = S.sim(**V3, **cost, log=log, cool=cool)
        g_no, _ = wash(log, rule=False); g_w, st = wash(log, rule=True)
        a_no, tx_no = after_tax(cv, g_no); a_w, tx_w = after_tax(cv, g_w)
        # conservative: everything else the account earned (parking ETFs, cost drag) is also taxed every year, as if all short-term
        ye = {int(y): cv[np.flatnonzero((YEAR == y) & (np.arange(D) >= t0))[-1]] for y in sorted(set(YEAR[t0:]))}; yy = sorted(ye)
        tot = {y: ye[y] - (ye[yy[i - 1]] if i else cv[t0 - 1]) for i, y in enumerate(yy)}
        dip_raw = {int(y): v for y, v in g_no.items()}
        g_all = {y: tot[y] - dip_raw.get(y, 0.0) + g_w.get(y, 0.0) for y in yy}
        a_all, _ = after_tax(cv, g_all)
        if cool is None: st_no_rule = None
        k = f"{cname} | {vname}"
        RES["wash_sales"][k] = {"before_tax": cagr(cv), "after_tax_no_wash_rule": cagr(a_no), "after_tax_with_wash_rule": cagr(a_w), "after_tax_with_rule_parking_taxed_too": cagr(a_all), "worst_drop_before_tax": worst(cv),
                                "after_tax_ratio_with_rule": round(cagr(a_w) / max(1e-9, cagr(cv)), 3), "trades_per_month": round(len(tr) / ((D - t0) / 21), 1), **st,
                                "tax_paid_pct_of_equity_by_year_with_rule": tx_w}
        r = RES["wash_sales"][k]
        print(f"WASH {k:42s} before {r['before_tax']}% | after tax: no rule {r['after_tax_no_wash_rule']}% -> with rule {r['after_tax_with_wash_rule']}% (parking taxed too: {r['after_tax_with_rule_parking_taxed_too']}%) | "
              f"losing sales {r['losing_sales']}, washed {r['washed_pct']}% | {r['trades_per_month']}/mo", flush=True)
# ---------------------------------------------------------------- 2) news proxies
Cs = pd.DataFrame(S.S_C, index=S.dates, columns=S.tick); Os = pd.DataFrame(S.S_O, index=S.dates, columns=S.tick)
gap = np.log(Os / Cs.shift(1)); tot = np.log(Cs / Cs.shift(5))
GAPSHARE = (gap.rolling(5).sum() / tot).where(tot < -0.02).values          # share of the 5-day drop that came from overnight gaps
VR = S.vr.values
SPY5 = np.r_[np.full(5, np.nan), S.SP[5:] / S.SP[:-5] - 1]
SIG = S.SIG
MASKS = {"heavy volume (1.5-2x normal)": np.nan_to_num(VR, nan=0) > 1.5, "light volume (< 1x normal)": np.nan_to_num(VR, nan=9) < 1.0,
         "mostly overnight gaps (> 60% of the drop)": np.nan_to_num(GAPSHARE, nan=0) > 0.6, "mostly during the day (< 30% from gaps)": np.nan_to_num(GAPSHARE, nan=1) < 0.3,
         "market up (SPY up over the 5 days)": np.repeat((np.nan_to_num(SPY5) > 0)[:, None], SIG.shape[1], axis=1),
         "market down 3%+ over the 5 days": np.repeat((np.nan_to_num(SPY5) < -0.03)[:, None], SIG.shape[1], axis=1)}
# per-trade groups (from the v3.0 live-like log)
log = []; cvb, trb = S.sim(**V3, **LIVE, log=log)
stk = [r for r in log if r[0] == "S"]
def grp(rows):
    x = np.array([r[5] for r in rows]);
    if not len(x): return None
    return {"trades": len(x), "avg_trade_pct": round(float(x.mean()) * 100, 2), "win_pct": round(float((x > 0).mean()) * 100, 1), "t_stat": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 1) if len(x) > 2 else None}
RES["per_trade_groups"]["all stock dips"] = grp(stk)
for name, m in MASKS.items():
    RES["per_trade_groups"][name] = grp([r for r in stk if m[r[2], r[1]]]); RES["per_trade_groups"]["NOT " + name] = grp([r for r in stk if not m[r[2], r[1]]])
    a, b = RES["per_trade_groups"][name], RES["per_trade_groups"]["NOT " + name]
    print(f"GROUP {name:45s} {a} | rest {b}", flush=True)
def summ(cv, tr):
    return {"1999-2026": cagr(cv), "1999-2012": cagr(cv, "1999-01-01", "2013-01-01"), "2013-2026": cagr(cv, "2013-01-01"), "worst": worst(cv), "trades_per_month": round(len(tr) / ((D - t0) / 21), 1)}
for cname, cost in (("live-like", LIVE), ("realistic", REAL)):
    RES["news_proxies"][f"{cname} | v3.0 as is"] = summ(*S.sim(**V3, **cost))
    for name, m in MASKS.items():
        RES["news_proxies"][f"{cname} | skip {name}"] = summ(*S.sim(**V3, **cost, sig=SIG & ~m))
    for k in [k for k in RES["news_proxies"] if k.startswith(cname)]:
        g = RES["news_proxies"][k]; print(f"NEWS {k:70s} {g['1999-2026']}% | 99-12 {g['1999-2012']} 13-26 {g['2013-2026']} | worst {g['worst']} | {g['trades_per_month']}/mo", flush=True)
assert summ(cvb, trb) == RES["news_proxies"]["live-like | v3.0 as is"], "log must not change results"
print("check ok: logging trades does not change the bot", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, **RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
