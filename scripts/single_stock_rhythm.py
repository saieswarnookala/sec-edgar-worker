"""Single-stock "rhythm" test (default ORCL): does one stock have an intraday / daily pattern you can trade?
Honest design: every pattern family and setting is fixed in advance (about 600 versions). We look ONLY at 2016-2022
(train) to pick the best ones, then check those exact rules on 2023-2026 (test), which they never saw.
Data: Alpaca SIP 1-minute bars, regular hours (9:30-16:00 ET). Entries happen at the OPEN of the bar after a signal
(no peeking). Stops fill at the stop or worse; targets need the price to trade through. Flat by the close unless the
family says "hold N days". Cost 0.02% per side (Robinhood has no commission; this is spread/slippage), stress test 0.05%.
Not financial advice."""
import os, json, time, urllib.request, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

SYM = os.environ.get("SYMBOL", "ORCL").upper()
OUT = f"data/rhythm_{SYM.lower()}.json"
H = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
TRAIN_END, TEST_START = "2022-12-31", "2023-01-01"
COST, STRESS = 0.0002, 0.0005
NY = ZoneInfo("America/New_York")

def get(url):
    for i in range(6):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120))
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404, 422): raise
            time.sleep(min(60, 5 * (i + 1)))
        except Exception: time.sleep(3 * (i + 1))
    raise RuntimeError("Alpaca unreachable")

