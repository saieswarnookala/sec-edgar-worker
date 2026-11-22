"""India strategies on SURVIVORSHIP-FREE data (Nov 21 2026). Research only, not financial advice.
Source: NSE daily bhavcopy archives (every stock traded each day, including ones later delisted / merged / suspended), 2006-2026,
cached privately in R2 (nse/bhav/<year>.json.gz). Daily return = CLOSE / PREVCLOSE - 1 (NSE adjusts PREVCLOSE on ex-dates for splits and
bonuses; checked below on known events). Prices exclude dividends (~1.3%/yr for Nifty), same for the Nifty 50 benchmark.
MODE fetch: download/cache missing days. MODE run: the tests (see run()). DRY=1: fake data."""
import os, sys, io, json, time, zipfile, urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DRY = os.environ.get("DRY") == "1"
if not DRY: import r2cache
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
SERIES = {"EQ", "BE", "BZ"}
def get(u, tries=4):
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(3 * (a + 1))
        except Exception: time.sleep(3 * (a + 1))
    return None
def yahoo(sym, start="2006-01-01"):
    p1 = int(pd.Timestamp(start).timestamp())
    b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1={p1}&period2={int(time.time())}&interval=1d")
    j = json.loads(b)["chart"]["result"][0]; q = j["indicators"]["quote"][0]
    adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
    s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); return s[~s.index.duplicated(keep="last")]
def bhav(d):
    """{symbol: [open, high, low, close, prevclose, traded value Rs]} for EQ/BE/BZ series on date d"""
    if d < pd.Timestamp("2024-07-08"):
        u = f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{d.year}/{MON[d.month-1]}/cm{d.day:02d}{MON[d.month-1]}{d.year}bhav.csv.zip"
    else: u = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    b = get(u)
    if not b: return None
    z = zipfile.ZipFile(io.BytesIO(b)); df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    df.columns = [c.strip() for c in df.columns]
    if "TckrSymb" in df.columns:
        df = df.rename(columns={"TckrSymb": "SYMBOL", "SctySrs": "SERIES", "OpnPric": "OPEN", "HghPric": "HIGH", "LwPric": "LOW", "ClsPric": "CLOSE", "PrvsClsgPric": "PREVCLOSE", "TtlTrfVal": "TOTTRDVAL"})
    df = df[df.SERIES.astype(str).str.strip().isin(SERIES)]
    return {str(r.SYMBOL).strip(): [float(r.OPEN), float(r.HIGH), float(r.LOW), float(r.CLOSE), float(r.PREVCLOSE), float(r.TOTTRDVAL)] for r in df.itertuples()}
def fetch():
    days = [d for d in yahoo("^NSEI").index if d >= pd.Timestamp("2006-06-01")]
    for y in sorted({d.year for d in days}):
        key = f"nse/bhav/{y}.json.gz"; cache = r2cache.load(key) or {}; miss = [d for d in days if d.year == y and str(d.date()) not in cache]
        print(y, "cached", len(cache), "missing", len(miss), flush=True); n = 0
        for d in miss:
            x = bhav(d); cache[str(d.date())] = x or {}; n += 1; time.sleep(0.4)
            if n % 60 == 0: r2cache.save(key, cache); print(" ", y, n, "of", len(miss), flush=True)
        if miss: r2cache.save(key, cache)
        print(y, "done:", sum(1 for v in cache.values() if v), "days with data", flush=True)
