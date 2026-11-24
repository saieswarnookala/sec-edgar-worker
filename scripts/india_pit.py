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
        base = curve[START - 1] if START > 0 and np.isfinite(curve[START - 1]) and curve[START - 1] > 0 else curve[START]
        c = pd.Series(curve[START:] / base, index=dates[START:]); p = c.pct_change().fillna(0); p.iloc[0] = c.iloc[0] - 1; yrs = len(p) / 248   # Nov 22 fix: measure from START, not from the curve's own start (benchmarks started in 2007)
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
    if MODE == "factor":
        # Test #5 (factor rotation) + #7 (large vs mid/small switch), Nov 22 2026. niftyindices.com's TRI download now needs a login, so the
        # price-based factor indices are REBUILT here from survivorship-free NSE data (equal weight; NSE's own indices are cap/score weighted).
        # Value and Quality need company financials -> not possible with price data. Index funds: 0.4%/yr fee; switching 0.2% per buy/sell.
        mstarts = [i for i in range(1, D) if dates[i].month != dates[i - 1].month]
        qtr = [i for i in mstarts if dates[i].month in (1, 4, 7, 10)]
        mret = n.pct_change().fillna(0).values
        def build(memb, score, N, rebal, low=False):
            """equal-weight factor index; score(t, cols) -> values (higher = better unless low)"""
            rb = set(i for i in rebal if i >= START - 260); w = {}; eq = 1.0; curve = np.full(D, np.nan); started = False
            for t in range(min(rb), D):
                if w:
                    day = sum(wi * Rt[t, j] for j, wi in w.items()); eq *= 1 + day; w = {j: wi * (1 + Rt[t, j]) / (1 + day) for j, wi in w.items()}
                    for j in [j for j in w if not traded[t, j]]: w.pop(j)
                    if w: s_ = sum(w.values()); w = {j: wi / s_ for j, wi in w.items()}
                if t in rb:
                    cols = np.where(memb[t] & ~glitch[t])[0]
                    v = score(t, cols); okc = np.isfinite(v); cols, v = cols[okc], v[okc]
                    if len(cols) >= N: pick_ = cols[np.argsort(v if low else -v)[:N]]; w = {j: 1.0 / N for j in pick_}; started = True
                if started: curve[t] = eq
            return curve
        M100, M200, M250, M300, M500 = members(100), members(200), members(250), members(300), members(500)
        momsc = SC["(6m+12m)/volatility"].values
        def s_mom(t, cols): return momsc[t, cols]
        def s_lv(t, cols): return np.nanstd(np.where(np.isfinite(R.values[t - 251:t + 1, cols]), R.values[t - 251:t + 1, cols], np.nan), axis=0) if t >= 251 else np.full(len(cols), np.nan)
        def s_alpha(t, cols):
            if t < 251: return np.full(len(cols), np.nan)
            X = R.values[t - 251:t + 1, cols]; m = mret[t - 251:t + 1]; good = np.isfinite(X).sum(0) >= 200
            Xf = np.where(np.isfinite(X), X, 0.0); mm = m - m.mean(); b = (mm[:, None] * (Xf - Xf.mean(0))).sum(0) / (mm ** 2).sum()
            a = (Xf.mean(0) - b * m.mean()) * 248; a[~good] = np.nan; return a
        def s_eq(t, cols): return np.zeros(len(cols))
        print("building factor indices ...", flush=True)
        FX = {"Momentum 30 (top 200, (6m+12m)/vol, 6-monthly)": build(M200, s_mom, 30, halves),
              "Low Vol 30 (top 100, lowest 1-yr volatility, quarterly)": build(M100, s_lv, 30, qtr, low=True),
              "Alpha 50 (top 300, highest 1-yr alpha vs Nifty, quarterly)": build(M300, s_alpha, 50, qtr),
              "Large 100 (top 100, equal weight)": build(M100, s_eq, 100, halves),
              "Mid 150 (ranks 101-250, equal weight)": build(M250 & ~M100, s_eq, 150, halves),
              "Small 250 (ranks 251-500, equal weight)": build(M500 & ~M250, s_eq, 250, halves)}
        FX["Nifty 50 (+1.3% dividends)"] = np.cumprod(1 + nr + dv)
        keys = list(FX); short = {k: k.split(" (")[0] for k in keys}
        IR = {k: np.nan_to_num(np.r_[0, FX[k][1:] / FX[k][:-1] - 1], nan=0.0) for k in keys}
        n_on = (n > n.rolling(100).mean()).values; g_on = (gold > gold.rolling(100).mean()).values
        me = [i - 1 for i in mstarts if i - 1 >= START]                    # month-end rows
        FEE = 0.004 / 248; CST = 0.002
        def engine(pick, freq="M", filt=False):
            reb = set(me if freq == "M" else [i for i in me if dates[i].month in (6, 12)])
            w = {}; pend = None; eq = 1.0; curve = np.full(D, np.nan); sw = 0; turn = 0.0
            for t in range(START, D):
                day = sum(wi * (gr[t] if k == "gold" else liq[t] if k == "liq" else IR[k][t] - FEE) for k, wi in w.items()); eq *= 1 + day
                w = {k: wi * (1 + (gr[t] if k == "gold" else liq[t] if k == "liq" else IR[k][t] - FEE)) / (1 + day) for k, wi in w.items()}
                if pend is not None:
                    tv_ = sum(abs(pend.get(k, 0) - w.get(k, 0)) for k in set(pend) | set(w)); eq *= 1 - CST * tv_; turn += tv_
                    if set(pend) != set(w): sw += 1
                    w = dict(pend); pend = None
                curve[t] = eq if w else np.nan
                if t in reb:
                    tg = pick(t)
                    if tg is None: continue
                    if filt and not n_on[t]: tg = {"gold": 1.0} if g_on[t] else {"liq": 1.0}
                    pend = tg
            c = np.where(np.isfinite(curve), curve, np.nan); first = int(np.argmax(np.isfinite(c))); c[:first] = c[first]
            o = summ(c); yrs_ = (D - START) / 248; o.update(switches_per_year=round(sw / yrs_, 1), turnover_per_year=round(turn / yrs_, 1)); return o
        tr_ = lambda k, t, lb: FX[k][t] / FX[k][t - 21 * lb] - 1 if t - 21 * lb >= 0 and np.isfinite(FX[k][t]) and np.isfinite(FX[k][t - 21 * lb]) else np.nan
        OUTF = {"note": "India factor rotation (#5) and size switch (#7) on factor indices REBUILT from survivorship-free NSE data (equal weight), 2009-2026. "
                        "Signal at month-end close, trade next day. Index-fund fee 0.4%/yr, 0.2% per buy/sell. After-tax rough = 20.8% on each year's net gain. "
                        "No Value/Quality (needs company financials). Paper bot 13 basket for comparison: 32.6%/yr best case, ~27% realistic.",
                "built": str(pd.Timestamp.today().date()), "hold": {}, "blend": {}, "rotation": {}, "size_switch": {}}
        FAC = keys[:3]; SIZE = [keys[6], keys[4], keys[5]]
        for k in keys:
            o = engine(lambda t, k=k: {k: 1.0} if np.isfinite(FX[k][t]) else None); OUTF["hold"][k] = o; pr("HOLD " + k, o)
        for lbl, ks in (("Momentum + Low Vol (50/50)", [keys[0], keys[1]]), ("Momentum + Alpha (50/50)", [keys[0], keys[2]]), ("Momentum + Low Vol + Alpha (1/3 each)", FAC)):
            for filt in (False, True):
                o = engine(lambda t, ks=ks: {k: 1 / len(ks) for k in ks}, "S", filt); kk = lbl + (" + crash filter" if filt else ""); OUTF["blend"][kk] = o; pr("BLEND " + kk, o)
        for uni_l, uni in (("3 factors", FAC), ("3 factors + Nifty 50", FAC + [keys[6]])):
            for lb in (6, 12):
                for top in (1, 2):
                    for freq in ("M", "S"):
                        for filt in (False, True):
                            def pick(t, uni=uni, lb=lb, top=top):
                                sc_ = {k: tr_(k, t, lb) for k in uni}; sc_ = {k: v for k, v in sc_.items() if np.isfinite(v)}
                                b_ = sorted(sc_, key=lambda k: -sc_[k])[:top]; return {k: 1 / len(b_) for k in b_} if b_ else None
                            o = engine(pick, freq, filt); kk = f"{uni_l} | top {top} by {lb}-month return | {'monthly' if freq == 'M' else 'every 6 months'}{' | crash filter' if filt else ''}"
                            OUTF["rotation"][kk] = o; pr("ROT " + kk, o)
        for lbl, uni in (("Large vs Mid", [keys[3], keys[4]]), ("Large vs Mid vs Small", [keys[3], keys[4], keys[5]]), ("Nifty 50 vs Mid vs Small", SIZE)):
            for lb in (6, 12):
                def pick(t, uni=uni, lb=lb):
                    sc_ = {k: tr_(k, t, lb) for k in uni}; sc_ = {k: v for k, v in sc_.items() if np.isfinite(v)}
                    if not sc_: return None
                    b_ = max(sc_, key=sc_.get); return {b_: 1.0} if sc_[b_] > 1.06 ** (lb / 12) - 1 else {"liq": 1.0}
                o = engine(pick); kk = f"{lbl} | best {lb}-month return, liquid fund if none beats 6%/yr | monthly"; OUTF["size_switch"][kk] = o; pr("SIZE " + kk, o)
        mo = pd.DataFrame({short[k]: FX[k] for k in keys}, index=dates).iloc[START:].resample("ME").last().pct_change().dropna()
        OUTF["monthly_correlation"] = mo.corr().round(2).to_dict()
        last = int(np.searchsorted(dates.values, np.datetime64("2026-10-31"), side="right")) - 1
        def win(k, y_):
            a_ = int(np.searchsorted(dates.values, np.datetime64(dates[last] - pd.DateOffset(years=y_)))); v0, v1 = FX[k][a_], FX[k][last]
            return round(100 * ((v1 / v0) ** (1 / y_) - 1), 1) if np.isfinite(v0) and np.isfinite(v1) else None
        OUTF["validation_to_2026_10_31"] = {"official_nse_tri": {"Momentum 30": {"3y": 9.41, "5y": 7.93}, "Low Vol 30": {"3y": 9.79, "5y": 9.13}, "Alpha 50": {"3y": 14.88, "5y": 11.56}, "Nifty 50": {"3y": 7.74, "5y": 6.70}},
                                            "rebuilt_here_no_fees_no_dividends": {short[k]: {"3y": win(k, 3), "5y": win(k, 5)} for k in keys}, "as_of": str(dates[last].date())}
        print("VALIDATION", OUTF["validation_to_2026_10_31"], flush=True)
        rot = OUTF["rotation"]; best = max(rot, key=lambda k: rot[k]["cagr"]); OUTF["best_rotation_hindsight"] = {"version": best, "of": len(rot), **rot[best]}
        os.makedirs("data", exist_ok=True); json.dump(OUTF, open("data/india_factor.json" if not DRY else "/tmp/india_factor_dry.json", "w"), indent=1, default=float); print("wrote", flush=True); return
    if MODE == "momrobust":
        # Is the India momentum basket (paper bot 13: top 500, (6m+12m)/vol, 20 stocks, monthly, Nifty-100-day filter, gold/liquid) solid or lucky?
        # 1) nearby settings, one at a time and a 3x3x3 grid  2) reshuffle on the 1st/5th/10th/15th trading day of the month
        # 3) different start years  4) 2x and 3x costs  5) placebo: 20 RANDOM stocks from the same top 500, same filter (200 runs).
        Mk = members(500); hide_r = np.where(gtr, gr, liq)
        def score(a_, b_):
            if b_ is None: return (Pf.pct_change(a_) / (vol * np.sqrt(248))).values
            return ((Pf.pct_change(a_) + Pf.pct_change(b_)) / (vol * np.sqrt(248))).values
        SCR = {"(6m+12m)/vol": score(126, 252), "(3m+6m)/vol": score(63, 126), "(3m+12m)/vol": score(63, 252), "(9m+12m)/vol": score(189, 252), "12m/vol": score(252, None), "6m/vol": score(126, None)}
        nma = {m: (n > n.rolling(m).mean()).shift(1, fill_value=False).values for m in (60, 80, 100, 120, 150, 200)}
        mstarts = [i for i in range(1, D) if dates[i].month != dates[i - 1].month]
        def rebal_days(k):
            out = []
            for m0 in mstarts:
                i = m0 + k - 1
                if i < D and dates[i].month == dates[m0].month and i >= START: out.append(i)
            return set(out)
        RB = {k: rebal_days(k) for k in (1, 5, 10, 15)}
        def mom3(sc_key="(6m+12m)/vol", N=20, ma=100, day=1, cost=0.003, rand=None):
            sc = SCR[sc_key]; ok = Mk & ~glitch & np.isfinite(sc); rebal = RB[day]; rng = np.random.default_rng(rand) if rand is not None else None
            w = {}; eq = 1.0; curve = np.ones(D); turn = 0.0; inside = True
            for t in range(START, D):
                day_r = sum(wi * Rt[t, j] for j, wi in w.items()); cash = 1 - sum(w.values())
                day_r += cash * (hide_r[t] if not inside else liq[t]); eq *= 1 + day_r
                w = {j: wi * (1 + Rt[t, j]) / (1 + day_r) for j, wi in w.items()}
                for j in [j for j in w if not traded[t, j]]: w.pop(j)
                if t in rebal:
                    inside = bool(nma[ma][t])
                    if inside:
                        cand = np.where(ok[t])[0]
                        if rng is not None: new = list(rng.choice(cand, size=min(N, len(cand)), replace=False))
                        else:
                            order = cand[np.argsort(-sc[t, cand])]; rank = {j: r for r, j in enumerate(order)}
                            kept = [j for j in w if rank.get(j, 1e9) < 1.5 * N][:N]; new = kept + [j for j in order if j not in kept][: N - len(kept)]
                        tgt = {j: 1.0 / N for j in new}
                    else: tgt = {}
                    tv_ = sum(abs(tgt.get(j, 0) - w.get(j, 0)) for j in set(tgt) | set(w)); eq *= 1 - cost * tv_; turn += tv_; w = dict(tgt)
                curve[t] = eq
            o = summ(curve); o["turnover_per_year"] = round(turn / ((D - START) / 248), 1); return o, curve
        OUTR = {"note": "India momentum basket robustness, NSE survivorship-free 2009-2026, before tax (after-tax rough).", "built": str(pd.Timestamp.today().date()), "one_at_a_time": {}, "grid": [], "start_years": {}, "costs": {}, "placebo": {}}
        base, bc = mom3(); OUTR["base"] = base; pr("BASE paper bot 13 rules", base)
        for lbl, kw in ([(f"stocks {x}", dict(N=x)) for x in (10, 15, 25, 30)] + [(f"score {k}", dict(sc_key=k)) for k in SCR if k != "(6m+12m)/vol"] +
                        [(f"filter {m}-day", dict(ma=m)) for m in (60, 80, 120, 150, 200)] + [(f"reshuffle on trading day {k} of the month", dict(day=k)) for k in (5, 10, 15)]):
            o, _ = mom3(**kw); OUTR["one_at_a_time"][lbl] = o; pr("NEAR " + lbl, o)
        for sk in ("(6m+12m)/vol", "(3m+12m)/vol", "12m/vol"):
            for Nn in (15, 20, 25):
                for m in (80, 100, 150):
                    o, _ = mom3(sc_key=sk, N=Nn, ma=m); OUTR["grid"].append({"score": sk, "stocks": Nn, "filter": m, "cagr": o["cagr"], "dd": o["dd"], "test": o["test_2019_2026"]["cagr"], "after_tax": o["after_tax_rough_cagr"]})
        g = OUTR["grid"]; cs = np.array([x["cagr"] for x in g]); ds = np.array([x["dd"] for x in g])
        OUTR["grid_summary"] = {"versions": len(g), "per_year_min": float(cs.min()), "per_year_median": float(np.median(cs)), "per_year_max": float(cs.max()), "worst_drop_median": float(np.median(ds)), "worst_drop_worst": float(ds.min()), "share_beating_nifty_by_5pts": round(float(np.mean(cs > OUTR.get("nifty", 11.9) + 5)) * 100)}
        print("GRID 27 nearby versions:", OUTR["grid_summary"], flush=True)
        cser = pd.Series(bc, index=dates); nser = pd.Series(np.cumprod(1 + nr + dv), index=dates)
        for y in (2009, 2012, 2015, 2018, 2021, 2023):
            a_ = cser[cser.index >= f"{y}-01-01"]; b_ = nser[nser.index >= f"{y}-01-01"]; yrs_ = len(a_) / 248
            OUTR["start_years"][str(y)] = {"basket": round(100 * ((a_.iloc[-1] / a_.iloc[0]) ** (1 / yrs_) - 1), 1), "nifty": round(100 * ((b_.iloc[-1] / b_.iloc[0]) ** (1 / yrs_) - 1), 1), "basket_worst": round(100 * float((a_ / a_.cummax() - 1).min()), 1)}
            print(f"START {y}: basket {OUTR['start_years'][str(y)]}", flush=True)
        for c_ in (0.006, 0.009):
            o, _ = mom3(cost=c_); OUTR["costs"][f"{c_*100:.1f}% per side"] = o; pr(f"COST {c_*100:.1f}% per side", o)
        pl = [mom3(rand=s_)[0] for s_ in range(200)]; pc = np.array([x["cagr"] for x in pl]); pd_ = np.array([x["dd"] for x in pl])
        OUTR["placebo"] = {"runs": 200, "random_median": float(np.median(pc)), "random_p95": float(np.percentile(pc, 95)), "random_max": float(pc.max()), "share_beating_base_pct": round(float(np.mean(pc >= base["cagr"])) * 100, 1), "random_median_worst_drop": float(np.median(pd_))}
        print("PLACEBO 20 random stocks (same universe, same filter):", OUTR["placebo"], flush=True)
        os.makedirs("data", exist_ok=True); json.dump(OUTR, open("data/india_momrobust.json" if not DRY else "/tmp/india_momrobust_dry.json", "w"), indent=1, default=float); print("wrote", flush=True); return
    if MODE in ("slowtax", "taxexec"):
        # Nov 22: (A) slower reshuffles / wider buffers / letting winners run, judged AFTER TAX with lot-level Indian tax (current rules applied to the whole
        # period: held < 12 months 20% + cess = 20.8%; >= 12 months 12.5% + cess = 13% above Rs 1.25 lakh a year; FIFO lots; short-term losses offset both,
        # long-term losses only long-term, carried forward; calendar years; start Rs 10 lakh). (B) score tweaks on bot 13's settings, same tax engine.
        # best = reshuffle day 1 at that close; honest = money split over days 1/6/11/16, trade next day (each part Rs 2.5 lakh, exemption split 4 ways).
        M500 = members(500); hide_r = np.where(gtr, gr, liq); nma = (n > n.rolling(100).mean()).shift(1, fill_value=False).values
        r6, r12 = Pf.pct_change(126), Pf.pct_change(252); vv = vol * np.sqrt(248)
        Ps = Pf.shift(21); r6s, r12s = Ps / Pf.shift(126) - 1, Ps / Pf.shift(252) - 1
        SCX = {"bot 13: (6m+12m)/vol": ((r6 + r12) / vv).values, "skip last month: (6-1 + 12-1)/vol": ((r6s + r12s) / vv).values,
               "more weight on 6m: (2x6m + 12m)/vol": ((2 * r6 + r12) / vv).values, "no volatility divisor: 6m+12m": (r6 + r12).values}
        mser = n.pct_change().fillna(0); mm_ = mser.rolling(252).mean(); mv_ = mser.rolling(252).var()
        beta = ((R.mul(mser, axis=0)).rolling(252, min_periods=200).mean() - R.rolling(252, min_periods=200).mean().mul(mm_, axis=0)).div(mv_, axis=0)
        resid = R - beta.mul(mser, axis=0); del beta
        rs = resid.shift(21).rolling(231, min_periods=180); SCX["residual momentum: 12-1 residual return / residual vol"] = (rs.sum() / (rs.std() * np.sqrt(231))).values; del resid, rs
        lp = np.log(Pf); nW = 90; I = pd.Series(np.arange(D, dtype=float), index=dates)
        Sy = lp.rolling(nW, min_periods=nW).sum(); Syy = (lp ** 2).rolling(nW, min_periods=nW).sum(); Sxy_g = lp.mul(I, axis=0).rolling(nW, min_periods=nW).sum()
        Sxy = Sxy_g - Sy.mul(I - nW + 1, axis=0); Sx = nW * (nW - 1) / 2; Sxx = (nW - 1) * nW * (2 * nW - 1) / 6
        den = nW * Sxx - Sx ** 2; slope = (nW * Sxy - Sx * Sy) / den; r2 = (slope ** 2 * den / (nW * Syy - Sy ** 2)).clip(0, 1)
        SCX["Clenow: 90-day trend slope x R-squared"] = ((np.exp(slope * 248) - 1) * r2).values; del Sy, Syy, Sxy_g, Sxy, slope, r2, lp
        pos = (R > 0).rolling(252, min_periods=200).mean(); neg = (R < 0).rolling(252, min_periods=200).mean()
        smooth = (pos - neg).values; del pos, neg                               # higher = smoother climb (frog-in-the-pan)
        mstarts = [i for i in range(1, D) if dates[i].month != dates[i - 1].month]
        MONTHS = {"monthly": None, "every 2 months": (1, 3, 5, 7, 9, 11), "every 3 months": (1, 4, 7, 10)}
        def plan(k, lag, months):
            out = {}
            for m0 in mstarts:
                if months and dates[m0].month not in months: continue
                s_ = m0 + k - 1
                if s_ < D and dates[s_].month == dates[m0].month and s_ >= START and s_ + lag < D: out[s_ + lag] = s_
            return out
        STR, LTR, EX, SLAB = 0.208, 0.13, 125000.0, float(os.environ.get("SLAB", "0.312"))
        def sleeve_tax(k, lag, cfg, cap):
            sc = SCX[cfg.get("score", "bot 13: (6m+12m)/vol")]; N = 20; buf = cfg.get("buf", 1.5); reset = cfg.get("reset", True); two = cfg.get("smooth", False)
            P_ = plan(k, lag, MONTHS[cfg.get("freq", "monthly")]); ex = EX * cap / 1e6
            fy = cfg.get("fy", False); h366 = cfg.get("hold366", 0); hv_lt = cfg.get("harvest_lt", False); hv_st = cfg.get("harvest_st", False); ptax = cfg.get("parktax", None)
            slab = 0.0; ltnx = 0.0; pg = 0.0; pg_t0 = None; pg_gold = None   # park leg: realised gains taxed at slab (short) or 13% without the exemption (gold held >= 12m)
            lots = {}; cash = cap; inside = True; st = lt = carry = 0.0; taxes = 0.0; pre = np.full(D, cap); post = np.full(D, cap); pre_eq = cap; tv_sum = 0.0
            def sell(j, amt, t):                       # sell amt rupees of stock j, FIFO; returns proceeds before costs
                nonlocal st, lt
                got = 0.0; L_ = lots[j]
                while amt > 1e-6 and L_:
                    d0, cost, val = L_[0]; take = min(amt, val); f = take / val
                    g = take - cost * f
                    if t - d0 >= 248: lt += g
                    else: st += g
                    if take >= val - 1e-9: L_.pop(0)
                    else: L_[0] = [d0, cost * (1 - f), val - take]
                    amt -= take; got += take
                if not L_: lots.pop(j)
                return got
            def park_realise(t):
                nonlocal pg, pg_t0, pg_gold, slab, ltnx, st
                if pg_t0 is None: return
                if pg_gold and t - pg_t0 >= 248: ltnx += pg
                elif ptax == "arb" and not pg_gold: st += pg          # arbitrage fund instead of liquid: equity-taxed (20.8% short-term)
                else: slab += pg
                pg = 0.0; pg_t0 = None
            def settle():
                nonlocal st, lt, carry, cash, taxes, slab, ltnx
                s_, l_ = st, lt
                if s_ < 0: l_ += s_; s_ = 0.0
                if carry < 0:
                    use = min(-carry, s_); s_ -= use; carry += use; use = min(-carry, max(l_, 0)); l_ -= use; carry += use
                if l_ < 0: carry += l_; l_ = 0.0
                tax = STR * s_ + LTR * max(0.0, l_ - ex) + (SLAB * max(slab, 0.0) + LTR * max(ltnx, 0.0) if ptax else 0.0); cash -= tax; taxes += tax; st = lt = 0.0; slab = ltnx = 0.0
            pre_cash_ratio = 1.0
            for t in range(START, D):
                park = hide_r[t] if not inside else liq[t]
                if ptax and not inside:
                    g_ = bool(gtr[t])
                    if pg_t0 is not None and g_ != pg_gold: park_realise(t)
                    if pg_t0 is None: pg_t0, pg_gold = t, g_
                    if ptax == "arb" and not g_: park = park - 0.005 / 248          # arbitrage fund ~0.5%/yr below liquid
                    pg += cash * park
                for j, L_ in lots.items():
                    r_ = Rt[t, j]
                    for l in L_: l[2] *= 1 + r_
                cash *= 1 + park
                for j in [j for j in lots if not traded[t, j]]:
                    cash += sell(j, sum(l[2] for l in lots[j]), t)
                if t in P_:
                    s_ = P_[t]; inside = bool(nma[s_] if lag == 0 else nma[s_ + 1])
                    if ptax and inside: park_realise(t)
                    held = {j: sum(l[2] for l in L_) for j, L_ in lots.items()}; eq = cash + sum(held.values())
                    if inside:
                        okm = M500[s_] & ~glitch[s_] & np.isfinite(sc[s_])
                        if lag: okm &= traded[t]
                        cand = np.where(okm)[0]; order = cand[np.argsort(-sc[s_, cand])]
                        if two:
                            top = order[: 2 * N]; top = top[np.argsort(-np.nan_to_num(smooth[s_, top], nan=-9))]; order = np.r_[top, order[2 * N:]]
                        rank = {j: r for r, j in enumerate(order)}
                        near = lambda j: h366 and any(203 <= t - l[0] < 248 and l[2] > l[1] for l in lots[j]) and rank.get(j, 1e9) < 4 * N   # a winner within ~45 days of long-term: wait
                        kept = [j for j in held if rank.get(j, 1e9) < buf * N or near(j)][:N]; new = kept + [j for j in order if j not in kept][: N - len(kept)]
                    else: new = []
                    tgt = {}
                    if reset or not inside: tgt = {j: eq / N for j in new}
                    else:
                        free = eq - sum(held[j] for j in new if j in held); buys = [j for j in new if j not in held]
                        tgt = {j: held[j] for j in new if j in held}
                        for j in buys: tgt[j] = max(0.0, free) / max(len(buys), 1) if len(buys) else 0.0
                        tgt = {j: min(v, eq / N * 1.0) if j not in held else v for j, v in tgt.items()}
                    traded_amt = 0.0
                    for j in list(held):
                        d_ = held[j] - tgt.get(j, 0.0)
                        if d_ > 1e-6: cash += sell(j, d_, t); traded_amt += d_
                    for j, v in tgt.items():
                        d_ = v - held.get(j, 0.0)
                        if d_ > 1e-6: lots.setdefault(j, []).append([t, d_, d_]); cash -= d_; traded_amt += d_
                    cash -= 0.003 * traded_amt; tv_sum += traded_amt / max(eq, 1)
                yend = (t + 1 >= D) or ((dates[t + 1].month == 4 and dates[t].month == 3) if fy else (dates[t + 1].year != dates[t].year))
                if yend and t + 1 < D and (hv_lt or hv_st):          # last trading day of the tax year: sell and rebuy at the same price (0.3%/side)
                    room = ex - max(lt, 0.0) if hv_lt else 0.0; need = max(st, 0.0) if hv_st else 0.0
                    for j, L_ in list(lots.items()):
                        add = []
                        for l in L_:
                            g = l[2] - l[1]; f = 0.0
                            if hv_lt and room > 1 and t - l[0] >= 248 and g > 0:
                                f = min(1.0, room / g); lt += g * f; room -= g * f
                            elif hv_st and need > 1 and t - l[0] < 248 and g < 0:
                                f = min(1.0, need / -g); st += g * f; need += g * f
                            if f > 0:                      # the rebought part is a NEW lot (new cost, holding clock restarts)
                                v = l[2] * f; cash -= 0.006 * v; add.append([t, v, v]); l[1] *= 1 - f; l[2] -= v
                        L_[:] = [l for l in L_ if l[2] > 1e-9] + add
                if ptax and yend and t + 1 >= D: park_realise(t)
                if yend: settle()
                post[t] = cash + sum(l[2] for L_ in lots.values() for l in L_)
            # sell everything at the end and settle (what you'd keep if you cashed out)
            for j in list(lots): cash += sell(j, sum(l[2] for l in lots[j]), D - 1)
            settle(); post[-1] = cash
            return post, taxes, tv_sum
        def run_tax(cfg, days, lag):
            cap = 1e6 / len(days); res = [sleeve_tax(k, lag, cfg, cap) for k in days]
            post = sum(r[0] for r in res) / 1e6; o = summ(post)
            yrs_ = (D - START) / 248
            return {"after_tax_cagr": o["cagr"], "after_tax_dd": o["dd"], "after_tax_2019_2026": o["test_2019_2026"]["cagr"],
                    "tax_paid_lakh": round(sum(r[1] for r in res) / 1e5, 1), "turnover_per_year": round(sum(r[2] for r in res) / len(days) / yrs_, 1)}
        def both(lbl, cfg):
            nonlocal STR, LTR, SLAB
            out = {}
            for nm, days, lag in (("best_day1", (1,), 0), ("honest_4days_nextday", (1, 6, 11, 16), 1)):
                a = run_tax(cfg, days, lag); s0, l0, k0 = STR, LTR, SLAB; STR, LTR, SLAB = 0.0, 0.0, 0.0; b = run_tax(cfg, days, lag); STR, LTR, SLAB = s0, l0, k0
                out[nm] = {"before_tax_cagr": b["after_tax_cagr"], "before_tax_dd": b["after_tax_dd"], **a}
                print(f"{nm[:6].upper():6s} {lbl:78s} pre {b['after_tax_cagr']:>5}/{b['after_tax_dd']:>6} | AFTER TAX {a['after_tax_cagr']:>5} (tax Rs {a['tax_paid_lakh']}L, turnover {a['turnover_per_year']}x/yr)", flush=True)
            return out
        OUTS = {"note": "India momentum (bot 13 family) with LOT-LEVEL Indian tax, current rules over 2009-2026: <12m 20.8%, >=12m 13% above Rs 1.25 lakh/yr, FIFO, losses carried; "
                        "start Rs 10 lakh; final value after selling everything and paying tax. best = day-1 reshuffle; honest = days 1/6/11/16 next-day. 0.3%/side.",
                "built": str(pd.Timestamp.today().date()), "A_reshuffle": {}, "B_score": {}}
        if MODE == "taxexec":
            # Nov 24: tax-aware EXECUTION of bot 13 (same picks). Indian tax year Apr-Mar. Park leg (gold ETF / liquid fund while the crash filter is out)
            # taxed: gold < 12 months and liquid at slab (SLAB, default 30% + cess = 31.2%), gold >= 12 months 13% (no Rs 1.25 lakh exemption).
            OUTS = {"note": "Bot 13 (top 500, (6m+12m)/vol, 20 stocks, monthly, top-30 buffer, Nifty 100-day filter -> gold/liquid) with lot-level tax. "
                            "hold366 = a winner within ~45 days of 12 months is kept (while still top 80); harvest_lt = sell+rebuy on the last trading day of March "
                            "to use the Rs 1.25 lakh long-term exemption; harvest_st = sell+rebuy short-term losers to offset that year's short-term gains; "
                            "parktax = tax the gold/liquid leg (slab " + str(SLAB) + "); arb = arbitrage fund instead of liquid (equity tax, 0.5%/yr lower return). 0.3%/side; harvest 0.3%/side x2.",
                    "built": str(pd.Timestamp.today().date()), "variants": {}}
            V = [("0 old engine (calendar year, park leg untaxed)", {}),
                 ("1 base: tax year Apr-Mar, park leg taxed at slab", dict(fy=True, parktax="slab")),
                 ("2 + hold winners to 12 months (hold366)", dict(fy=True, parktax="slab", hold366=1)),
                 ("3 + March long-term harvest (Rs 1.25 lakh)", dict(fy=True, parktax="slab", harvest_lt=True)),
                 ("4 + March short-term loss harvest", dict(fy=True, parktax="slab", harvest_st=True)),
                 ("5 all three (hold366 + both harvests)", dict(fy=True, parktax="slab", hold366=1, harvest_lt=True, harvest_st=True)),
                 ("6 all three + arbitrage fund instead of liquid", dict(fy=True, parktax="arb", hold366=1, harvest_lt=True, harvest_st=True)),
                 ("7 all three, no trims (let winners run)", dict(fy=True, parktax="slab", hold366=1, harvest_lt=True, harvest_st=True, reset=False))]
            for lbl, cfg in V: OUTS["variants"][lbl] = both(lbl, cfg)
            os.makedirs("data", exist_ok=True); json.dump(OUTS, open("data/india_taxexec.json" if not DRY else "/tmp/india_taxexec_dry.json", "w"), indent=1, default=float); print("wrote", flush=True); return
        for fr in ("monthly", "every 2 months", "every 3 months"):
            for bf in (1.5, 2.0, 2.5):
                for rs_ in (True, False):
                    lbl = f"{fr} | keep while in top {int(bf * 20)} | {'trim/top up to equal' if rs_ else 'let winners run (no trims)'}"
                    OUTS["A_reshuffle"][lbl] = both("A " + lbl, dict(freq=fr, buf=bf, reset=rs_))
        for sk in SCX:
            if sk.startswith("bot 13"): continue
            OUTS["B_score"][sk] = both("B " + sk, dict(score=sk))
        OUTS["B_score"]["smooth-trend filter: top 40 by bot-13 score, keep the 20 smoothest climbers"] = both("B smooth-trend filter", dict(smooth=True))
        os.makedirs("data", exist_ok=True); json.dump(OUTS, open("data/india_slowtax.json" if not DRY else "/tmp/india_slowtax_dry.json", "w"), indent=1, default=float); print("wrote", flush=True); return
    if MODE == "ideas3":
        # Nov 22 research shortlist #1-3 on paper bot 13 (momentum: top 500, (6m+12m)/vol, 20 stocks, monthly, 1.5N buffer, Nifty 100-day filter):
        #  1) low-volatility basket beside momentum  2) junk/tradability exclusions  3) per-slot absolute check (12m > liquid AND above own 200-day avg).
        # Each version: "best" = reshuffle day 1, trade at that close (paper bot 13 = 32.6%) and "honest" = money split over days 1/6/11/16, trade next day (26.7%).
        # Not testable with price data: ASM/GSM lists, promoter pledge, insider selling (no history) -> proxies only (circuit-lock share, low turnover, big down days).
        M500, M200 = members(500), members(200); hide_r = np.where(gtr, gr, liq)
        scm = ((Pf.pct_change(126) + Pf.pct_change(252)) / (vol * np.sqrt(248))).values
        v252 = R.rolling(252, min_periods=200).std().values; sclv = -v252
        r12 = Pf.pct_change(252).values
        lock120 = ((H == L) & C.notna()).rolling(120, min_periods=40).mean().values
        drop10 = (R <= -0.10).rolling(63, min_periods=1).max().fillna(0).astype(bool).values
        vspike = (V > 3 * V.rolling(50, min_periods=20).median())
        drop10v = ((R <= -0.10) & vspike).rolling(63, min_periods=1).max().fillna(0).astype(bool).values
        tvv = tv.values
        nma = (n > n.rolling(100).mean()).shift(1, fill_value=False).values
        mstarts = [i for i in range(1, D) if dates[i].month != dates[i - 1].month]
        def excl_fn(kind):
            if kind is None: return None
            def f(s_, M):
                x = np.zeros(len(tick), bool)
                if "circ60" in kind: x |= np.nan_to_num(locked[s_], nan=0) >= 0.2
                if "circ120" in kind: x |= np.nan_to_num(lock120[s_], nan=0) >= 0.1
                if "lowturn" in kind:
                    th = np.nanpercentile(np.where(M[s_], tvv[s_], np.nan), 10); x |= ~(tvv[s_] >= th)
                if "drop10v" in kind: x |= drop10v[s_]
                elif "drop10" in kind: x |= drop10[s_]
                return x
            return f
        def plan(k, lag, months):
            out = {}
            for m0 in mstarts:
                if months and dates[m0].month not in months: continue
                s_ = m0 + k - 1
                if s_ < D and dates[s_].month == dates[m0].month and s_ >= START and s_ + lag < D: out[s_ + lag] = s_
            return out
        def sleeve(k, lag, cfg):
            sc = cfg["score"]; M = cfg["M"]; N = cfg["N"]; buf = cfg.get("buf", 1.5); filt = cfg.get("filt", True); slot = cfg.get("slot"); ex = excl_fn(cfg.get("excl"))
            P_ = plan(k, lag, {"M": None, "Q": (1, 4, 7, 10), "S": (1, 7)}[cfg.get("freq", "M")])
            w = {}; eq = 1.0; curve = np.ones(D); turn = 0.0; inside = True; slots_cash = 0.0; nslot = 0; nreb = 0
            for t in range(START, D):
                day_r = sum(wi * Rt[t, j] for j, wi in w.items()); cash = 1 - sum(w.values())
                park = hide_r[t] if (not inside or slot == "cash") else liq[t]
                day_r += cash * park; eq *= 1 + day_r
                w = {j: wi * (1 + Rt[t, j]) / (1 + day_r) for j, wi in w.items()}
                for j in [j for j in w if not traded[t, j]]: w.pop(j)
                if t in P_:
                    s_ = P_[t]; inside = bool(nma[s_] if lag == 0 else nma[s_ + 1]) if filt else True
                    if inside:
                        okm = M[s_] & ~glitch[s_] & np.isfinite(sc[s_])
                        if lag: okm &= traded[t]
                        if ex is not None: okm &= ~ex(s_, M)
                        qual = (np.nan_to_num(r12[s_], nan=-9) > 0.06) & above[s_]
                        if slot == "fill": okm &= qual
                        cand = np.where(okm)[0]; order = cand[np.argsort(-sc[s_, cand])]; rank = {j: r for r, j in enumerate(order)}
                        kept = [j for j in w if rank.get(j, 1e9) < buf * N][:N]; new = kept + [j for j in order if j not in kept][: N - len(kept)]
                        if slot == "cash": nslot += len(new); new = [j for j in new if qual[j]]; slots_cash += 1
                        tgt = {j: 1.0 / N for j in new}; nreb += 1
                    else: tgt = {}
                    tv_ = sum(abs(tgt.get(j, 0) - w.get(j, 0)) for j in set(tgt) | set(w)); eq *= 1 - 0.003 * tv_; turn += tv_; w = dict(tgt)
                curve[t] = eq
            return curve, turn, (nreb, nslot)
        def runv(cfg, days, lag):
            cs = [sleeve(k, lag, cfg) for k in days]; curve = sum(c for c, _, _ in cs) / len(days)
            o = summ(curve); o["turnover_per_year"] = round(sum(t_ for _, t_, _ in cs) / len(days) / ((D - START) / 248), 1); return o, curve
        def both(lbl, cfg):
            b_, cb = runv(cfg, (1,), 0); h_, ch = runv(cfg, (1, 6, 11, 16), 1)
            pr("BEST   " + lbl, b_); pr("HONEST " + lbl, h_); return {"best_day1": b_, "honest_4days_nextday": h_}, ch
        OUT3 = {"note": "Shortlist #1-3 on India momentum (paper bot 13). best = day-1 reshuffle at that close; honest = split over days 1/6/11/16, trade next day. "
                        "Survivorship-free NSE 2009-2026, 0.3%/side, before tax (after-tax rough = 20.8% on each year's net gain).", "built": str(pd.Timestamp.today().date()),
                "base": {}, "junk_filters": {}, "slot_check": {}, "low_vol": {}, "blends": {}}
        BASE = dict(score=scm, M=M500, N=20)
        OUT3["base"]["paper bot 13 rules"], c_base = both("BASE momentum (paper bot 13)", BASE)
        for lbl, ex in (("circuit-locked 20%+ of last 60 days", "circ60"), ("circuit-locked 10%+ of last 120 days", "circ120"), ("bottom 10% turnover of the universe", "lowturn"),
                        ("any -10% day in last 3 months", "drop10"), ("any -10% day on 3x volume in last 3 months (results-crash proxy)", "drop10v"),
                        ("all three: circuit60 + low turnover + -10% on 3x volume", "circ60+lowturn+drop10v")):
            OUT3["junk_filters"][lbl], _ = both("JUNK " + lbl, dict(BASE, excl=ex))
        for lbl, cfg in (("skip stocks failing the check, fill with the next qualifying (Nifty filter kept)", dict(BASE, slot="fill")),
                         ("failing slots go to gold/liquid (Nifty filter kept)", dict(BASE, slot="cash")),
                         ("failing slots go to gold/liquid, NO Nifty filter", dict(BASE, slot="cash", filt=False)),
                         ("skip failing stocks, fill next qualifying, NO Nifty filter", dict(BASE, slot="fill", filt=False))):
            OUT3["slot_check"][lbl], _ = both("SLOT " + lbl, cfg)
        lv_curves = {}
        for uni, M_ in (("top 200", M200), ("top 500", M500)):
            for N_ in (30, 50):
                for fr, frl in (("S", "every 6 months (Jan/Jul)"), ("M", "monthly, 1.5N buffer")):
                    lbl = f"{uni}, lowest 1-yr volatility, {N_} stocks, {frl}"
                    OUT3["low_vol"][lbl], lv_curves[lbl] = both("LOWVOL " + lbl, dict(score=sclv, M=M_, N=N_, freq=fr, filt=False))
        bestlv = max(OUT3["low_vol"], key=lambda k: OUT3["low_vol"][k]["honest_4days_nextday"]["cagr"])
        OUT3["low_vol"][bestlv + " + Nifty crash filter"], _ = both("LOWVOL+FILTER " + bestlv, dict(score=sclv, M=M500 if "500" in bestlv else M200, N=int(bestlv.split(", ")[2].split()[0]),
                                                                                       freq="S" if "6 months" in bestlv else "M", filt=True))
        # blends of the honest curves, rebalanced monthly back to the split
        def blend(c1, c2, w1):
            r1 = np.r_[0, c1[1:] / c1[:-1] - 1]; r2 = np.r_[0, c2[1:] / c2[:-1] - 1]; a, b = w1, 1 - w1; eq = 1.0; out = np.ones(D)
            for t in range(START, D):
                if t in mstarts: tot = a + b; a, b = w1 * tot, (1 - w1) * tot
                a *= 1 + r1[t]; b *= 1 + r2[t]; out[t] = a + b
            return out
        mo = lambda c: pd.Series(c[START:], index=dates[START:]).resample("ME").last().pct_change().dropna()
        OUT3["blends"]["monthly_correlation_momentum_vs_best_lowvol"] = round(float(mo(c_base).corr(mo(lv_curves[bestlv]))), 2)
        for w1 in (0.7, 0.5, 0.3):
            o = summ(blend(c_base, lv_curves[bestlv], w1)); kk = f"{int(w1 * 100)}% momentum + {100 - int(w1 * 100)}% low vol ({bestlv}), honest"; OUT3["blends"][kk] = o; pr("BLEND " + kk, o)
        os.makedirs("data", exist_ok=True); json.dump(OUT3, open("data/india_ideas3.json" if not DRY else "/tmp/india_ideas3_dry.json", "w"), indent=1, default=float); print("wrote", flush=True); return
    if MODE == "momsplit":
        # Reshuffle-day luck check for paper bot 13 (Nov 21): 1) every reshuffle day 1..18 of the month, same day and 1 day late
        # (friends see the 7:15 pm IST alert and trade next day)  2) split money into 2/3/4 parts, each reshuffled on a different day.
        Mk = members(500); hide_r = np.where(gtr, gr, liq)
        sc = ((Pf.pct_change(126) + Pf.pct_change(252)) / (vol * np.sqrt(248))).values; ok = Mk & ~glitch & np.isfinite(sc)
        nma = {m: (n > n.rolling(m).mean()).shift(1, fill_value=False).values for m in (100, 200)}
        mstarts = [i for i in range(1, D) if dates[i].month != dates[i - 1].month]
        def plan(k, lag):
            out = {}
            for m0 in mstarts:
                s_ = m0 + k - 1
                if s_ < D and dates[s_].month == dates[m0].month and s_ >= START and s_ + lag < D: out[s_ + lag] = s_
            return out
        def sleeve(k, lag, ma, N=20, cost=0.003):
            P = plan(k, lag); w = {}; eq = 1.0; curve = np.ones(D); turn = 0.0; inside = True
            for t in range(START, D):
                day_r = sum(wi * Rt[t, j] for j, wi in w.items()); cash = 1 - sum(w.values())
                day_r += cash * (hide_r[t] if not inside else liq[t]); eq *= 1 + day_r
                w = {j: wi * (1 + Rt[t, j]) / (1 + day_r) for j, wi in w.items()}
                for j in [j for j in w if not traded[t, j]]: w.pop(j)
                if t in P:
                    s_ = P[t]; inside = bool(nma[ma][s_] if lag == 0 else nma[ma][s_ + 1])   # filter as of the signal day's close
                    if inside:
                        cand = np.where(ok[s_] & (traded[t] if lag else True))[0]; order = cand[np.argsort(-sc[s_, cand])]; rank = {j: r for r, j in enumerate(order)}
                        kept = [j for j in w if rank.get(j, 1e9) < 1.5 * N][:N]; new = kept + [j for j in order if j not in kept][: N - len(kept)]
                        tgt = {j: 1.0 / N for j in new}
                    else: tgt = {}
                    tv_ = sum(abs(tgt.get(j, 0) - w.get(j, 0)) for j in set(tgt) | set(w)); eq *= 1 - cost * tv_; turn += tv_; w = dict(tgt)
                curve[t] = eq
            return curve, turn
        def runs(days, lag=0, ma=100):
            cs = [sleeve(k, lag, ma) for k in days]; curve = sum(c for c, _ in cs) / len(days)   # each part starts with 1/K of the money
            o = summ(curve); o.update(days=list(days), lag=lag, filter=ma, turnover_per_year=round(sum(t_ for _, t_ in cs) / len(days) / ((D - START) / 248), 1)); return o
        OUTS = {"note": "India momentum: reshuffle-day luck and split reshuffles. NSE survivorship-free 2009-2026, before tax (after-tax rough). lag=1: trade the day after the signal.",
                "built": str(pd.Timestamp.today().date()), "single_day": {}, "split": {}}
        DAYS = range(1, 19) if not DRY else (1, 5, 10)
        for lag in (0, 1):
            rows = {}
            for k in DAYS:
                o = runs([k], lag); rows[str(k)] = o; pr(f"DAY {k:2d} lag {lag}", o)
            c_ = np.array([r["cagr"] for r in rows.values()]); d_ = np.array([r["dd"] for r in rows.values()])
            OUTS["single_day"][f"lag{lag}"] = {"rows": rows, "summary": {"per_year_min": float(c_.min()), "per_year_median": float(np.median(c_)), "per_year_mean": float(c_.mean()),
                                                "per_year_max": float(c_.max()), "worst_drop_median": float(np.median(d_)), "worst_drop_worst": float(d_.min())}}
            print(f"SUMMARY lag {lag}:", OUTS["single_day"][f"lag{lag}"]["summary"], flush=True)
        for lbl, days in (("1 part, day 1", (1,)), ("2 parts, days 1 and 11", (1, 11)), ("3 parts, days 1, 8, 15", (1, 8, 15)), ("4 parts, days 1, 6, 11, 16", (1, 6, 11, 16))):
            for lag in (0, 1):
                for ma in ((100, 200) if len(days) > 1 else (100,)):
                    o = runs(days, lag, ma); key = f"{lbl} | lag {lag} | filter {ma}"; OUTS["split"][key] = o; pr("SPLIT " + key, o)
        os.makedirs("data", exist_ok=True); json.dump(OUTS, open("data/india_momsplit.json" if not DRY else "/tmp/india_momsplit_dry.json", "w"), indent=1, default=float); print("wrote", flush=True); return
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
