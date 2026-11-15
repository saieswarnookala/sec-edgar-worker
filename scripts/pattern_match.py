"""Pattern matching ("find the lookalikes"), Nov 14 2026. Research only, not financial advice.
For each stock and day t: take the shape of the last L daily moves, find the K most similar past stretches
(only stretches whose outcome was already known by day t: no peeking), and look at what happened next.
If the lookalikes mostly went up, buy at the next open and sell at the close H days later.
Neighbor pool: the stock's OWN history ("its habits"), or ALL stocks in the list (more examples).
Pick settings on 2017-2022, check them unchanged on 2023-2026. Every trade is compared with simply holding that
same stock for the same H days on an average day (excess), so a rising stock can't fake skill.
Stock list mixes winners AND losers (INTC, PYPL, BA, DIS, NKE, PFE, MMM, WBA...) to limit hindsight. Cost 0.05%/side."""
import os, json, time, urllib.request, urllib.parse, urllib.error
import numpy as np, pandas as pd

SYMS = ("ORCL NVDA TSLA AMD PLTR COIN AAPL MSFT AMZN META GOOGL NFLX INTC PYPL BA DIS NKE PFE MMM WBA "
        "SNAP ROKU PTON ZM SPY QQQ").split()
OUT = "data/pattern_match.json"
COST = 0.0005
SPLIT = np.datetime64("2023-01-01")
H_ = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}

def get(url):
    for i in range(6):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H_), timeout=120))
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404, 422): print("HTTP", e.code, e.read()[:200], flush=True); return None
            time.sleep(5 * (i + 1))
        except Exception: time.sleep(3 * (i + 1))
    return None

end = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
rows = {}
for s in SYMS:
    p = {"symbols": s, "timeframe": "1Day", "start": "2016-01-01", "end": end, "adjustment": "all", "feed": "sip", "limit": "10000"}
    while True:
        js = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p)) or {}
        for b in (js.get("bars") or {}).get(s, []): rows.setdefault(s, {})[b["t"][:10]] = (b["o"], b["c"])
        if not js.get("next_page_token"): break
        p["page_token"] = js["next_page_token"]
SYMS = [s for s in SYMS if s in rows]
dates = sorted(rows["SPY"]); D, N = len(dates), len(SYMS); dn = np.array(dates, dtype="datetime64[D]")
O = np.array([[rows[s].get(d, (np.nan, np.nan))[0] for s in SYMS] for d in dates]); C = np.array([[rows[s].get(d, (np.nan, np.nan))[1] for s in SYMS] for d in dates])
print("stocks", N, "days", D, dates[0], dates[-1], flush=True)
with np.errstate(all="ignore"):
    LR = np.vstack([np.full(N, np.nan), np.log(C[1:] / C[:-1])])
HS = (1, 3, 5)
FWD = {h: np.vstack([np.vstack([C[h:], np.full((h, N), np.nan)]) / np.vstack([O[1:], np.full((1, N), np.nan)]) - 1]) for h in HS}
per = np.where(dn < SPLIT, 0, 1)

def feats(L, kind):
    """rows = (t, j) with a full window; returns index arrays and normalized feature matrix"""
    T, J, F = [], [], []
    for j in range(N):
        r = LR[:, j]
        for t in range(L, D):
            w = r[t - L + 1:t + 1]
            if np.isnan(w).any(): continue
            v = np.cumsum(w) if kind == "path" else w.copy()
            v = v - v.mean() if kind == "path" else v
            sd = v.std()
            if sd == 0: continue
            T.append(t); J.append(j); F.append(v / sd)
    return np.array(T), np.array(J), np.array(F, dtype=np.float32)

