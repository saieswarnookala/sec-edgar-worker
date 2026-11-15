"""Run the per-stock rhythm test on a batch of symbols, one after another. One stock failing or being skipped
(too little history) never stops the rest. Writes data/rhythm_batch_log_<batch>.json with what happened to each."""
import os, sys, json, subprocess, time
syms = [s.strip().upper() for s in os.environ["SYMBOLS"].split(",") if s.strip()]
tag = os.environ.get("BATCH", "x"); log = {}
for s in syms:
    t = time.time()
    r = subprocess.run([sys.executable, "-u", os.environ.get("RHYTHM_SCRIPT", "scripts/single_stock_rhythm.py")], env={**os.environ, "SYMBOL": s}, capture_output=True, text=True)
    status = {0: "ok", 3: "skipped (too little history)"}.get(r.returncode, f"failed (exit {r.returncode})")
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    log[s] = {"status": status, "minutes": round((time.time() - t) / 60, 1), "last_lines": tail}
    print(s, status, log[s]["minutes"], "min", "|", " / ".join(tail)[:300], flush=True)
json.dump(log, open(f"data/rhythm_batch_log_{tag}.json", "w"), indent=1)
ok = sum(v["status"] == "ok" for v in log.values())
print(f"batch {tag}: {ok} ok of {len(syms)}", flush=True)
if ok == 0 and any(v["status"].startswith("failed") for v in log.values()): sys.exit(1)