def load():
    """daily DataFrames (dates x symbols): close, prevclose, open, high, low, traded value"""
    if DRY:
        rng = np.random.default_rng(2); ix = pd.bdate_range("2006-06-01", "2026-11-20"); syms = [f"S{i}" for i in range(300)]
        C = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.022, (len(ix), len(syms))), axis=0)), index=ix, columns=syms)
        for i in range(0, 300, 7): C.iloc[rng.integers(500, len(ix)):, i] = np.nan          # delistings
        PC = C.shift(1); O = PC * (1 + rng.normal(0, 0.006, C.shape)); V = pd.DataFrame(rng.lognormal(18, 1.0, C.shape), index=ix, columns=syms).where(C.notna())
        return C, PC, O, C * 1.01, C * 0.99, V
    rows = {}
    for y in range(2006, pd.Timestamp.today().year + 1):
        c = r2cache.load(f"nse/bhav/{y}.json.gz") or {}; rows.update({d: v for d, v in c.items() if v})
    dates = sorted(rows); ix = pd.to_datetime(dates); syms = sorted({s for d in dates for s in rows[d]}); si = {s: i for i, s in enumerate(syms)}
    A = np.full((6, len(dates), len(syms)), np.nan, dtype=np.float32)
    for t, d in enumerate(dates):
        for s, v in rows[d].items(): A[:, t, si[s]] = v
    mk = lambda k: pd.DataFrame(A[k], index=ix, columns=syms)
    return mk(3), mk(4), mk(0), mk(1), mk(2), mk(5)
if __name__ == "__main__" and (sys.argv[1:2] or ["run"])[0] == "fetch": fetch(); sys.exit(0)

