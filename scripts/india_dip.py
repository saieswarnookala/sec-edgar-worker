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
    def sim(S, R, park, cost=0.0015, entry="close", mx=5, slots=10, smart=True, curve_out=None):
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
                if p[1] >= mx or (smart and over5[t, p[0]]): eq *= 1 - cost * p[2]; tr.append(p[3] - 1 - 2 * cost)
                else: keep.append(p)
            pos = keep; used = sum(p[2] for p in pos); held = {p[0] for p in pos}
            new = [c for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
            if new:
                w = min(1.0 / slots, max(0.0, 1 - used) / len(new))
                for c in new: pos.append([c, 0, w, 1.0]); eq *= 1 - cost * w
            curve[t] = eq
        if curve_out is not None: curve_out.append(curve.copy())
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
    if MODE == "momentum":
        # Nov 21 2026: Indian momentum basket with a crash filter (research report idea #1), and a 50/50 mix with the dip bot.
        # Universe: top 200 or top 500 by traded value (approx point-in-time, re-picked every 6 months), price > Rs 20, glitch filter.
        # Score: 12-month return skipping the last month (12-1), or 6-month, or (6m + 12m) / volatility. Top 20 or 30, equal weight.
        # Rebalance monthly (first trading day) or semi-annually (Jan/Jul); a held stock stays while it ranks within 1.5x N (buffer).
        # Crash filter (checked at each rebalance; 'daily' variant checks every day): Nifty above its 200-day average, else park in
        # liquid fund (6%/yr) or gold-if-gold-above-its-100-day-avg. Costs 0.30% per side on every rupee traded. Before tax.
        g = yahoo("GOLDBEES.NS"); gold = g.c.reindex(dates).ffill(); gr = gold.pct_change().fillna(0).values
        gtr = (gold > gold.rolling(100).mean()).shift(1, fill_value=False).values
        dv = (1 + 0.013) ** (1 / 248) - 1
        nifty_ok = (n > n.rolling(200).mean()).shift(1, fill_value=False).values
        vol = r1.rolling(120, min_periods=80).std()
        SC = {"12-1 month": (Cf.shift(21) / Cf.shift(252) - 1), "6 month": Cf.pct_change(126), "(6m+12m)/volatility": (Cf.pct_change(126) + Cf.pct_change(252)) / (vol * np.sqrt(248))}
        months = [i for i in range(START, D) if dates[i].month != dates[i - 1].month]
        rows, curves = [], {}
        def mom(k, score, N, freq, filt, hide, cost=0.003):
            Mk = members(k).values; sc = SC[score].values; ok = Mk & ~glitch.values & np.isfinite(sc)
            rebal = set(months if freq == "monthly" else [i for i in months if dates[i].month in (1, 7)])
            w = {}; eq = 1.0; curve = np.ones(D); invested = []; turn = 0.0; inside = True; hold_days = {}; held_len = []
            hide_r = liq if hide == "liquid" else np.where(gtr, gr, liq)
            for t in range(START, D):
                day = sum(wi * Rt[t, j] for j, wi in w.items()); cash = 1 - sum(w.values())
                day += cash * (hide_r[t] if not inside else liq[t]); eq *= 1 + day
                w = {j: wi * (1 + Rt[t, j]) / (1 + day) for j, wi in w.items()}
                for j in w: hold_days[j] = hold_days.get(j, 0) + 1
                check = t in rebal or (filt == "daily" and inside != bool(nifty_ok[t]))
                if check:
                    inside = bool(nifty_ok[t]) if filt != "none" else True
                    if inside:
                        cand = np.where(ok[t])[0]; order = cand[np.argsort(-sc[t, cand])]; rank = {j: r for r, j in enumerate(order)}
                        keep = [j for j in w if rank.get(j, 1e9) < 1.5 * N][:N]
                        new = keep + [j for j in order if j not in keep][: N - len(keep)]
                        tgt = {j: 1.0 / N for j in new}
                    else: tgt = {}
                    tv_ = sum(abs(tgt.get(j, 0) - w.get(j, 0)) for j in set(tgt) | set(w)); eq *= 1 - cost * tv_; turn += tv_
                    for j in list(w):
                        if j not in tgt: held_len.append(hold_days.pop(j, 0))
                    w = dict(tgt)
                invested.append(sum(w.values())); curve[t] = eq
            o = summarize(curve); yrs = (D - START) / 248
            o.update(universe=f"top {k}", score=score, stocks=N, rebalance=freq, crash_filter=filt, hide_in=hide, turnover_per_year=round(turn / yrs, 1),
                     invested_pct=round(100 * float(np.mean(invested)), 1), held_over_1yr_pct=round(100 * float(np.mean(np.array(held_len) > 248)), 1) if held_len else None)
            return o, curve
        def show(o):
            print(f"MOM {o['universe']:7s} {o['score']:20s} N{o['stocks']} {o['rebalance']:11s} filter {o['crash_filter']:9s} hide {o['hide_in']:15s} {o['cagr']:6.1f}%/yr dd {o['dd']:6.1f} | "
                  f"08-09 {o['per']['2008-2009']} 10-15 {o['per']['2010-2015']} 16-20 {o['per']['2016-2020']} 21-26 {o['per']['2021-2026']} | test19-26 {o.get('test_2019_2026', {}).get('cagr')} | turn {o['turnover_per_year']}x/yr, >1yr {o['held_over_1yr_pct']}%", flush=True)
        for k in (200, 500):
            for score in SC:
                for N in (20, 30):
                    for freq in ("monthly", "semi-annual"):
                        for filt in ("none", "rebalance", "daily"):
                            hides = ("liquid", "gold or liquid") if filt != "none" else ("liquid",)
                            for hide in hides:
                                o, c = mom(k, score, N, freq, filt, hide); rows.append(o); show(o); curves[(k, score, N, freq, filt, hide)] = c
        # the dip bot (today's rules, realistic) and 50/50 mixes with the best-by-2008-2018 momentum version
        M2 = members(200).values; ab = above.values & M2 & ~glitch.values & ~(vr > 2.0).values; co = []
        dipr = sim((rl.values <= -0.12) & ab, (-rl).values, PARK["Nifty trend (100-day), else liquid"], cost=0.003, entry="open", curve_out=co)
        dipc = co[0]; OUT["dip_bot_today"] = dipr; print("DIP BOT today's rules", dipr["cagr"], dipr["dd"], dipr.get("test_2019_2026"), flush=True)
        pick = max([r for r in rows if r["crash_filter"] != "none"], key=lambda r: r["train_2008_2018"]["cagr"] / max(1, -r["train_2008_2018"]["dd"]))
        key = (int(pick["universe"].split()[1]), pick["score"], pick["stocks"], pick["rebalance"], pick["crash_filter"], pick["hide_in"])
        mc = curves[key]; mixes = {}
        for wm in (0.3, 0.5, 0.7):
            rm = np.r_[0, mc[1:] / mc[:-1] - 1]; rd = np.r_[0, dipc[1:] / dipc[:-1] - 1]
            mixes[f"{int(wm*100)}% momentum + {int((1-wm)*100)}% dip bot (rebalanced monthly-ish: daily weights)"] = summarize(np.cumprod(1 + wm * rm + (1 - wm) * rd))
        OUT["momentum"] = rows; OUT["picked_on_2008_2018_return_per_drop"] = pick; OUT["mixes_with_dip_bot"] = mixes
        print("PICKED (train 2008-2018 only)", json.dumps({k_: pick[k_] for k_ in ("universe", "score", "stocks", "rebalance", "crash_filter", "hide_in", "cagr", "dd", "train_2008_2018", "test_2019_2026")}), flush=True)
        for k_, v_ in mixes.items(): print("MIX", k_, v_["cagr"], v_["dd"], v_.get("test_2019_2026"), flush=True)
        OUT["note"] += " Momentum: before tax; a holding kept > 1 year gets 12.5% LTCG instead of 20% STCG."
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_momentum.json", "w"), indent=1, default=float); return
    if MODE == "timeframe":
        # Nov 21 2026: is the India dip bot on the wrong time frame? Same universe (top 200 by traded value), 200-day trend, 2x volume skip,
        # glitch filter, idle money = Nifty when above its 100-day avg else liquid fund. Realistic fills (next open, 0.30%/side) + ideal.
        # A) DIPS: look-back 1/2/3/5/10 days (drop threshold scaled ~ sqrt(days): 12% at 5 days), max hold 1/2/3/5/10 days,
        #    exit = back above 5-day avg OR max hold ("smart") vs fixed hold.
        # B) WINNERS (trend side): buy the strongest stocks vs Nifty over 20/40/60 days (top of the list, >= +10/15/20%), hold 20/40/60 days fixed.
        # C) Today's bot (5-day look-back, 12%, smart exit, max 5) for reference.
        M = members(200).values; ab = above.values & M & ~glitch.values & ~(vr > 2.0).values
        pk = PARK["Nifty trend (100-day), else liquid"]; rows = []
        def go(label, S, R, mx, smart, **kw):
            for scen, cost, entry in (("realistic", 0.003, "open"), ("ideal", 0.0015, "close")):
                r = sim(S, R, pk, cost=cost, entry=entry, mx=mx, smart=smart, **kw); r.update(test=label, scenario=scen); rows.append(r)
                if scen == "realistic":
                    yrs = (dates[-1] - dates[START]).days / 365.25
                    print(f"{label:62s} {r['cagr']:6.1f}%/yr dd {r['dd']:6.1f} | 08-09 {r['per']['2008-2009']} 10-15 {r['per']['2010-2015']} 16-20 {r['per']['2016-2020']} 21-26 {r['per']['2021-2026']} | "
                          f"test19-26 {r.get('test_2019_2026', {}).get('cagr')} | {r.get('trades', 0) / yrs:.0f} trades/yr avg {r.get('avg_trade_pct')}% win {r.get('win_rate')}%", flush=True)
        for L in (1, 2, 3, 5, 10):
            th = round(0.12 * (L / 5) ** 0.5, 3)
            rel = Cf.pct_change(L).sub(n.pct_change(L), axis=0)
            S = (rel.values <= -th) & ab; R = (-rel).values
            for mx in (1, 2, 3, 5, 10):
                go(f"DIP look-back {L}d (drop {th*100:.1f}%), smart exit, max {mx}d", S, R, mx, True)
            for mx in (1, 3, 5):
                go(f"DIP look-back {L}d (drop {th*100:.1f}%), FIXED hold {mx}d", S, R, mx, False)
        for L, th in ((20, 0.10), (40, 0.15), (60, 0.20)):
            rel = Cf.pct_change(L).sub(n.pct_change(L), axis=0)
            S = (rel.values >= th) & ab; R = rel.values
            for mx in (20, 40, 60):
                go(f"WINNERS look-back {L}d (up {int(th*100)}%+ vs Nifty), hold {mx}d", S, R, mx, False)
        OUT["timeframe"] = rows; OUT["note"] += " Before tax. Short holds pay 20% STCG on every gain; holds over a year 12.5%."
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_timeframe.json", "w"), indent=1, default=float); return
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
    if MODE == "bots":
        # Nov 16: the newer US paper bots, on India. Bot 5 = dips + sector/ETF dips sleeve (index 5-day drop >= 5% while above its
        # 200-day avg, sell on close > 5-day avg or after 10 days, fills slots after stocks); bot 6 = tuned (8% dip, 150-day trend,
        # hold 7) + sleeve. Sector indices stand in for their ETFs (Nifty sector ETFs exist for most). Realistic = next open,
        # 0.30%/side stocks, 0.15%/side sector ETFs; ideal = close, 0.15% / 0.05%.
        SECT = {"^NSEBANK": "Bank", "^CNXIT": "IT", "^CNXPHARMA": "Pharma", "^CNXAUTO": "Auto", "^CNXFMCG": "FMCG", "^CNXMETAL": "Metal",
                "^CNXENERGY": "Energy", "^CNXREALTY": "Realty", "^CNXPSUBANK": "PSU Bank", "^CNXMEDIA": "Media", "^CNXINFRA": "Infra",
                "^CNXPSE": "PSE", "^CNXMNC": "MNC", "^CNXCONSUM": "Consumption", "NIFTY_FIN_SERVICE.NS": "Financials", "^NSEMDCP50": "Midcap 50",
                "^CNXSC": "Smallcap", "^NSEI": "Nifty 50", "JUNIORBEES.NS": "Next 50", "GOLDBEES.NS": "Gold", "MON100.NS": "Nasdaq 100"}
        E = {}
        for sym, nm_ in SECT.items():
            d = yahoo(sym); time.sleep(0.3)
            if d is None: print("sector missing", sym, flush=True); continue
            c = d.c.reindex(dates).ffill(); o = d.o.reindex(dates).ffill()
            if c.notna().sum() < 1000: print("sector short history", sym, int(c.notna().sum()), flush=True); continue
            E[nm_] = (c, o)
        print("sector/ETF series used:", list(E), flush=True)
        if len(E) < 8: raise RuntimeError("too few sector series")
        EC = pd.DataFrame({k: v[0] for k, v in E.items()}); EO = pd.DataFrame({k: v[1] for k, v in E.items()})
        e5 = EC.pct_change(5); eab = EC > EC.rolling(200).mean()
        SE = ((e5 <= -0.05) & eab & EC.notna()).values; RE = (-e5).values
        RtE = EC.pct_change().fillna(0).values; OCE = (EC / EO - 1).values
        bad = ~np.isfinite(OCE) | (EO.values <= 0) | (np.abs(OCE) > 0.2); print('sector days with a bad open (use close-to-close instead):', int(bad.sum()), flush=True)
        OCE = np.where(bad, RtE, OCE); over5E = (EC > EC.rolling(5).mean()).values
        RtA, OCA, overA = np.hstack([Rt, RtE]), np.hstack([OC, OCE]), np.hstack([over5, over5E]); NS = Rt.shape[1]
        def sim2(S, R, park, SEs=None, cost=0.0015, cost_e=0.0005, entry="close", mx=5, mx_e=10, slots=10):
            eq = 1.0; curve = np.ones(D); pos = []; tr = []; tre = []; inv = []
            for t in range(START, D):
                used = sum(p[2] for p in pos); day = 0.0
                for p in pos:
                    g = OCA[t, p[0]] if (entry == "open" and p[1] == 0) else RtA[t, p[0]]
                    p[3] *= 1 + g; day += p[2] * g
                day += max(0.0, 1 - used) * park[t]; inv.append(used); eq *= 1 + day; keep = []
                for p in pos:
                    g = OCA[t, p[0]] if (entry == "open" and p[1] == 0) else RtA[t, p[0]]
                    p[1] += 1; p[2] *= (1 + g) / (1 + day); isE = p[0] >= NS; c_ = cost_e if isE else cost
                    if p[1] >= (mx_e if isE else mx) or overA[t, p[0]]:
                        eq *= 1 - c_ * p[2]; (tre if isE else tr).append(p[3] - 1 - 2 * c_)
                    else: keep.append(p)
                pos = keep; used = sum(p[2] for p in pos); held = {p[0] for p in pos}
                new = [c for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
                if SEs is not None and len(new) < slots - len(pos):
                    new += [NS + c for c in sorted(np.where(SEs[t])[0], key=lambda c: -RE[t, c]) if NS + c not in held][: slots - len(pos) - len(new)]
                if new:
                    w = min(1.0 / slots, max(0.0, 1 - used) / len(new))
                    for c in new: pos.append([c, 0, w, 1.0]); eq *= 1 - (cost_e if c >= NS else cost) * w
                curve[t] = eq
            o = summarize(curve, tr + tre, inv)
            if tre: o["sector_trades"] = len(tre); o["sector_avg_trade_pct"] = round(100 * float(np.mean(tre)), 2); o["sector_win_rate"] = round(100 * float((np.array(tre) > 0).mean()), 1)
            if tr: o["stock_trades"] = len(tr); o["stock_avg_trade_pct"] = round(100 * float(np.mean(tr)), 2)
            return o
        g = yahoo("GOLDBEES.NS"); gold = g.c.reindex(dates).ffill(); gr = gold.pct_change().fillna(0).values
        gtr = (gold > gold.rolling(100).mean()).shift(1, fill_value=False).values; dv = (1 + 0.013) ** (1 / 248) - 1
        def tsig(k): return (n > n.rolling(k).mean()).shift(1, fill_value=False).values.astype(bool)
        PK = {"Nifty 100-day trend, else liquid": np.where(tsig(100), nr + dv, liq),
              "Nifty 150-day trend, else gold-if-trending/liquid": np.where(tsig(150), nr + dv, np.where(gtr, gr, liq))}
        M = members(200).values; volok = ~(vr > 2.0).values; R = (-rl).values
        ab200 = above.values & M & ~glitch.values; ab150 = (Cf > Cf.rolling(150).mean()).values & M & ~glitch.values
        V_ = [("bot 1 rules (10% dip, 200-day, hold 5)", (rl.values <= -0.10) & ab200 & volok, 5, False),
              ("India best (12% dip, 200-day, hold 5)", (rl.values <= -0.12) & ab200 & volok, 5, False),
              ("bot 5: bot 1 rules + sector dips", (rl.values <= -0.10) & ab200 & volok, 5, True),
              ("India best + sector dips", (rl.values <= -0.12) & ab200 & volok, 5, True),
              ("bot 6 tuned (8% dip, 150-day, hold 7) + sector dips", (rl.values <= -0.08) & ab150 & volok, 7, True),
              ("bot 6 tuned without sector dips", (rl.values <= -0.08) & ab150 & volok, 7, False),
              ("sector dips only", np.zeros_like(ab200), 5, True),
              ("parking only", np.zeros_like(ab200), 5, False)]
        for pname, park in PK.items():
            for name, S, mx, sect in V_:
                for tag, kw in [("ideal", {}), ("realistic", dict(entry="open", cost=0.003, cost_e=0.0015)), ("stress 2x costs", dict(entry="open", cost=0.006, cost_e=0.003))]:
                    if tag == "stress 2x costs" and not name.startswith(("bot 6", "bot 5", "India best +")): continue
                    r = sim2(S, R, park, SE if sect else None, mx=mx, **kw); r.update(version=name, parking=pname, scenario=tag)
                    OUT["results"].append(r)
                    print(f"{pname[:22]:22s} | {name:52s} | {tag:15s} {r['cagr']:5.1f}%/yr dd {r['dd']:6.1f} | train {r.get('train_2008_2018', {}).get('cagr')} test {r.get('test_2019_2026', {}).get('cagr')} | sector trades {r.get('sector_trades', 0)} avg {r.get('sector_avg_trade_pct')}", flush=True)
        OUT["nifty_with_dividends_pct"] = summarize(np.cumprod(1 + nr + dv) / np.prod(1 + nr[:START + 1] + dv))
        os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_bots.json", "w"), indent=1, default=float); return
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
if __name__ == "__main__":
  try: run()
  except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open({"bots": "data/india_bots.json", "trend": "data/india_trend.json", "checks": "data/india_checks.json", "oos": "data/india_oos.json", "gold": "data/india_gold.json", "timeframe": "data/india_timeframe.json", "momentum": "data/india_momentum.json"}.get((sys.argv[1:2] or ["dip"])[0], "data/india_dip.json"), "w")); print(traceback.format_exc()); sys.exit(1)
