import sys, json, time, itertools, numpy as np
sys.argv = ["x", "/tmp/fl/ignore.json"]
exec(open("scripts/future_leaders.py").read().split("res = {")[0])
MID = int(np.searchsorted(dates.values, np.datetime64("2012-01-01")))
rows = []; t0 = time.time()
for N, q, hi, (tr, tx), ex in itertools.product((8, 10, 12, 15, 20), (0.8, 0.9), (0.85, 0.9, 0.95), ((False, False), (True, False), (True, True)), ("ma200", "trail30")):
    c = dict(kind="run", N=N, mom_q=q, near_hi=hi, trend=tr, trend_exit=tx, exit_rule=ex)
    a, ca = run(**c, st=0, lt=0, end=MID); b, cb = run(**c, st=0, lt=0, start=MID)
    rows.append(dict(c, h1=a["cagr"], h1dd=a["max_dd"], h2=b["cagr"], h2dd=b["max_dd"]))
print("configs", len(rows), "secs", round(time.time() - t0))
json.dump(rows, open("data/future_leaders_oos.json", "w"))