KMAX, GAP, MINHIST = 50, 5, 250
results, preds_store = [], {}
for L in (10, 20, 40):
    for kind in ("returns", "path"):
        T, J, F = feats(L, kind); n = len(T); sq = (F * F).sum(1)
        for pool in ("own", "all"):
            NB = np.full((n, KMAX), -1, int)
            order = np.argsort(T, kind="stable")
            if pool == "own":
                for j in range(N):
                    idx = np.flatnonzero(J == j); idx = idx[np.argsort(T[idx])]
                    Fj, Tj = F[idx], T[idx]
                    d2 = sq[idx][:, None] + sq[idx][None, :] - 2 * Fj @ Fj.T
                    d2[Tj[None, :] > Tj[:, None] - GAP] = np.inf
                    ok = (np.isfinite(d2).sum(1) >= MINHIST)
                    part = np.argpartition(d2, KMAX, axis=1)[:, :KMAX]
                    NB[idx[ok]] = idx[part[ok]]
            else:
                ud = np.unique(T)
                for b0 in range(0, len(ud), 40):
                    blk = ud[b0:b0 + 40]; q = np.flatnonzero((T >= blk[0]) & (T <= blk[-1]))
                    db = np.flatnonzero(T <= blk[0] - GAP)
                    if len(db) < MINHIST * 3: continue
                    d2 = sq[q][:, None] + sq[db][None, :] - 2 * F[q] @ F[db].T
                    part = np.argpartition(d2, KMAX, axis=1)[:, :KMAX]
                    NB[q] = db[part]
            have = NB[:, 0] >= 0
            for H in HS:
                fwd_self = FWD[H][T, J]
                nf = np.where(NB >= 0, FWD[H][T[NB], J[NB]], np.nan)
                base = {(j, p): np.nanmean(FWD[H][(per == p), j]) for j in range(N) for p in (0, 1)}
                bj = np.array([base[(J[i], per[T[i]])] for i in range(n)])
                for K in (10, 25, 50):
                    sub = nf[:, :K]
                    with np.errstate(all="ignore"):
                        mu = np.nanmean(sub, 1); up = np.nanmean(sub > 0, 1)
                    for sig in ("long if lookalikes avg up", "long if 60%+ lookalikes up", "long/short by lookalikes avg"):
                        if sig.startswith("long if lookalikes"): d = np.where(mu > 0, 1, 0)
                        elif sig.startswith("long if 60"): d = np.where(up >= 0.6, 1, 0)
                        else: d = np.sign(mu)
                        sel = have & (d != 0) & ~np.isnan(fwd_self) & ~np.isnan(mu)
                        ret = d * fwd_self - 2 * COST; exc = ret - d * bj
                        hit = (np.sign(mu) == np.sign(fwd_self))
                        for scope in ["ALL"] + SYMS:
                            sm = sel if scope == "ALL" else sel & (J == SYMS.index(scope))
                            row = {"stock": scope, "L_days": L, "shape": kind, "pool": pool, "hold_days": H, "K": K, "signal": sig}
                            for pn, pv in (("train", 0), ("test", 1)):
                                m = sm & (per[T] == pv)
                                if m.sum() < 30: row[pn] = {"trades": int(m.sum())}; continue
                                e = exc[m]
                                row[pn] = {"trades": int(m.sum()), "avg_bps": round(float(ret[m].mean()) * 1e4, 1), "excess_bps": round(float(e.mean()) * 1e4, 1),
                                           "t": round(float(e.mean() / (e.std(ddof=1) or 1e-9) * np.sqrt(m.sum() / H)), 2),
                                           "direction_hit_pct": round(float(hit[m & have & ~np.isnan(mu)].mean()) * 100, 1),
                                           "base_up_pct": round(float((fwd_self[m] > 0).mean()) * 100, 1)}
                            results.append(row)
            print("done", L, kind, pool, len(results), flush=True)

def summarize(rs, label):
    ok = [r for r in rs if r["train"].get("trades", 0) >= 100 and r["test"].get("trades", 0) >= 50]
    if len(ok) < 3: return None
    ok.sort(key=lambda r: -r["train"]["t"])
    tr, te = np.array([r["train"]["excess_bps"] for r in ok]), np.array([r["test"]["excess_bps"] for r in ok])
    rk = lambda a: a.argsort().argsort()
    top = ok[:5]
    return {"scope": label, "versions": len(ok), "train_t_over_2": int(sum(r["train"]["t"] > 2 for r in ok)), "expected_by_luck": round(len(ok) * 0.023, 1),
            "test_t_over_2": int(sum(r["test"]["t"] > 2 for r in ok)), "test_excess_positive_pct": round(float((te > 0).mean()) * 100, 1),
            "rank_corr_train_test": round(float(np.corrcoef(rk(tr), rk(te))[0, 1]), 3),
            "median_test_hit_minus_base": round(float(np.median([r["test"]["direction_hit_pct"] - max(r["test"]["base_up_pct"], 100 - r["test"]["base_up_pct"]) for r in ok])), 1),
            "top5_by_train": top}
out = {"note": __doc__, "stocks": SYMS, "period": f"{dates[0]} to {dates[-1]}", "split": str(SPLIT),
       "summary_all_stocks": summarize([r for r in results if r["stock"] == "ALL"], "ALL"),
       "per_stock": {s: summarize([r for r in results if r["stock"] == s], s) for s in SYMS}, "all": results}
json.dump(out, open(OUT, "w"), indent=1, default=float)
s = out["summary_all_stocks"]; print(json.dumps({k: v for k, v in s.items() if k != "top5_by_train"}, indent=1))
for r in s["top5_by_train"]: print(r)
for st, v in out["per_stock"].items():
    if v: print(st, v["train_t_over_2"], "/", v["expected_by_luck"], "test pos%", v["test_excess_positive_pct"], "rc", v["rank_corr_train_test"], "| best:", v["top5_by_train"][0]["train"].get("excess_bps"), "->", v["top5_by_train"][0]["test"].get("excess_bps"), v["top5_by_train"][0]["test"].get("t"))