ETF_RX = r"(BEES|ETF|IETF|NIFTY|SENSEX|GOLD|SILVER|LIQUID|^SETF|^MON100|^MAFANG|BHARAT22|^MID150|^MOM\d|^ALPHA|^LOWVOL|^QUAL|^NV20|^MAHKTECH|^MASPTOP|^MAKEINDIA|^CONSUM|^INFRA|^PSUBNK|^ESG|^EBBETF|^HDFCSML|^HDFCMID|^ICICIB22|^GILT|^LTGILT|^SDL|^CPSE|^MOREALTY|^MODEFENCE|^AXIS|^TATSILV|^TATAGOLD|^EQUAL)"
def run():
    C, PC, O, H, L, V = load()
    keep = [s for s in C.columns if not pd.Series([s]).str.contains(ETF_RX, regex=True).iloc[0]]
    C, PC, O, H, L, V = (x[keep] for x in (C, PC, O, H, L, V))
    dates = C.index; D = len(dates); tick = list(C.columns)
    if DRY: n = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0.0003, 0.011, D))), index=dates); gold = n * 0 + 100 * np.exp(np.cumsum(np.random.default_rng(4).normal(0.0003, 0.009, D)))
    else: n = yahoo("^NSEI").reindex(dates).ffill(); gold = yahoo("GOLDBEES.NS").reindex(dates).ffill()
    print("stocks (ex ETFs):", len(tick), "| days", D, dates[0].date(), "->", dates[-1].date(), flush=True)
    R = (C / PC - 1).where(C.notna() & PC.notna() & (PC > 0))
    # NSE bhavcopy PREVCLOSE is NOT adjusted for splits/bonuses. Price bands cap real moves at 20% for most stocks, so an overnight gap of
    # -18% or worse (or +80% or more: reverse split) is treated as a corporate action: that day keeps only its open -> close move.
    gap = (O / PC - 1).where((O > 0) & (PC > 0))
    ca = ((gap <= -0.18) | (gap >= 0.8) | (R <= -0.30) | (R >= 0.8)).fillna(False)
    R = R.mask(ca, ((C / O - 1).where(O > 0)).clip(-0.2, 0.2))
    print("corporate-action days fixed:", int(ca.values.sum()), flush=True)
    R = R.where(R.abs() < 0.6)
    Rt = R.fillna(0).values
    # validation vs Yahoo adjusted prices (splits/bonuses) for big names
    if not DRY:
        for s in ("RELIANCE", "INFY", "TCS", "HDFCBANK", "ITC", "SBIN"):
            try:
                y = yahoo(s + ".NS", "2010-01-01"); a = (1 + R[s].loc["2010-01-04":].fillna(0)).prod(); b = y.iloc[-1] / y.loc["2010-01-04":].iloc[0]
                print(f"CHECK {s}: NSE growth x{a:.2f} vs Yahoo adjusted x{b:.2f} (Yahoo includes dividends: expect NSE ~15-35% lower)", flush=True)
            except Exception as e: print("CHECK", s, "failed", e)
    tv = V.rolling(120, min_periods=60).median(); RC = C
    halves = [i for i in range(1, D) if dates[i].month in (1, 7) and dates[i - 1].month not in (1, 7)]
    START = int(np.searchsorted(dates.values, np.datetime64("2009-01-01")))   # NSE archive has only ~72 days of 2007 -> start once 12-month look-backs exist
    traded = C.notna().values
    def members(k):
        M = np.zeros((D, len(tick)), bool); b = halves + [D]
        for a, z in zip(b[:-1], b[1:]):
            row = tv.iloc[a - 1]; row = row[(RC.iloc[a - 1] > 20)].dropna().sort_values(ascending=False)
            M[a:z, [tick.index(s) for s in row.index[:k]]] = True
        return M & traded
    # cumulative (adjusted) price from returns, for averages and look-backs
    P = (1 + R.fillna(0)).cumprod().where(C.notna()); Pf = P.ffill()
    glitch = (R.abs() > 0.35).rolling(6, min_periods=1).max().fillna(0).astype(bool).values
    above = (Pf > Pf.rolling(200, min_periods=180).mean()).values
    over5 = (Pf > Pf.rolling(5).mean()).values
    nr = n.pct_change().fillna(0); nr = nr.where(nr.abs() < 0.2, 0).values
    gr = gold.pct_change().fillna(0); print("gold days dropped (bad prints):", int((gr.abs() >= 0.15).sum()), flush=True); gr = gr.where(gr.abs() < 0.15, 0).values
    gold = pd.Series(np.cumprod(1 + gr), index=dates)
    liq = np.full(D, (1.06) ** (1 / 248) - 1); dv = (1.013) ** (1 / 248) - 1
    ntr = (n > n.rolling(100).mean()).shift(1, fill_value=False).values
    park_dip = np.where(ntr, nr + dv, liq)
    OCr = ((C / O) - 1).where(O > 0).fillna(0).values                  # open -> close return on the buy day
    vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5)).values
    locked = ((H == L) & C.notna()).rolling(60, min_periods=20).mean().values     # share of days stuck at a circuit (high == low)
    def summ(curve, tr=None):
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0); yrs = len(p) / 248
        per = {}
        for a, b in (("2009", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")):
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[f"{a}-{b}"] = round(100 * ((1 + q).prod() ** (248 / max(len(q), 1)) - 1), 1)
        o = {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * float((c / c.cummax() - 1).min()), 1), "per": per}
        for nm_, a, b in (("train_2009_2018", "2009", "2018-12-31"), ("test_2019_2026", "2019", "2100")):
            q = c[(c.index >= a) & (c.index <= b)]; o[nm_] = {"cagr": round(100 * ((q.iloc[-1] / q.iloc[0]) ** (248 / len(q)) - 1), 1), "dd": round(100 * float((q / q.cummax() - 1).min()), 1)}
        yr = c.resample("YE").last(); g = yr.pct_change(); g.iloc[0] = yr.iloc[0] / c.iloc[0] - 1
        at, carry = 1.0, 0.0                                            # rough after-tax: 20.8% on each year's net gain, losses carried
        for x in g.values:
            gain = at * x; net = gain + carry; tax = 0.208 * net if net > 0 else 0.0; carry = 0.0 if net > 0 else net; at += gain - tax
        o["after_tax_rough_cagr"] = round(100 * (at ** (1 / yrs) - 1), 1)
        if tr: o["trades_per_year"] = round(len(tr) / yrs); o["avg_trade_pct"] = round(100 * float(np.mean(tr)), 2); o["win_pct"] = round(100 * float(np.mean(np.array(tr) > 0)), 1)
        return o
    def dip(lb=5, th=0.12, k=200, mx=5, cost=0.003, filters=False, slots=10):
        M = members(k); rel = (Pf.pct_change(lb).values - n.pct_change(lb).values[:, None])
        S = (rel <= -th) & M & above & ~glitch & ~(np.nan_to_num(vr, nan=9) > 2.0)
        if filters:
            S &= ~(np.nan_to_num(locked, nan=0) >= 0.2)
            tvv = tv.values; S &= ~(tvv < np.nanpercentile(np.where(M, tvv, np.nan), 10, axis=1)[:, None])
        eq = 1.0; curve = np.ones(D); pos = []; tr = []
        for t in range(START, D):
            used = sum(p[2] for p in pos); day = 0.0
            for p in pos:
                g = OCr[t, p[0]] if p[1] == 0 else Rt[t, p[0]]; p[3] *= 1 + g; day += p[2] * g
            day += max(0.0, 1 - used) * park_dip[t]; eq *= 1 + day; keep_ = []
            for p in pos:
                g = OCr[t, p[0]] if p[1] == 0 else Rt[t, p[0]]; p[1] += 1; p[2] *= (1 + g) / (1 + day)
                if p[1] >= mx or over5[t, p[0]] or not traded[t, p[0]]: eq *= 1 - cost * p[2]; tr.append(p[3] - 1 - 2 * cost)
                else: keep_.append(p)
            pos = keep_; used = sum(p[2] for p in pos); held = {p[0] for p in pos}
            if t + 1 < D:                                                # signal at t's close, buy at t+1's open (realistic)
                new = [c for c in sorted(np.where(S[t])[0], key=lambda c: rel[t, c]) if c not in held and traded[t + 1, c]][: max(0, slots - len(pos))]
                for c in new:
                    w = min(1.0 / slots, max(0.0, 1 - used)); used += w
                    if w > 0: pos.append([c, 0, w, 1.0]); eq *= 1 - cost * w
            curve[t] = eq
        return summ(curve, tr), curve
    vol = R.rolling(120, min_periods=80).std()
    SC = {"12-1 month": (Pf.shift(21) / Pf.shift(252) - 1), "6 month": Pf.pct_change(126), "(6m+12m)/volatility": (Pf.pct_change(126) + Pf.pct_change(252)) / (vol * np.sqrt(248))}
    months = [i for i in range(START, D) if dates[i].month != dates[i - 1].month]
    nifty_ok = (n > n.rolling(200).mean()).shift(1, fill_value=False).values
    gtr = (gold > gold.rolling(100).mean()).shift(1, fill_value=False).values
    def mom(k, score, N, freq, filt, hide, cost=0.003):
        Mk = members(k); sc = SC[score].values; ok = Mk & ~glitch & np.isfinite(sc)
        rebal = set(months if freq == "monthly" else [i for i in months if dates[i].month in (1, 7)])
        w = {}; eq = 1.0; curve = np.ones(D); turn = 0.0; inside = True
        hide_r = liq if hide == "liquid" else np.where(gtr, gr, liq)
        for t in range(START, D):
            day = sum(wi * Rt[t, j] for j, wi in w.items()); cash = 1 - sum(w.values())
            day += cash * (hide_r[t] if not inside else liq[t]); eq *= 1 + day
            w = {j: wi * (1 + Rt[t, j]) / (1 + day) for j, wi in w.items()}
            gone = [j for j in w if not traded[t, j]]                     # delisted / suspended: out at the last price
            for j in gone: w.pop(j)
            if t in rebal or (filt == "daily" and inside != bool(nifty_ok[t])):
                inside = bool(nifty_ok[t]) if filt != "none" else True
                if inside:
                    cand = np.where(ok[t])[0]; order = cand[np.argsort(-sc[t, cand])]; rank = {j: r for r, j in enumerate(order)}
                    kept = [j for j in w if rank.get(j, 1e9) < 1.5 * N][:N]; new = kept + [j for j in order if j not in kept][: N - len(kept)]
                    tgt = {j: 1.0 / N for j in new}
                else: tgt = {}
                tv_ = sum(abs(tgt.get(j, 0) - w.get(j, 0)) for j in set(tgt) | set(w)); eq *= 1 - cost * tv_; turn += tv_; w = dict(tgt)
            curve[t] = eq
        o = summ(curve); o.update(universe=f"top {k}", score=score, stocks=N, rebalance=freq, crash_filter=filt, hide_in=hide, turnover_per_year=round(turn / ((D - START) / 248), 1))
        return o, curve
    def pr(lbl, o): print(f"{lbl:64s} {o['cagr']:6.1f}%/yr (after tax ~{o['after_tax_rough_cagr']}) dd {o['dd']:6.1f} | 2009 {o['per']['2009-2009']} 10-15 {o['per']['2010-2015']} 16-20 {o['per']['2016-2020']} 21-26 {o['per']['2021-2026']} | train {o['train_2009_2018']['cagr']} test {o['test_2019_2026']['cagr']}/{o['test_2019_2026']['dd']}" + (f" | {o.get('trades_per_year')} tr/yr avg {o.get('avg_trade_pct')}%" if 'trades_per_year' in o else f" | turn {o.get('turnover_per_year')}x"), flush=True)
    MODE = os.environ.get("MODE", "all")
    if MODE == "momrisk":
        # Ways to cut the momentum basket's worst drop (base = the picked version: top 500, (6m+12m)/vol, 20 stocks, monthly,
        # Nifty-200-day filter at reshuffles, hide in gold-if-trending else liquid).
        Mk = members(500); sc = SC["(6m+12m)/volatility"].values; ok = Mk & ~glitch & np.isfinite(sc)
        nma = {m: (n > n.rolling(m).mean()).shift(1, fill_value=False).values for m in (50, 100, 200)}
        hide_r = np.where(gtr, gr, liq)
        wk = [i for i in range(START, D) if dates[i].weekday() < dates[i - 1].weekday() or (dates[i] - dates[i - 1]).days > 3]
        def mom2(freq="monthly", ma=200, check="rebalance", stop=None, trail=None, ddstop=None, voltgt=None, N=20, cost=0.003):
            rebal = set(months if freq == "monthly" else wk if freq == "weekly" else wk[::2])
            w = {}; entry = {}; peakpx = {}; eq = 1.0; curve = np.ones(D); turn = 0.0; inside = True; peak = 1.0; stopped = False; hist = []
            for t in range(START, D):
                day = sum(wi * Rt[t, j] for j, wi in w.items()); cash = 1 - sum(w.values())
                day += cash * (hide_r[t] if not inside or stopped else liq[t]); eq *= 1 + day; hist.append(day)
                w = {j: wi * (1 + Rt[t, j]) / (1 + day) for j, wi in w.items()}
                for j in list(w):
                    entry[j] *= 1 + Rt[t, j]; peakpx[j] = max(peakpx[j], entry[j])
                    if not traded[t, j] or (stop and entry[j] <= 1 - stop) or (trail and entry[j] <= peakpx[j] * (1 - trail)):
                        eq *= 1 - cost * w[j]; turn += w[j]; w.pop(j)
                peak = max(peak, eq)
                if ddstop and not stopped and eq <= peak * (1 - ddstop):
                    turn += sum(w.values()); eq *= 1 - cost * sum(w.values()); w = {}; stopped = True
                go = t in rebal or (check == "daily" and inside != bool(nma[ma][t]))
                if go:
                    inside = bool(nma[ma][t]); stopped = False if t in rebal else stopped
                    if stopped: peak = eq
                    if inside and not stopped:
                        cand = np.where(ok[t])[0]; order = cand[np.argsort(-sc[t, cand])]; rank = {j: r for r, j in enumerate(order)}
                        kept = [j for j in w if rank.get(j, 1e9) < 1.5 * N][:N]; new = kept + [j for j in order if j not in kept][: N - len(kept)]
                        scale = 1.0
                        if voltgt and len(hist) > 60: rv = float(np.std(hist[-60:]) * np.sqrt(248)); scale = min(1.0, voltgt / max(rv, 1e-6))
                        tgt = {j: scale / N for j in new}
                    else: tgt = {}
                    tv_ = sum(abs(tgt.get(j, 0) - w.get(j, 0)) for j in set(tgt) | set(w)); eq *= 1 - cost * tv_; turn += tv_
                    for j in tgt:
                        if j not in w: entry[j] = 1.0; peakpx[j] = 1.0
                    w = dict(tgt); peak = max(peak, eq) if not stopped else peak
                curve[t] = eq
            o = summ(curve); o["turnover_per_year"] = round(turn / ((D - START) / 248), 1); return o, curve
        V = [("base: monthly reshuffle, 200-day filter at reshuffle (paper bot)", {}),
             ("reshuffle every 2 weeks", dict(freq="biweekly")), ("reshuffle weekly", dict(freq="weekly")),
             ("filter 100-day avg, at reshuffle", dict(ma=100)), ("filter 50-day avg, at reshuffle", dict(ma=50)),
             ("filter 200-day, checked daily", dict(check="daily")), ("filter 100-day, checked daily", dict(check="daily", ma=100)), ("filter 50-day, checked daily", dict(check="daily", ma=50)),
             ("stop-loss: sell a stock -15% from buy", dict(stop=0.15)), ("stop-loss: sell a stock -25% from buy", dict(stop=0.25)),
             ("trailing stop: sell a stock -20% from its high", dict(trail=0.20)), ("trailing stop: -30% from its high", dict(trail=0.30)),
             ("basket stop: all out if basket -15% from its peak (back in next month)", dict(ddstop=0.15)), ("basket stop: -20% from peak", dict(ddstop=0.20)),
             ("volatility target 20% (smaller basket when markets are wild)", dict(voltgt=0.20)), ("volatility target 25%", dict(voltgt=0.25)),
             ("30 stocks instead of 20", dict(N=30)),
             ("combo: 100-day filter daily + volatility target 25%", dict(check="daily", ma=100, voltgt=0.25)),
             ("combo: basket stop -15% + volatility target 25%", dict(ddstop=0.15, voltgt=0.25))]
        OUTR = {"note": "Momentum risk-control variants on survivorship-free NSE data, 2009-2026, 0.30%/side, before tax (after-tax rough)", "built": str(pd.Timestamp.today().date()), "variants": {}, "mix_50_50_with_dip": {}}
        _, dc = dip(); rd = np.r_[0, dc[1:] / dc[:-1] - 1]
        ref, _ = mom(500, "(6m+12m)/volatility", 20, "monthly", "rebalance", "gold or liquid"); chk, _ = mom2()
        print("CHECK base matches the 96-version engine:", ref["cagr"], chk["cagr"], ref["dd"], chk["dd"], flush=True); assert abs(ref["cagr"] - chk["cagr"]) < 0.25, "engine mismatch"
        for lbl, kw in V:
            o, c = mom2(**kw); OUTR["variants"][lbl] = o; pr("RISK " + lbl, o)
            rm = np.r_[0, c[1:] / c[:-1] - 1]; OUTR["mix_50_50_with_dip"][lbl] = summ(np.cumprod(1 + 0.5 * rm + 0.5 * rd))
            m = OUTR["mix_50_50_with_dip"][lbl]; print(f"     50/50 with dip bot: {m['cagr']}%/yr dd {m['dd']} test {m['test_2019_2026']}", flush=True)
        os.makedirs("data", exist_ok=True); json.dump(OUTR, open("data/india_momrisk.json" if not DRY else "/tmp/india_momrisk_dry.json", "w"), indent=1, default=float); print("wrote", flush=True); return
    OUT = {"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "stocks": len(tick)}
    bench = summ(np.cumprod(1 + nr + dv)); OUT["nifty50_with_dividends"] = bench; pr("NIFTY 50 (+1.3% dividends)", bench)
    # 1) dip bot variants
    OUT["dip"] = {}; CUR = {}
    for lbl, kw in (("dip bot today (5d, 12%, top 200)", {}), ("dip bot + NSE filters (circuit-locked, low turnover)", dict(filters=True)),
                    ("dip 10-day look-back, 17%", dict(lb=10, th=0.17)), ("dip 10-day, 17% + NSE filters", dict(lb=10, th=0.17, filters=True)),
                    ("dip bot, top 500", dict(k=500)), ("dip bot, 2x costs", dict(cost=0.006))):
        o, c = dip(**kw); OUT["dip"][lbl] = o; CUR[lbl] = c; pr("DIP " + lbl, o)
    # 2) momentum grid
    rows, curves = [], {}
    for k in (200, 500):
        for score in SC:
            for N in (20, 30):
                for freq in ("monthly", "semi-annual"):
                    for filt, hide in (("none", "liquid"), ("rebalance", "liquid"), ("rebalance", "gold or liquid"), ("daily", "gold or liquid")):
                        o, c = mom(k, score, N, freq, filt, hide); rows.append(o); curves[len(rows) - 1] = c
                        pr(f"MOM {o['universe']} {score} N{N} {freq} filter {filt} hide {hide}", o)
    OUT["momentum"] = rows
    pi = max(range(len(rows)), key=lambda i: rows[i]["train_2009_2018"]["cagr"] / max(1, -rows[i]["train_2009_2018"]["dd"]) if rows[i]["crash_filter"] != "none" else -1)
    OUT["momentum_picked_on_2009_2018"] = rows[pi]; pr("PICKED (2009-2018 only) " + json.dumps({k_: rows[pi][k_] for k_ in ('universe', 'score', 'stocks', 'rebalance', 'crash_filter', 'hide_in')}), rows[pi])
    med = lambda key, f: float(np.median([r[key] if not isinstance(r[key], dict) else r[key]["cagr"] for r in rows if f(r)]))
    OUT["momentum_medians"] = {f"{k} | filter {fl}": {"cagr": med("cagr", lambda r: r["universe"] == k and r["crash_filter"] == fl), "dd": med("dd", lambda r: r["universe"] == k and r["crash_filter"] == fl),
                               "test_2019_2026": med("test_2019_2026", lambda r: r["universe"] == k and r["crash_filter"] == fl)} for k in ("top 200", "top 500") for fl in ("none", "rebalance", "daily")}
    for k_, v_ in OUT["momentum_medians"].items(): print("MEDIAN", k_, v_, flush=True)
    # 3) mixes: picked momentum + dip bot
    mc = curves[pi]; dc = CUR["dip bot today (5d, 12%, top 200)"]; rm = np.r_[0, mc[1:] / mc[:-1] - 1]; rd = np.r_[0, dc[1:] / dc[:-1] - 1]
    OUT["mixes"] = {}
    for wm in (0.3, 0.5, 0.7):
        o = summ(np.cumprod(1 + wm * rm + (1 - wm) * rd)); OUT["mixes"][f"{int(wm*100)}% momentum + {int(100-wm*100)}% dip"] = o; pr(f"MIX {int(wm*100)}% momentum + {int(100-wm*100)}% dip", o)
    OUT["correlation_monthly_momentum_vs_dip"] = round(float(pd.Series(mc[START:], index=dates[START:]).resample("ME").last().pct_change().corr(pd.Series(dc[START:], index=dates[START:]).resample("ME").last().pct_change())), 2)
    # 4) Nifty / gold / liquid dual momentum (monthly, best 12-month return, 1% switch buffer)
    lv = np.cumprod(1 + liq); ser = {"nifty": pd.Series(np.cumprod(1 + nr + dv), index=dates), "gold": pd.Series(np.cumprod(1 + gr), index=dates), "liquid": pd.Series(lv, index=dates)}
    rr = {"nifty": nr + dv, "gold": gr, "liquid": liq}; hold = "nifty"; eq = 1.0; curve = np.ones(D); sw = 0
    for t in range(START, D):
        eq *= 1 + rr[hold][t]
        if t in set(months):
            m12 = {a: ser[a].iloc[t] / ser[a].iloc[max(0, t - 252)] - 1 for a in ser}; best = max(m12, key=m12.get)
            if best != hold and m12[best] > m12[hold] + 0.01: eq *= 1 - 0.002; hold = best; sw += 1
        curve[t] = eq
    o = summ(curve); o["switches_per_year"] = round(sw / ((D - START) / 248), 1); OUT["dual_momentum_nifty_gold_liquid"] = o; pr("DUAL MOMENTUM nifty/gold/liquid", o)
    os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/india_pit.json" if not DRY else "/tmp/india_pit_dry.json", "w"), indent=1, default=float); print("wrote", flush=True)
if __name__ == "__main__" and (sys.argv[1:2] or ["run"])[0] == "run": run()
