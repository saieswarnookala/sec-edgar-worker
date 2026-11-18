# Dry run of the India paper bot over 60 made-up trading days: no crashes, no negative cash, buys/sells/parking all happen,
# and the planted dips get bought.
import sys, os, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); os.environ["DRY_FAKE"] = "1"
import paper_india as B
px, nifty, nb, gb = B.fake_market(days=480, n=60, seed=3)
st, buys, sells, parks = None, 0, 0, set()
for k in range(60, 0, -1):
    cut = lambda d: d.iloc[:-k] if k else d
    sig = B.signals({s: cut(d) for s, d in px.items()}, cut(nifty), cut(nb), cut(gb))
    st, r = B.step(st, sig)
    assert r is not None and st["cash"] >= -1e-6, ("negative cash", st["cash"])
    buys += sum(1 for o in r["orders"] if o["side"] == "buy" and o["symbol"].startswith("S")); sells += sum(1 for o in r["orders"] if o["side"] == "sell" and o["symbol"].startswith("S")); parks.add(sig["park"])
    if k == 1: title, body = B.fmt(sig, st, r)
print("days", len(st["history"]), "| equity", round(st["history"][-1]["equity"]), "| buy orders", buys, "sell orders", sells, "| closed trades", len(st["trades"]), "| parking used", parks)
assert buys > 0 and sells > 0 and len(st["trades"]) > 0
again, r2 = B.step(st, sig); assert r2 is None, "second run on the same day must do nothing"
print(title); print(body[:1600])
fills = [f for h in st["history"] for f in h["filled"]]
print(len(fills), "fills;", sum("NIFTYBEES" in f for f in fills), "NIFTYBEES fills"); print(fills[:14]); print(st["trades"])

# before-close account: same days, mode 'close' (decide + fill at once at the latest price)
stc, nb_, ns_ = None, 0, 0
for k in range(60, 0, -1):
    cut = lambda d: d.iloc[:-k] if k else d
    sig = B.signals({s: cut(d) for s, d in px.items()}, cut(nifty), cut(nb), cut(gb)); sig["quote_ist"] = "15:05"
    stc, r = B.step(stc, sig, "close")
    assert r is not None and stc["cash"] >= -1e-6 and not stc["pending"], "close mode must fill at once, never leave orders pending"
    import re; nb_ += sum(bool(re.match(r"BOUGHT \d+ S\d", f)) for f in r["done"]); ns_ += sum(bool(re.match(r"SOLD \d+ S\d", f)) for f in r["done"])
    if k == 1: tc, bc = B.fmt(sig, stc, r, "close", {"name": "next-open", "equity": st["history"][-1]["equity"]})
print("before-close account: equity", round(stc["history"][-1]["equity"]), "| stock buys", nb_, "| closed trades", len(stc["trades"]))
assert nb_ > 0 and len(stc["trades"]) > 0
print(tc); print(bc)