# ---------- data: minute bars -> per-day 390-minute arrays ----------
p = {"timeframe": "1Min", "start": "2016-01-01", "end": datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z"), "adjustment": "split", "feed": "sip", "limit": "10000"}
rows = {}
while True:
    js = get(f"https://data.alpaca.markets/v2/stocks/{SYM}/bars?" + urllib.parse.urlencode(p))
    for b in js.get("bars") or []:
        t = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
        m = t.hour * 60 + t.minute - 570
        if 0 <= m < 390: rows.setdefault(t.strftime("%Y-%m-%d"), {})[m] = (b["o"], b["h"], b["l"], b["c"], b["v"])
    if not js.get("next_page_token"): break
    p["page_token"] = js["next_page_token"]
    if len(rows) % 250 < 2: print("days so far", len(rows), flush=True)
dates = sorted(d for d, v in rows.items() if len(v) >= 180)
D = len(dates); print(SYM, "days", D, dates[0], dates[-1], flush=True)
O, Hh, L, C, V = (np.full((D, 390), np.nan) for _ in range(5)); last = np.zeros(D, int)
for i, d in enumerate(dates):
    for m, (o, h, l, c, v) in rows[d].items(): O[i, m], Hh[i, m], L[i, m], C[i, m], V[i, m] = o, h, l, c, v
    last[i] = max(rows[d]); first = min(rows[d])
    for m in range(first): O[i, m] = Hh[i, m] = L[i, m] = C[i, m] = O[i, first]; V[i, m] = 0
    for m in range(first, last[i] + 1):            # empty minute = no trade: carry the last close
        if np.isnan(C[i, m]): O[i, m] = Hh[i, m] = L[i, m] = C[i, m] = C[i, m - 1]; V[i, m] = 0
    for m in range(last[i] + 1, 390): O[i, m] = Hh[i, m] = L[i, m] = C[i, m] = C[i, last[i]]; V[i, m] = 0
del rows
CL = C[np.arange(D), last]                          # daily close
PREV = np.r_[np.nan, CL[:-1]]
VWAP = np.cumsum((Hh + L + C) / 3 * V, 1) / np.maximum(np.cumsum(V, 1), 1)
train = np.array([d <= TRAIN_END for d in dates]); test = ~train
DOW = np.array([datetime.strptime(d, "%Y-%m-%d").weekday() for d in dates])

# ---------- engine ----------
def sim(day, e, d, stop, tgt, end):
    """Enter at the open of bar e on `day`, direction d (+1 long / -1 short). stop/tgt absolute prices (nan = none).
    Exit at the first stop/target touch (stop wins ties, fills at the stop or a worse open), else the close of bar `end`."""
    end = min(end, last[day]); px = O[day, e]
    if e > end or not px > 0: return None
    lo, hi, op = L[day, e:end + 1], Hh[day, e:end + 1], O[day, e:end + 1]
    if d > 0: s = np.flatnonzero(lo <= stop) if stop == stop else np.array([], int); t = np.flatnonzero(hi > tgt) if tgt == tgt else np.array([], int)
    else: s = np.flatnonzero(hi >= stop) if stop == stop else np.array([], int); t = np.flatnonzero(lo < tgt) if tgt == tgt else np.array([], int)
    si, ti = (s[0] if s.size else 10**9), (t[0] if t.size else 10**9)
    if si <= ti and si < 10**9: out = min(stop, op[si]) if d > 0 else max(stop, op[si])
    elif ti < 10**9: out = max(tgt, op[ti]) if d > 0 else min(tgt, op[ti])
    else: out = C[day, end]
    return d * (out / px - 1)

def first_true(cond, lo, hi):
    """index of first True in each row within [lo, hi], -1 if none"""
    c = cond.copy(); c[:, :lo] = False; c[:, hi + 1:] = False
    idx = c.argmax(1); idx[~c.any(1)] = -1; return idx

CONFIGS = []   # (family, name, list of (day_index, gross_return))
HOLD = {}     # rule name -> hold in days, for rules compared against "buy on a random day, same hold"
def add(fam, name, trades, hold=None):
    CONFIGS.append((fam, name, trades))
    if hold: HOLD[name] = hold

# A) time-of-day drift: open of bar a -> close of bar b, every day (the pure "rhythm")
starts = [0, 15, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360]
for a in starts:
    for b in sorted({a + 14, a + 29, a + 59, a + 119, 389}):
        if b > 389 or b <= a: continue
        r = C[:, b] / O[:, a] - 1
        for d in (1, -1): add("A time-of-day", f"{'long' if d > 0 else 'short'} {a}-{b + 1} min after open", [(i, d * r[i]) for i in range(D)])
# A2) weekday: open->close and overnight (prev close -> open) by day of week
oc, on = CL / O[:, 0] - 1, O[:, 0] / PREV - 1
for wd, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
    for d in (1, -1):
        add("A weekday", f"{'long' if d > 0 else 'short'} open->close on {nm}", [(i, d * oc[i]) for i in range(D) if DOW[i] == wd])
        add("A weekday", f"{'long' if d > 0 else 'short'} overnight into {nm}", [(i, d * on[i]) for i in range(1, D) if DOW[i] == wd])

# B) opening-range breakout
for N in (5, 15, 30, 60):
    rh, rl = Hh[:, :N].max(1), L[:, :N].min(1); rng = rh - rl
    up, dn = first_true(C > rh[:, None], N, 329), first_true(C < rl[:, None], N, 329)
    for stopk in ("range", "half"):
        for tk in (0, 1, 2):
            for d, sig in ((1, up), (-1, dn)):
                tr = []
                for i in np.flatnonzero(sig >= 0):
                    e = sig[i] + 1; px = O[i, e]
                    stop = (rl[i] if d > 0 else rh[i]) if stopk == "range" else (rh[i] + rl[i]) / 2
                    tgt = px + d * tk * rng[i] if tk else np.nan
                    r = sim(i, e, d, stop, tgt, 389)
                    if r is not None: tr.append((i, r))
                add("B opening-range breakout", f"{N}-min range, {'long above' if d > 0 else 'short below'}, stop {stopk}, target {f'{tk}x range' if tk else 'close'}", tr)

# C) move from the open: fade it or follow it
for x in (0.005, 0.01, 0.015, 0.02, 0.03):
    dn, up = first_true(C <= O[:, :1] * (1 - x), 5, 329), first_true(C >= O[:, :1] * (1 + x), 5, 329)
    for tgt_k in ("0.5%", "1%", "2%", "open"):
        for stop_k in (0.01, 0.02, None):
            for move, sig in (("drop", dn), ("jump", up)):
                for act in ("fade", "follow"):
                    d = (1 if move == "drop" else -1) * (1 if act == "fade" else -1)
                    if tgt_k == "open" and act == "follow": continue
                    tr = []
                    for i in np.flatnonzero(sig >= 0):
                        e = sig[i] + 1; px = O[i, e]
                        tgt = O[i, 0] if tgt_k == "open" else px * (1 + d * float(tgt_k[:-1]) / 100)
                        stop = px * (1 - d * stop_k) if stop_k else np.nan
                        r = sim(i, e, d, stop, tgt, 389)
                        if r is not None: tr.append((i, r))
                    add("C move from open", f"{act} a {x * 100:g}% {move} from the open, target {tgt_k}, stop {f'{stop_k * 100:g}%' if stop_k else 'close'}", tr)

# D) opening gap: follow or fade
gap = O[:, 0] / PREV - 1
for g in (0.005, 0.01, 0.02, 0.03):
    for side in ("up", "down"):
        hit = (gap >= g) if side == "up" else (gap <= -g)
        for act in ("follow", "fade"):
            d = (1 if side == "up" else -1) * (1 if act == "follow" else -1)
            for end in (29, 59, 389):
                r = C[:, end] / O[:, 0] - 1
                add("D opening gap", f"{act} a {g * 100:g}%+ gap {side}, exit {'close' if end == 389 else f'{end + 1} min'}", [(i, d * r[i]) for i in np.flatnonzero(hit)])

# E) after a big day: buy/short next open, hold to the close of day 1, 2 or 5
dret = CL / PREV - 1
for x in (0.01, 0.02, 0.03, 0.04):
    for side in ("down", "up"):
        hit = (dret <= -x) if side == "down" else (dret >= x)
        for act in ("bounce", "continue"):
            d = (1 if side == "down" else -1) * (1 if act == "bounce" else -1)
            for k in (1, 2, 5):
                tr = [(i + 1, d * (CL[i + k] / O[i + 1, 0] - 1)) for i in np.flatnonzero(hit) if i + k < D]
                add("E after a big day", f"bet on a {act} after a {x * 100:g}%+ {side} day, hold {k} day(s)", tr)

# F) stretch away from VWAP: snap back to VWAP
for x in (0.003, 0.005, 0.01, 0.015):
    lo_sig, hi_sig = first_true(C <= VWAP * (1 - x), 15, 329), first_true(C >= VWAP * (1 + x), 15, 329)
    for stop_k in (0.01, 0.02, None):
        for d, sig in ((1, lo_sig), (-1, hi_sig)):
            tr = []
            for i in np.flatnonzero(sig >= 0):
                e = sig[i] + 1; px = O[i, e]
                r = sim(i, e, d, px * (1 - d * stop_k) if stop_k else np.nan, VWAP[i, sig[i]], 389)
                if r is not None: tr.append((i, r))
            add("F VWAP snap-back", f"{'buy' if d > 0 else 'short'} {x * 100:g}% {'below' if d > 0 else 'above'} VWAP, target VWAP, stop {f'{stop_k * 100:g}%' if stop_k else 'close'}", tr)
# ---- research-based families (Nov 14) ----
# G) Same half-hour persistence (Heston, Korajczyk & Sadka 2010, J. Finance): a stock's return in a half-hour slot
#    predicts its return in the SAME slot on later days, for up to ~40 days. Per-stock time-series version:
#    trade each 30-min slot in the direction of that slot's average over the last k days.
blocks13 = list(range(0, 390, 30))
BR = np.stack([C[:, min(b + 29, 389)] / O[:, b] - 1 for b in blocks13], 1)
csum = np.vstack([np.zeros(13), np.cumsum(BR, 0)])
full = last >= 389
for k in (1, 5, 10, 20, 40):
    avgk = np.full_like(BR, np.nan); avgk[k:] = (csum[k:-1] - csum[:-k - 1]) / k
    for mode in ("both", "long"):
        for j in list(range(13)) + ["all"]:
            cols = range(13) if j == "all" else [j]; tr = []
            for i in range(k, D):
                if not full[i]: continue
                for c in cols:
                    a = avgk[i, c]
                    if a != a or a == 0 or (mode == "long" and a < 0): continue
                    tr.append((i, np.sign(a) * BR[i, c]))
            slot = "every half-hour" if j == "all" else f"{(570 + blocks13[j]) // 60}:{(570 + blocks13[j]) % 60:02d} half-hour"
            add("G same half-hour (HKS 2010)", f"{'long/short' if mode == 'both' else 'long only'} {slot} by its last {k}-day average", tr)
# H) Intraday momentum (Gao, Han, Li & Zhou 2018 JFE; Baltussen et al. 2021 JFE) and end-of-day reversal (CXO/1993-2019):
#    an early-day move predicts the LAST half-hour. Enter at 3:30 pm open, exit at the close.
last30 = CL / O[:, 360] - 1
preds = {"first 30 min incl. overnight": C[:, 29] / PREV - 1, "first 30 min (from open)": C[:, 29] / O[:, 0] - 1,
         "day so far (prev close to 3:30)": C[:, 359] / PREV - 1, "overnight gap": O[:, 0] / PREV - 1}
for pn, pv in preds.items():
    for act in ("follow", "fade"):
        for th in (0, 0.005, 0.01, 0.02):
            for lo in (False, True):
                tr = []
                for i in range(1, D):
                    if not full[i] or not (abs(pv[i]) >= th) or pv[i] == 0: continue
                    d = np.sign(pv[i]) * (1 if act == "follow" else -1)
                    if lo and d < 0: continue
                    tr.append((i, d * last30[i]))
                add("H last half-hour", f"{act} the {pn} (move >= {th * 100:g}%) in the last 30 min{', long only' if lo else ''}", tr)
# J) Yesterday's last half-hour predicts today's last half-hour (Zhang & Hua 2024, Risks)
for act in ("follow", "fade"):
    for th in (0, 0.003, 0.006):
        for lo in (False, True):
            tr = []
            for i in range(1, D):
                if not (full[i] and full[i - 1]) or not abs(last30[i - 1]) >= th or last30[i - 1] == 0: continue
                d = np.sign(last30[i - 1]) * (1 if act == "follow" else -1)
                if lo and d < 0: continue
                tr.append((i, d * last30[i]))
            add("J yesterday's last 30 min", f"{act} yesterday's last-30-min move (>= {th * 100:g}%) today in the last 30 min{', long only' if lo else ''}", tr)
# K) Short swings, max 3 days (Sai's limit). Buy at the open (or right after an intraday trigger), sell at the close
#    of day 1, 2 or 3. Each is also compared with "buy at the open on ANY day, same hold" so a rising stock's drift
#    doesn't look like skill (excess_bps).
for k in (1, 2, 3):
    for g in (0.01, 0.02, 0.03, 0.04):
        for side in ("down", "up"):
            hit = (gap <= -g) if side == "down" else (gap >= g)
            for act in ("bounce", "follow"):
                d = (1 if side == "down" else -1) * (1 if act == "bounce" else -1)
                if d < 0: continue   # long only: Robinhood cash-style account, no shorting
                add("K swing <= 3 days", f"buy at the open after a {g * 100:g}%+ gap {side} ({act}), sell at the close of day {k}",
                    [(i, CL[i + k - 1] / O[i, 0] - 1) for i in np.flatnonzero(hit) if i + k - 1 < D], hold=k)
    for x in (0.01, 0.02, 0.03, 0.05):
        for side in ("down", "up"):
            hit = (dret <= -x) if side == "down" else (dret >= x)
            add("K swing <= 3 days", f"buy the next open after a {x * 100:g}%+ {side} day, sell at the close of day {k}",
                [(i + 1, CL[i + k] / O[i + 1, 0] - 1) for i in np.flatnonzero(hit) if i + k < D], hold=k)
    for x in (0.02, 0.03, 0.05):
        sig = first_true(C <= O[:, :1] * (1 - x), 5, 329)
        tr = [(i, CL[i + k - 1] / O[i, sig[i] + 1] - 1) for i in np.flatnonzero(sig >= 0) if i + k - 1 < D]
        add("K swing <= 3 days", f"buy when it falls {x * 100:g}% below the open during the day, sell at the close of day {k}", tr, hold=k)
    lose = (CL / O[:, 0] - 1)
    for x in (0.02, 0.03, 0.05):
        add("K swing <= 3 days", f"buy at the close after a {x * 100:g}%+ drop from open to close, sell at the close {k} day(s) later",
            [(i, CL[i + k] / CL[i] - 1) for i in np.flatnonzero(lose <= -x) if i + k < D], hold=None)
# baseline: buy at the open on any day, sell at the close of day k
BASE = {k: np.array([CL[i + k - 1] / O[i, 0] - 1 if i + k - 1 < D else np.nan for i in range(D)]) for k in (1, 2, 3)}
# L/M/N) Candlestick patterns on this stock alone (Nov 14): daily candles (buy the next open, hold 1-3 days, long only,
#    compared with buying on a random day), and 30-min / 15-min candles inside the day (enter the next bar's open,
#    exit after 1 bar, 2 bars or at the close; bullish patterns long, bearish patterns short).
def candle_pats(o, h, l, c, po, pc, ph, pl):
    rg = h - l; body = np.abs(c - o); us = h - np.maximum(o, c); ls = np.minimum(o, c) - l
    with np.errstate(all="ignore"): clv = (c - l) / rg
    v = rg > 0
    return {"hammer (long lower tail)": (v & (ls >= 2 * body) & (us <= 0.3 * rg), 1),
            "shooting star (long upper tail)": (v & (us >= 2 * body) & (ls <= 0.3 * rg), -1),
            "bullish engulfing": (v & (c > o) & (pc < po) & (o <= pc) & (c >= po), 1),
            "bearish engulfing": (v & (c < o) & (pc > po) & (o >= pc) & (c <= po), -1),
            "doji": (v & (body <= 0.1 * rg), 1),
            "strong close (top 20% of bar)": (v & (clv >= 0.8), 1),
            "weak close (bottom 20% of bar)": (v & (clv <= 0.2), -1),
            "inside bar": (v & (h < ph) & (l > pl), 1)}
Hd = np.array([Hh[i, :last[i] + 1].max() for i in range(D)]); Ld = np.array([L[i, :last[i] + 1].min() for i in range(D)]); Od = O[:, 0]
sh1 = lambda x: np.r_[np.nan, x[:-1]]
for pn, (m, sgn) in candle_pats(Od, Hd, Ld, CL, sh1(Od), sh1(CL), sh1(Hd), sh1(Ld)).items():
    for k in (1, 2, 3):
        add("L candles (daily)", f"buy the next open after a daily {pn}, sell at the close of day {k}" + (" [pattern says down]" if sgn < 0 else ""),
            [(i + 1, CL[i + k] / O[i + 1, 0] - 1) for i in np.flatnonzero(m) if i + k < D], hold=k)
for bm, fam, exits in ((30, "M candles (30-min)", (("1 bar", 1), ("2 bars", 2), ("close", None))),
                       (15, "N candles (15-min)", (("1 bar", 1), ("2 bars", 2), ("close", None))),
                       (5, "O candles (5-min)", (("1 bar", 1), ("3 bars", 3), ("close", None))),
                       (1, "P candles (1-min)", (("1 bar", 1), ("5 bars", 5), ("close", None)))):
    nb = 390 // bm
    bo = O[:, 0::bm][:, :nb]; bc = C[:, bm - 1::bm][:, :nb]
    bh = Hh.reshape(D, nb, bm).max(2); bl = L.reshape(D, nb, bm).min(2)
    prev = lambda x: np.hstack([np.full((D, 1), np.nan), x[:, :-1]])
    for pn, (m, sgn) in candle_pats(bo, bh, bl, bc, prev(bo), prev(bc), prev(bh), prev(bl)).items():
        m = m.copy(); m[:, 0] = False; m[:, nb - 1] = False          # need a previous bar and a next bar
        I, J = np.nonzero(m & full[:, None])
        for ex, kb in exits:
            xb = np.full(len(J), nb - 1) if kb is None else J + kb
            ok_ = xb < nb
            Ii, Jj, Xb = I[ok_], J[ok_], xb[ok_]
            r = sgn * (bc[Ii, Xb] / bo[Ii, Jj + 1] - 1)
            add(fam, f"{'buy' if sgn > 0 else 'short'} the next {bm}-min bar after a {pn}, exit after {ex}", list(zip(Ii.tolist(), r.tolist())))
print("versions tested", len(CONFIGS), flush=True)

# ---------- score ----------
def stats(tr, mask, cost=COST):
    r = np.array([x for i, x in tr if mask[i]]) - 2 * cost
    if r.size < 2: return {"trades": int(r.size)}
    yrs = mask.sum() / 252
    return {"trades": int(r.size), "avg_bps": round(float(r.mean()) * 1e4, 1), "win_pct": round(float((r > 0).mean()) * 100, 1),
            "t": round(float(r.mean() / (r.std(ddof=1) or 1e-9) * np.sqrt(r.size)), 2),
            "per_year_pct": round(float(r.sum() / yrs) * 100, 1), "worst_bps": round(float(r.min()) * 1e4, 0)}
res = []
for fam, name, tr in CONFIGS:
    row = {"family": fam, "rule": name, "train": stats(tr, train), "test": stats(tr, test), "test_stress": stats(tr, test, STRESS)}
    if name in HOLD:
        for per, m in (("train", train), ("test", test)):
            b = np.nanmean(BASE[HOLD[name]][m]) - 2 * COST
            row[per]["random_day_bps"] = round(float(b) * 1e4, 1)
            if "avg_bps" in row[per]: row[per]["excess_bps"] = round(row[per]["avg_bps"] - b * 1e4, 1)
    res.append(row)
ok = [r for r in res if r["train"].get("trades", 0) >= 40 and r["test"].get("trades", 0) >= 15]
ok.sort(key=lambda r: -r["train"]["t"])
top = ok[:15]
tt, te = np.array([r["train"]["avg_bps"] for r in ok]), np.array([r["test"]["avg_bps"] for r in ok])
rank = lambda a: a.argsort().argsort()
summary = {
    "symbol": SYM, "days": D, "first": dates[0], "last": dates[-1], "train": f"{dates[0]} to {TRAIN_END}", "test": f"{TEST_START} to {dates[-1]}",
    "versions": len(res), "versions_scored": len(ok), "cost_per_side_pct": COST * 100,
    "train_t_over_2": int(sum(r["train"]["t"] > 2 for r in ok)), "expected_by_luck_t_over_2": round(len(ok) * 0.023, 1),
    "test_t_over_2": int(sum(r["test"]["t"] > 2 for r in ok)),
    "top15_train_still_positive_in_test": int(sum(r["test"]["avg_bps"] > 0 for r in top)),
    "top15_train_t_over_2_in_test": int(sum(r["test"]["t"] > 2 for r in top)),
    "rank_corr_train_vs_test": round(float(np.corrcoef(rank(tt), rank(te))[0, 1]), 3) if len(ok) > 2 else None,
    "buy_hold": {k: round(float(CL[m][-1] / O[m][0, 0] - 1) * 100, 1) for k, m in (("train", train), ("test", test))},
    "long_open_to_close_every_day": {"train": stats([(i, oc[i]) for i in range(D)], train), "test": stats([(i, oc[i]) for i in range(D)], test)},
    "long_overnight_every_day": {"train": stats([(i, on[i]) for i in range(1, D)], train), "test": stats([(i, on[i]) for i in range(1, D)], test)},
}
# the "rhythm" itself: average move per 30-min block, train vs test
blocks = list(range(0, 390, 30))
br = np.stack([C[:, min(b + 29, 389)] / O[:, b] - 1 for b in blocks], 1) * 1e4
summary["avg_bps_by_30min_block"] = {"blocks_from_open": blocks, "train": [round(float(x), 1) for x in br[train].mean(0)], "test": [round(float(x), 1) for x in br[test].mean(0)],
                                     "corr": round(float(np.corrcoef(br[train].mean(0), br[test].mean(0))[0, 1]), 3)}
summary["avg_daily_range_pct"] = {k: round(float(np.nanmean((Hh[m].max(1) - L[m].min(1)) / O[m][:, 0])) * 100, 2) for k, m in (("train", train), ("test", test))}
best_test = sorted(ok, key=lambda r: -r["test"]["t"])[:10]
json.dump({"summary": summary, "top15_by_train": top, "best10_in_test_hindsight": best_test,
           "by_family": {f: {"versions": sum(r["family"] == f for r in ok), "train_pos": sum(r["family"] == f and r["train"]["avg_bps"] > 0 for r in ok),
                             "test_pos": sum(r["family"] == f and r["test"]["avg_bps"] > 0 for r in ok),
                             "train_t_over_2": sum(r["family"] == f and r["train"]["t"] > 2 for r in ok),
                             "top3_by_train": [{"rule": r["rule"], "train": r["train"], "test": r["test"]} for r in [x for x in ok if x["family"] == f][:3]]} for f in sorted({r["family"] for r in ok})},
           "all": res, "note": __doc__}, open(OUT, "w"), indent=1)
print(json.dumps(summary, indent=1))
for r in top: print(f"{r['train']['t']:6.2f} {r['train']['avg_bps']:7.1f} | test {r['test'].get('t')} {r['test'].get('avg_bps')} bps n={r['test'].get('trades')} | {r['family']}: {r['rule']}")
