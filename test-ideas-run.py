"""Runs EVERY ideas/*.py with fake data (DRY=1) to prove each idea's settings still run end to end. Real results are never overwritten
(every engine writes to /tmp in DRY mode). Usage: python test-ideas-run.py [-j 4] [name-filter]"""
import os, sys, glob, subprocess, time, concurrent.futures as cf
j = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 4
flt = [a for a in sys.argv[1:] if not a.startswith("-") and not a.isdigit()]
files = sorted(f for f in glob.glob("ideas/*.py") if not flt or any(x in f for x in flt))
os.makedirs("/tmp/ideas_run", exist_ok=True)
def one(f):
    t = time.time(); name = os.path.basename(f)[:-3]
    try:
        r = subprocess.run([sys.executable, f], env={**os.environ, "DRY": "1", "NO_NOTIFY": "1", "NO_SAVE": "1"}, capture_output=True, text=True, timeout=1800)
        ok = r.returncode == 0 or r.returncode is None
        out = (r.stdout or "") + (r.stderr or ""); open(f"/tmp/ideas_run/{name}.log", "w").write(out)
        st = "skip" if "SKIP:" in out else ("ok" if ok and "Traceback" not in out else "fail")
        return name, st, round(time.time() - t), out.strip().splitlines()[-1][:140] if out.strip() else ""
    except subprocess.TimeoutExpired: return name, "fail", round(time.time() - t), "timeout"
def data_state(): return subprocess.run(["git", "status", "--porcelain", "data/"], capture_output=True, text=True).stdout
before = data_state()
warm = [f for f in files if f.endswith("us_dip_live_robinhood.py")]          # build the shared fake data once, before parallel runs
res = [one(f) for f in warm]
with cf.ThreadPoolExecutor(j) as ex: res += list(ex.map(one, [f for f in files if f not in warm]))
after = data_state()
if after != before:
    changed = sorted(set(after.splitlines()) - set(before.splitlines()))
    print("WARNING: a fake-data run changed real data files, restoring them:", changed)
    subprocess.run(["git", "checkout", "--"] + [c[3:] for c in changed if c.startswith(" M")]); res.append(("REAL-DATA-CHANGED", "fail", 0, ", ".join(changed)))
bad = [r for r in res if r[1] == "fail"]; skip = [r for r in res if r[1] == "skip"]
for n, st, s, last in res: print(f"{st.upper():4s} {n:42s} {s:4d}s  {last}")
print(f"\n{sum(r[1] == 'ok' for r in res)}/{len(res)} idea files ran on fake data; {len(skip)} skipped (need real data: {', '.join(b[0] for b in skip) or '-'})" + (f"; FAILED: {', '.join(b[0] for b in bad)}" if bad else ""))
sys.exit(1 if bad else 0)
