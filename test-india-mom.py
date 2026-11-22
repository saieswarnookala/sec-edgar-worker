"""Tests for scripts/paper_india_mom.py on fake data (DRY=1)."""
import os, json, subprocess, sys
env = dict(os.environ, DRY="1", NO_NOTIFY="1", STATE="/tmp/claude-0/imom_state.json")
if os.path.exists(env["STATE"]): os.remove(env["STATE"])
def run(**kw):
    e = dict(env, **kw); r = subprocess.run([sys.executable, "scripts/paper_india_mom.py"], env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]; return json.load(open(env["STATE"])), r.stdout
st, out = run(FAKE_END="2026-08-14")
assert len(st["holdings"]) == 20, len(st["holdings"]); assert abs(sum(st["holdings"].values()) + st["cash"] - 1e6) < 1e6 * 0.007, "start money adds up (minus 0.3% cost)"
assert all(abs(v - list(st["holdings"].values())[0]) < 1 for v in st["holdings"].values()), "equal weight"
first = set(st["holdings"])
st, out = run(FAKE_END="2026-11-20")
reb = [r for r in st["rebalances"]]; assert len(reb) == 4, [r["day"] for r in reb]           # start + Sep, Oct, Nov first days
assert [r["day"][:7] for r in reb[1:]] == ["2026-09", "2026-10", "2026-11"], [r["day"] for r in reb]
assert all(len(r["hold"]) == 20 for r in reb if r["inside"]), "20 stocks when inside"
assert all(r["turnover_pct"] < 210 for r in reb), "turnover sane"
h = st["history"]; assert h[-1]["day"] == "2026-11-20" and len({x["day"] for x in h}) == len(h), "one history row per day, no repeats"
st2, out2 = run(FAKE_END="2026-11-20"); assert len(st2["rebalances"]) == 4 and st2["history"][-1] == h[-1], "re-run on the same day changes nothing"
os.remove(env["STATE"]); st3, out3 = run(FAKE_END="2026-11-20", FAKE_CRASH="1")
assert not st3["rebalances"][-1]["inside"] and st3["holdings"] == {}, "crash filter: everything sold"
print("ok   India momentum paper bot: 20 equal-weight stocks, monthly reshuffle on the first trading day, catch-up of missed days, no double runs, crash filter sells all")
