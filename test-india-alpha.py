"""Tests for scripts/paper_india_alpha.py on fake data (DRY=1)."""
import os, json, subprocess, sys
env = dict(os.environ, DRY="1", NO_NOTIFY="1", STATE="/tmp/claude-0/ialpha_state.json")
os.makedirs("/tmp/claude-0", exist_ok=True)
if os.path.exists(env["STATE"]): os.remove(env["STATE"])
def run(**kw):
    e = dict(env, **kw); r = subprocess.run([sys.executable, "scripts/paper_india_alpha.py"], env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]; return json.load(open(e["STATE"])), r.stdout
st, out = run(FAKE_END="2026-08-14")
assert len(st["holdings"]) == 50, len(st["holdings"]); assert abs(sum(st["holdings"].values()) + st["cash"] - 1e6) < 1e6 * 0.007, "money adds up"
assert all(abs(v - list(st["holdings"].values())[0]) < 1 for v in st["holdings"].values()), "equal weight"
assert all(x in st["universe"] for x in st["holdings"]) and len(st["universe"]) == 300, "top 300 universe"
a = st["rebalances"][0]["alpha_pct"]; assert list(a.values()) == sorted(a.values(), reverse=True), "picked by highest alpha"
st, out = run(FAKE_END="2026-11-20")
reb = st["rebalances"]; assert [r["day"][:7] for r in reb] == ["2026-08", "2026-10"], [r["day"] for r in reb]   # start + October only (quarterly)
assert reb[1]["day"] == "2026-10-01", reb[1]["day"]
h = st["history"]; assert h[-1]["day"] == "2026-11-20" and len({x["day"] for x in h}) == len(h), "one history row per day"
st2, _ = run(FAKE_END="2026-11-20"); assert len(st2["rebalances"]) == 2 and st2["history"][-1] == h[-1], "re-run changes nothing"
tw = dict(STATE="/tmp/claude-0/ialpha_twin.json")
if os.path.exists(tw["STATE"]): os.remove(tw["STATE"])
st3, _ = run(FAKE_END="2026-11-20", FAKE_CRASH="1", FILTER="1", **tw)
assert st3["holdings"] == {} and not st3["rebalances"][-1]["inside"], "twin with crash filter: out when Nifty is below its 100-day average"
os.remove(env["STATE"]); os.remove(tw["STATE"])
print("ok   India Alpha 50 paper bot: top-300 universe, 50 equal-weight by 1-year alpha, quarterly (Jan/Apr/Jul/Oct) reshuffle, catch-up, no double runs, filter twin")
