# Buy-the-dip strategy on Indian stocks (NSE), 2008-2026. Research only.
# Universe: approx point-in-time top-100 / top-200 NSE stocks by 120-session median traded value, re-picked every 6 months,
# from today's Nifty 500 + former large caps (stocks that vanished from Yahoo are missing -> some survivorship bias).
# Rule (same as US): above 200-day avg, fell >=10% vs Nifty 50 over 5 sessions, buy biggest dips first, 10 slots x 10%,
# smart exit (close > 5-day avg, max 5 sessions). Optional: skip if 5-day volume > 2x its normal 50-day volume.
# Idle money: cash (0%), liquid fund (~6%/yr), or Nifty while Nifty > its 100-day avg else liquid fund.
import os, sys, json, time, traceback, urllib.request, urllib.parse, io
import numpy as np, pandas as pd
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
FORMER = ['HDFC', 'MINDTREE', 'LTI', 'IBULHSGFIN', 'DHFL', 'ZEEL', 'IDEA', 'YESBANK', 'CADILAHC', 'MCDOWELL-N', 'GRUH', 'BHARTIINFRA', 'PEL', 'AUROPHARMA', 'GLENMARK', 'RCOM', 'RELINFRA', 'RPOWER', 'JETAIRWAYS', 'SRTRANSFIN', 'L&TFH', 'NIACL', 'GICRE', 'BANKBARODA', 'IDBI', 'PNB', 'CANBK', 'MOTHERSUMI', 'AMARAJABAT', 'TATAMTRDVR', 'ADANITRANS', 'ADANIGAS', 'INFRATEL', 'HDFCAMC', 'VEDL', 'NMDC', 'SAIL', 'BHEL', 'OFSS', 'MRF', 'PAGEIND', 'BOSCHLTD', 'CONCOR', 'PETRONET', 'IGL', 'GAIL', 'ACC', 'AMBUJACEM', 'LUPIN', 'BIOCON', 'COLPAL', 'MARICO', 'DABUR', 'GODREJCP', 'HAVELLS', 'BERGEPAINT', 'PIDILITIND', 'SIEMENS', 'ABB', 'INDIGO', 'NAUKRI', 'UBL', 'TORNTPHARM', 'ICICIPRULI', 'ICICIGI', 'BANDHANBNK', 'PGHH', 'DLF', 'MUTHOOTFIN', 'COFORGE', 'PERSISTENT', 'TATAPOWER', 'TATACHEM', 'CHOLAFIN', 'APOLLOHOSP']
LIQUID = 0.06
def get(url, tries=5):
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("fail", url[:100], err); return None
def yahoo(sym):
    b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=1104537600&period2={int(time.time())}&interval=1d&events=div%2Csplit")
    if not b: return None
    try:
        j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]["quote"][0]
        adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
        df = pd.DataFrame({"c": adj, "rc": q["close"], "o": q["open"], "v": q["volume"]}, index=pd.to_datetime(j["timestamp"], unit="s").normalize())
        df = df[~df.index.duplicated(keep="last")].dropna(subset=["c", "rc"]); df = df[(df.c > 0) & (df.rc > 0)]
        df["o"] = df.o * df.c / df.rc   # adjust open like close
        return df
    except Exception as e: print("parse", sym, e); return None
def universe():
    syms = []
    for u in ["https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv", "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"]:
        b = get(u)
        if b:
            try: syms = list(pd.read_csv(io.BytesIO(b)).Symbol.dropna().astype(str)); break
            except Exception as e: print("csv", e)
    if not syms: raise RuntimeError("could not load Nifty 500 list")
    return sorted(set(syms) | set(FORMER))
