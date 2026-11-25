"""Paper bot 15 checks on fake prices: first run starts flat, next days fill pending orders at the next close, no double buys, state round-trips."""
import os, json, subprocess, sys, tempfile
tmp = tempfile.mkdtemp(); st = os.path.join(tmp, "s.json")
def run(day):
    env = dict(os.environ, STATE=st, FORCE_DAY=day, NO_NOTIFY="1", FAKE_SAVE="1")
    src = open("scripts/paper_crypto.py").read().replace('DRY = os.environ.get("DRY") == "1"', 'DRY = True').replace('if os.path.exists(STATE) and not DRY', 'if os.path.exists(STATE)').replace('if not (os.environ.get("NO_SAVE") or DRY):', 'if True:')
    p = os.path.join(tmp, "pc.py"); open(p, "w").write(src); out = subprocess.run([sys.executable, p], env=env, capture_output=True, text=True); assert out.returncode == 0, out.stderr; return json.load(open(st))
s1 = run("2026-11-02"); assert len(s1["history"]) == 1 and s1["start"] == "2026-11-02", s1["history"]
assert all(v["units"] == 0 for v in s1["sleeves"].values()), "first run holds nothing yet (orders fill at the next close)"
pend = {c: v["pending"] for c, v in s1["sleeves"].items()}
s2 = run("2026-11-03")
for c, v in s2["sleeves"].items():
    if pend[c] == "buy": assert v["units"] > 0 and v["cash"] == 0, (c, v)
assert len(s2["history"]) == 2
s3 = run("2026-11-03"); assert len(s3["history"]) == 2, "same day twice does nothing"
s4 = run("2026-11-13"); assert len(s4["history"]) == 10, len(s4["history"])            # catches up 8 missed weekdays
for v in s4["sleeves"].values(): assert v["units"] >= 0 and v["cash"] >= 0 and not (v["units"] > 0 and v["cash"] > 1)
print("ok   crypto paper bot: starts flat, fills next close, no repeats, catches up missed days")