def run():
    MODE = sys.argv[1] if len(sys.argv) > 1 else "dip"
    syms = universe(); print(len(syms), "symbols", flush=True)
    nifty = yahoo("^NSEI"); px = {}
    for i, s in enumerate(syms):
        d = yahoo(s + ".NS")
        if d is not None and len(d) > 250: px[s] = d
        if i % 50 == 0: print(i, len(px), flush=True)
        time.sleep(0.25)
    dates = nifty.index[nifty.index >= "2006-06-01"]
    C = pd.DataFrame({s: d.c for s, d in px.items()}).reindex(dates); O = pd.DataFrame({s: d.o for s, d in px.items()}).reindex(dates)
    RC = pd.DataFrame({s: d.rc for s, d in px.items()}).reindex(dates); V = pd.DataFrame({s: d.v for s, d in px.items()}).reindex(dates)
    valid = C.notna(); Cf = C.ffill(); tick = list(C.columns); n = nifty.c.reindex(dates).ffill()
    r1 = Cf.pct_change()
    glitch = (r1.abs() > 0.35).rolling(6, min_periods=1).max().astype(bool)          # skip windows with suspicious jumps
    tv = (RC * V).rolling(120, min_periods=60).median()
    D = len(dates); START = int(np.searchsorted(dates.values, np.datetime64("2008-01-01")))
    halves = [i for i in range(1, D) if dates[i].month in (1, 7) and dates[i - 1].month not in (1, 7)]
    def members(k):
        M = pd.DataFrame(False, index=dates, columns=tick); b = [0] + halves + [D]
        for a, z in zip(b[:-1], b[1:]):
            if a == 0: continue
            row = tv.iloc[a - 1].dropna().sort_values(ascending=False)
            M.iloc[a:z, M.columns.get_indexer(row.index[:k])] = True
        return M & valid & valid.shift(-1, fill_value=False) & (RC > 20)
    above = Cf > Cf.rolling(200).mean()
    rl = Cf.pct_change(5).sub(n.pct_change(5), axis=0)
    vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5))
    over5 = (Cf > Cf.rolling(5).mean()).values; Rt = r1.fillna(0).values; OC = (Cf / O - 1).fillna(0).values
    nr = n.pct_change().fillna(0).values; liq = np.full(D, (1 + LIQUID) ** (1 / 248) - 1)
    ntr = (n > n.rolling(100).mean()).shift(1, fill_value=False).values
    PARK = {"cash": np.zeros(D), "liquid fund ~6%": liq, "Nifty trend (100-day), else liquid": np.where(ntr, nr, liq), "Nifty always": nr}
    def sim(S, R, park, cost=0.0015, entry="close", mx=5, slots=10):
        eq = 1.0; curve = np.ones(D); pos = []; tr = []; inv = []
        for t in range(START, D):
            used = sum(p[2] for p in pos); day = 0.0
            for p in pos:
                g = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[3] *= 1 + g; day += p[2] * g
            day += max(0.0, 1 - used) * park[t]; inv.append(used); eq *= 1 + day; keep = []
            for p in pos:
                g = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[1] += 1; p[2] *= (1 + g) / (1 + day)
                if p[1] >= mx or over5[t, p[0]]: eq *= 1 - cost * p[2]; tr.append(p[3] - 1 - 2 * cost)
                else: keep.append(p)
            pos = keep; used = sum(p[2] for p in pos); held = {p[0] for p in pos}
            new = [c for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
            if new:
                w = min(1.0 / slots, max(0.0, 1 - used) / len(new))
                for c in new: pos.append([c, 0, w, 1.0]); eq *= 1 - cost * w
            curve[t] = eq
        return summarize(curve, tr, inv)
    def summarize(curve, tr=None, inv=None):
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0); yrs = len(p) / 248
        per = {}
        for a, b in [("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[a + "-" + b] = round(100 * ((1 + q).prod() ** (248 / max(len(q), 1)) - 1), 1)
        o = {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per}
        for nm_, a, b in [("train_2008_2018", "2008", "2018-12-31"), ("test_2019_2026", "2019", "2100")]:
            q = c[(c.index >= a) & (c.index <= b)]
            if len(q) > 100: o[nm_] = {"cagr": round(100 * ((q.iloc[-1] / q.iloc[0]) ** (248 / len(q)) - 1), 1), "dd": round(100 * (q / q.cummax() - 1).min(), 1)}
        if inv is not None: o["invested_pct"] = round(100 * float(np.mean(inv)), 1)
        if tr: o["trades"] = len(tr); o["win_rate"] = round(100 * float((np.array(tr) > 0).mean()), 1); o["avg_trade_pct"] = round(100 * float(np.mean(tr)), 2)
        return o
    OUT = {"years": f"{dates[START].date()} to {dates[-1].date()}", "stocks_with_prices": len(px),
           "nifty50": summarize((1 + pd.Series(nr, index=dates)).cumprod().values / (1 + nr[:START + 1]).prod()),
           "note": "Nifty 50 price index (no dividends, ~1.2-1.5%/yr understated). Ideal = buy at close, 0.15%/side (STT, stamp, charges). Realistic = next open, 0.30%/side.", "results": []}
    if MODE == "gold":
        # Where to hide when Nifty is below its trend: faster/slower gold exits, gold-vs-cash, gold+liquid splits.
        g = yahoo("GOLDBEES.NS"); gold = g.c.reindex(dates).ffill(); gr = gold.pct_change().fillna(0).values
        dv = (1 + 0.013) ** (1 / 248) - 1
        gt = lambda k: (gold > gold.rolling(k).mean()).shift(1, fill_value=False).values
        gmom = (gold.pct_change(63) > 0).shift(1, fill_value=False).values
        ALT = {"liquid fund only": liq, "gold always": gr, "cash only": np.zeros(D)}
        for k in (20, 50, 100, 150, 200): ALT[f"gold if above its {k}-day avg, else liquid"] = np.where(gt(k), gr, liq)
        ALT["gold if above its 50-day avg, else CASH"] = np.where(gt(50), gr, 0.0)
        ALT["gold if 3-month gain > 0, else liquid"] = np.where(gmom, gr, liq)
        ALT["gold if above 50-day AND 200-day avg, else liquid"] = np.where(gt(50) & gt(200), gr, liq)
        ALT["50% gold + 50% liquid"] = 0.5 * gr + 0.5 * liq
        ALT["50% liquid + 50% gold-if-above-100-day (else liquid)"] = 0.5 * liq + 0.5 * np.where(gt(100), gr, liq)
        def tsig(k): return (n > n.rolling(k).mean()).shift(1, fill_value=False).values.astype(bool)
        M = members(200).values; ab = above.values & M & ~glitch.values; R = (-rl).values; S12 = (rl.values <= -0.12) & ab & ~(vr > 2.0).values
        rows = []
        def per2(r):
            return {k: r["per"][k] for k in r["per"]}
        for k in (100, 150):
            sg = tsig(k)
            for name, alt in ALT.items():
                pk = np.where(sg, nr + dv, alt).astype(float); pk[np.r_[False, sg[1:] != sg[:-1]]] -= 0.0005
                a1 = sim(np.zeros_like(ab), R, pk); a2 = sim(S12, R, pk, entry="open", cost=0.003)
                row = {"nifty_avg": k, "hide_in": name, "parking_only": {kk: a1[kk] for kk in ("cagr", "dd", "per", "train_2008_2018", "test_2019_2026")},
                       "with_12pct_dips_realistic": {kk: a2[kk] for kk in ("cagr", "dd", "per", "train_2008_2018", "test_2019_2026")}}
                rows.append(row); print(k, name, a1["cagr"], a1["dd"], a1["per"]["2010-2015"], "| dips", a2["cagr"], a2["dd"], a2["test_2019_2026"], flush=True)
        gy = pd.Series(gr, index=dates)
        OUT["gold_by_period"] = {pp: round(100 * ((1 + gy[(gy.index >= pp[:4]) & (gy.index <= pp[5:] + "-12-31")]).prod() ** (248 / max(1, ((gy.index >= pp[:4]) & (gy.index <= pp[5:] + "-12-31")).sum())) - 1), 1) for pp in ("2008-2009", "2010-2015", "2016-2020", "2021-2026")}
        OUT["gold_tests"] = rows; OUT["note"] += " Before tax, Nifty with ~1.3% dividends, liquid fund 6%/yr, 0.05% per Nifty switch (gold/liquid switches not charged)."
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_gold.json", "w"), indent=1, default=float); return
    if MODE == "oos":
        # Out-of-sample check: pick settings using 2008-2018 only, then see how they did on 2019-2026.
        g = yahoo("GOLDBEES.NS"); gold = g.c.reindex(dates).ffill(); gr = gold.pct_change().fillna(0).values
        gtr = (gold > gold.rolling(100).mean()).shift(1, fill_value=False).values; dv = (1 + 0.013) ** (1 / 248) - 1
        nm = n.copy(); me = nm.groupby(nm.index.to_period("M")).transform("last") == nm
        def tsig(kind):
            if kind == "10m":
                mc = nm[me]; ok = (mc > mc.rolling(10).mean()).reindex(dates).ffill().fillna(False)
            else: ok = nm > nm.rolling(int(kind)).mean()
            return ok.shift(1, fill_value=False).values.astype(bool)
        def park(kind, below):
            sg = tsig(kind); alt = {"liquid": liq, "gold": gr, "gold if trending else liquid": np.where(gtr, gr, liq)}[below]
            r = np.where(sg, nr + dv, alt).astype(float); r[np.r_[False, sg[1:] != sg[:-1]]] -= 0.0005; return r
        M = members(200).values; ab = above.values & M & ~glitch.values; R = (-rl).values
        VC = {"none": np.ones_like(ab), "2x": ~(vr > 2.0).values}
        rows = []
        for kind in ("50", "100", "150", "200", "10m"):
            for below in ("liquid", "gold", "gold if trending else liquid"):
                pk = park(kind, below)
                r = sim(np.zeros_like(ab), R, pk); r.update(avg=kind, below=below, dip="none", vol="-"); rows.append(r)
                for th in (0.10, 0.12, 0.14):
                    for vk, vm in VC.items():
                        r = sim((rl.values <= -th) & ab & vm, R, pk, entry="open", cost=0.003); r.update(avg=kind, below=below, dip=f"{int(th*100)}%", vol=vk); rows.append(r)
                print(kind, below, len(rows), flush=True)
        def pick(rows_, key):
            return max(rows_, key=key)
        tr = lambda r: r["train_2008_2018"]["cagr"]
        trr = lambda r: r["train_2008_2018"]["cagr"] / max(1.0, -r["train_2008_2018"]["dd"])   # return per unit of drop
        ny = pd.Series(nr + dv, index=dates)
        def bench(a, b):
            q = ny[(ny.index >= a) & (ny.index <= b)]; c = (1 + q).cumprod(); return {"cagr": round(100 * (c.iloc[-1] ** (248 / len(c)) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1)}
        sel = lambda r: {k: r[k] for k in ("avg", "below", "dip", "vol", "train_2008_2018", "test_2019_2026", "cagr", "dd")}
        test_c = np.array([r["test_2019_2026"]["cagr"] for r in rows])
        ours = [r for r in rows if (r["avg"], r["below"], r["dip"], r["vol"]) in {("100", "liquid", "12%", "2x"), ("150", "gold if trending else liquid", "12%", "2x")}]
        OUT["oos"] = {"nifty_with_dividends": {"train_2008_2018": bench("2008", "2018-12-31"), "test_2019_2026": bench("2019", "2100")},
                      "picked_by_best_train_return": sel(pick(rows, tr)),
                      "picked_by_best_train_return_per_drop": sel(pick(rows, trr)),
                      "picked_best_with_dips_by_train_return": sel(pick([r for r in rows if r["dip"] != "none"], tr)),
                      "our_chosen_versions_full_period_picks": [sel(r) for r in ours],
                      "all_versions_test_period": {"n": len(rows), "median": float(np.median(test_c)), "min": float(test_c.min()), "max": float(test_c.max()),
                                                   "beat_nifty_test": int((test_c > bench("2019", "2100")["cagr"]).sum())},
                      "rows": [sel(r) for r in rows],
                      "note": "Realistic fills (next open, 0.30%/side), before tax, Nifty with ~1.3% dividends, liquid fund 6%/yr. Settings picked using 2008-2018 only."}
        print(json.dumps({k: v for k, v in OUT["oos"].items() if k != "rows"}, indent=1), flush=True)
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_oos.json", "w"), indent=1, default=float); return
    if MODE == "checks":
        STCG, LTCG, SLAB, CAP0, EXEMPT, DIV = 0.20 * 1.04, 0.125 * 1.04, 0.30 * 1.04, 1_000_000.0, 125_000.0, 0.013
        g = yahoo("GOLDBEES.NS"); gold = g.c.reindex(dates).ffill(); gr = gold.pct_change().fillna(0).values
        gtr = (gold > gold.rolling(100).mean()).shift(1, fill_value=False).values
        dv = (1 + DIV) ** (1 / 248) - 1
        def tsig(k): return (n > n.rolling(k).mean()).shift(1, fill_value=False).values.astype(bool)
        years = dates.year.values
        def sim_tax(S, R, sig, below, cost=0.003, entry="open", mx=5, slots=10, tax=True, trades_on=True):
            """Rupee simulation (Rs 10 lakh start) with Indian taxes: dip trades = short-term gains (20.8%), Nifty ETF gains
            short/long term by holding length (20.8% / 13% above Rs 1.25L), liquid fund & gold & dividends at 31.2% slab.
            Losses offset gains within a year (short-term losses also against long-term), net losses carried forward.
            Everything still held at the end is sold and taxed, so results are comparable with buy-and-hold."""
            eq = CAP0; pos = []; curve = np.ones(D) * CAP0
            acc = {"nifty": 0.0, "liquid": 0.0, "gold": 0.0}; seg0 = None; cur = None
            st = lt = slab = 0.0; cf_st = cf_lt = 0.0; paid = 0.0
            def realize(asset, t):
                nonlocal st, lt, slab
                gval = acc[asset]; acc[asset] = 0.0
                if asset == "nifty":
                    if seg0 is not None and t - seg0 > 248: lt += gval
                    else: st += gval
                else: slab += gval   # liquid fund and short-held gold: taxed at slab
            def year_end():
                nonlocal st, lt, slab, cf_st, cf_lt, eq, paid
                a = st + cf_st; b = lt + cf_lt
                if a < 0 and b > 0:
                    b2 = b + a; a, b = (0.0, b2) if b2 >= 0 else (b2, 0.0)
                tx = STCG * max(a, 0.0) + LTCG * max(b - EXEMPT, 0.0) + SLAB * max(slab, 0.0)
                cf_st = min(a, 0.0); cf_lt = min(b, 0.0); st = lt = slab = 0.0
                if tax: eq -= tx; paid += tx
            for t in range(START, D):
                asset = ("nifty" if sig[t] else ("liquid" if below == "liquid" else ("gold" if (below == "gold" or gtr[t]) else "liquid")))
                if asset != cur:
                    if cur is not None: realize(cur, t)
                    if cur is not None: eq -= 0.0005 * max(0.0, eq - sum(p[2] for p in pos))
                    cur = asset; seg0 = t if asset == "nifty" else None
                ar = nr[t] + dv if asset == "nifty" else (liq[t] if asset == "liquid" else gr[t])
                held_val = sum(p[2] for p in pos); park_val = max(0.0, eq - held_val)
                gain = park_val * ar
                if asset == "nifty": acc["nifty"] += park_val * nr[t]; slab += park_val * dv
                else: acc[asset] += gain
                day = gain
                for p in pos:
                    gg = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                    day += p[2] * gg; p[2] *= 1 + gg
                eq += day; keep = []
                for p in pos:
                    p[1] += 1
                    if p[1] >= mx or over5[t, p[0]]:
                        c = cost * p[2]; eq -= c; st += p[2] - p[3] - c - cost * p[3]
                    else: keep.append(p)
                pos = keep
                if trades_on:
                    held = {p[0] for p in pos}; used = sum(p[2] for p in pos)
                    new = [c for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
                    if new:
                        w = min(eq / slots, max(0.0, eq - used) / len(new))
                        for c in new: pos.append([c, 0, w, w]); eq -= cost * w   # [col, days, value now, cost basis]
                if t + 1 == D or years[t + 1] != years[t]:
                    if t + 1 == D:   # sell everything and settle
                        for p in pos: st += p[2] - p[3]
                        realize(cur, t)
                    year_end()
                curve[t] = eq
            c = pd.Series(curve[START:] / CAP0, index=dates[START:]); pr = c.pct_change().fillna(0); yrs = len(pr) / 248
            per = {}
            for a2, b2 in [("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
                q = pr[(pr.index >= a2) & (pr.index <= b2 + "-12-31")]; per[a2 + "-" + b2] = round(100 * ((1 + q).prod() ** (248 / max(len(q), 1)) - 1), 1)
            return {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per, "tax_paid_lakh": round(paid / 1e5, 1), "final_lakh": round(c.iloc[-1] * CAP0 / 1e5, 1)}
        def nifty_hold(tax=True):
            v = CAP0; basis = CAP0; curve = []
            for t in range(START, D):
                v *= 1 + nr[t]; d = v * dv
                v += d * (1 - SLAB) if tax else d
                if tax: basis += d * (1 - SLAB)
                curve.append(v)
            if tax: curve[-1] -= LTCG * max(curve[-1] - basis - EXEMPT, 0)
            c = pd.Series(curve, index=dates[START:]) / CAP0; yrs = len(c) / 248
            return {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "final_lakh": round(c.iloc[-1] * CAP0 / 1e5, 1)}
        OUT["checks"] = {"nifty_hold_with_dividends_pre_tax": nifty_hold(False), "nifty_hold_with_dividends_after_tax": nifty_hold(True)}
        print("nifty", OUT["checks"], flush=True)
        M = members(200).values; ab = above.values & M & ~glitch.values; R = (-rl).values; volok = ~(vr > 2.0).values
        S12 = (rl.values <= -0.12) & ab & volok
        tax_rows = []
        for name, S, k, below, on in [("Trend switch only: 100-day, else liquid", S12, 100, "liquid", False),
                                       ("Trend switch only: 150-day, else gold if trending / liquid", S12, 150, "gold if trending else liquid", False),
                                       ("SAFEST: 12% dips + 100-day, else liquid", S12, 100, "liquid", True),
                                       ("BEST: 12% dips + 150-day, else gold if trending / liquid", S12, 150, "gold if trending else liquid", True)]:
            for tx in (False, True):
                r = sim_tax(S, R, tsig(k), below, tax=tx, trades_on=on); r.update(version=name, tax="after tax" if tx else "before tax (with dividends)")
                tax_rows.append(r); print(name, r["tax"], r["cagr"], r["dd"], r["tax_paid_lakh"], r["final_lakh"], flush=True)
        OUT["checks"]["after_tax"] = tax_rows
        # ---- luck check 1: nearby versions (realistic, pre-tax, 100-day / liquid parking)
        park = np.where(tsig(100), nr + dv, liq); base = sim(np.zeros_like(M), R, park); grid = []
        vol_cache = {None: np.ones_like(volok), 1.5: ~(vr > 1.5).values, 2.0: volok, 3.0: ~(vr > 3.0).values}
        for k in (150, 200):
            Mk = members(k).values; abk = above.values & Mk & ~glitch.values
            for th in (0.10, 0.11, 0.12, 0.13, 0.14):
                for vc in (None, 1.5, 2.0, 3.0):
                    for mx in (4, 5, 7):
                        S = (rl.values <= -th) & abk & vol_cache[vc]
                        r = sim(S, R, park, entry="open", cost=0.003, mx=mx); r.update(universe=k, dip=th, vol=vc, max_days=mx); grid.append(r)
            print("grid", k, len(grid), flush=True)
        cg = np.array([g_["cagr"] for g_ in grid]); dg = np.array([g_["dd"] for g_ in grid])
        OUT["checks"]["nearby"] = {"versions": len(grid), "parking_only": base, "median_cagr": float(np.median(cg)), "min_cagr": float(cg.min()), "max_cagr": float(cg.max()),
                                   "beat_parking_only": int((cg > base["cagr"]).sum()), "beat_nifty_pre_tax": int((cg > OUT["checks"]["nifty_hold_with_dividends_pre_tax"]["cagr"]).sum()),
                                   "median_dd": float(np.median(dg)), "worst_dd": float(dg.min()), "rows": grid}
        print("nearby", {k2: v for k2, v in OUT["checks"]["nearby"].items() if k2 != "rows"}, flush=True)
        # ---- luck check 2: random stocks instead of dips (same number of buys on the same days)
        rng = np.random.default_rng(7); elig = above.values & M & ~glitch.values; rnd = []
        cnt = S12.sum(axis=1)
        for seed in range(20):
            Sr = np.zeros_like(S12)
            for t in np.where(cnt > 0)[0]:
                cand = np.where(elig[t])[0]
                if len(cand): Sr[t, rng.choice(cand, size=min(cnt[t], len(cand)), replace=False)] = True
            r = sim(Sr, rng.random(R.shape), park, entry="open", cost=0.003); rnd.append(r["cagr"])
        real = sim(S12, R, park, entry="open", cost=0.003)
        OUT["checks"]["random"] = {"real_12pct_dips": real, "random_median": float(np.median(rnd)), "random_best": float(max(rnd)), "random_worst": float(min(rnd)), "runs": 20}
        print("random", OUT["checks"]["random"]["random_median"], max(rnd), "real", real["cagr"], flush=True)
        OUT["checks"]["assumptions"] = "Rs 10 lakh start; STCG 20.8%, LTCG 13% above Rs 1.25L/yr, liquid fund/gold/dividends at 31.2% slab; Nifty dividends ~1.3%/yr; liquid fund 6%/yr; realistic fills (next open, 0.30%/side); 0.05% per parking switch. Indian resident taxes only."
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_checks.json", "w"), indent=1, default=float); return
    if MODE == "trend":
        g = yahoo("GOLDBEES.NS"); gold = g.c.reindex(dates).ffill() if g is not None else None
        if gold is None or gold.notna().sum() < 1000:   # fallback: gold futures in USD x USDINR
            gu, fx = yahoo("GC=F"), yahoo("USDINR=X"); gold = (gu.c.reindex(dates).ffill() * fx.c.reindex(dates).ffill())
        gr = gold.pct_change().fillna(0).values
        OUT["gold_source"] = "GOLDBEES" if g is not None and g.c.reindex(dates).notna().sum() >= 1000 else "GC=F x USDINR"
        nm = n.copy(); me = nm.groupby(nm.index.to_period("M")).transform("last") == nm   # month-end closes
        def trend_sig(kind):
            if kind.endswith("m"):   # N-month average, checked at month ends only
                k = int(kind[:-1]); mc = nm[me]; ok = (mc > mc.rolling(k).mean()).reindex(dates).ffill().fillna(False)
            else: ok = nm > nm.rolling(int(kind)).mean()
            return ok.shift(1, fill_value=False).values.astype(bool)
        gtr = (gold > gold.rolling(100).mean()).shift(1, fill_value=False).values
        SW = 0.0005   # cost per switch (ETF, ~0.05%)
        def park_series(sig, below):
            alt = {"liquid": liq, "cash": np.zeros(D), "gold": gr, "gold if trending else liquid": np.where(gtr, gr, liq)}[below]
            r = np.where(sig, nr, alt).astype(float)
            sw = np.r_[False, sig[1:] != sig[:-1]]; r[sw] -= SW
            if below == "gold if trending else liquid":
                sw2 = np.r_[False, (gtr[1:] != gtr[:-1])] & ~sig; r[sw2] -= SW
            return r
        TR = {}
        for kind in ("50", "100", "150", "200", "10m"):
            for below in ("liquid", "cash", "gold", "gold if trending else liquid"):
                ps = park_series(trend_sig(kind), below); TR[(kind, below)] = ps
                r = summarize(np.cumprod(1 + ps) / np.prod(1 + ps[:START + 1])); r.update(avg=kind, below=below, scenario="parking only", switches_per_year=round(float(np.sum(np.r_[False, trend_sig(kind)[1:] != trend_sig(kind)[:-1]][START:]) / ((D - START) / 248)), 1))
                OUT["results"].append(r); print(kind, below, r["cagr"], r["dd"], r["switches_per_year"], r["per"], flush=True)
        # best dip version (top 200, 12% dip, skip volume > 2x) on top of each parking rule
        M = members(200).values; ab = above.values & M & ~glitch.values; R = (-rl).values; volok = ~(vr > 2.0).values
        for th in (0.10, 0.12):
            S = (rl.values <= -th) & ab & volok
            for (kind, below), ps in TR.items():
                if below not in ("liquid", "gold if trending else liquid"): continue
                for tag, kw in [("ideal", {}), ("realistic", dict(entry="open", cost=0.003))]:
                    r = sim(S, R, ps, **kw); r.update(avg=kind, below=below, scenario=tag, dip=f"{int(th*100)}% + volume<2x, top 200")
                    OUT["results"].append(r); print("dip", th, kind, below, tag, r["cagr"], r["dd"], flush=True)
        OUT["note"] += " Trend rule: hold Nifty while above its average (checked daily at the close, acted on next day; '10m' = 10-month average checked at month end); otherwise the 'below' choice. 0.05% per switch."
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_trend.json", "w"), indent=1, default=float); return
    for k in (100, 200):
        M = members(k).values; ab = above.values & M & ~glitch.values; R = (-rl).values; volok = ~(vr > 2.0).values
        for th in (0.08, 0.10, 0.12):
            S = (rl.values <= -th) & ab
            for vname, sig in [("no volume filter", S), ("skip volume > 2x", S & volok)]:
                for pname, park in PARK.items():
                    if th != 0.10 and pname != "Nifty trend (100-day), else liquid": continue
                    for tag, kw in [("ideal", {}), ("realistic", dict(entry="open", cost=0.003))]:
                        r = sim(S if sig is None else sig, R, park, **kw); r.update(universe=f"top {k}", dip=f"{int(th*100)}%", volume=vname, parking=pname, scenario=tag)
                        OUT["results"].append(r); print(k, th, vname, pname, tag, r["cagr"], r["dd"], r.get("win_rate"), r["per"], flush=True)
        # parking alone (no trades)
        for pname, park in PARK.items():
            r = sim(np.zeros_like(M), R, park); r.update(universe=f"top {k}", dip="none", volume="-", parking=pname, scenario="parking only"); OUT["results"].append(r)
    os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_dip.json", "w"), indent=1, default=float)
try: run()
except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open({"trend": "data/india_trend.json", "checks": "data/india_checks.json", "oos": "data/india_oos.json", "gold": "data/india_gold.json"}.get((sys.argv[1:2] or ["dip"])[0], "data/india_dip.json"), "w")); print(traceback.format_exc()); sys.exit(1)
