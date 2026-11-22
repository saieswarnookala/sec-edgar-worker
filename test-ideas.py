"""Checks the ideas/ catalogue: every file imports, has the required fields and a run(), names follow <market>_<strategy>_<tweak>,
listed data/script/workflow paths exist, and README.md lists every file. Run: python test-ideas.py"""
import os, glob, json, importlib.util
REQ = ("file", "title", "market", "status", "date", "rules", "result", "verdict", "data", "script", "workflow", "group")
files = sorted(f for f in glob.glob("ideas/*.py") if not f.endswith("__init__.py")); readme = open("ideas/README.md").read(); cat = json.load(open("ideas/catalog.json"))
assert len(files) == len(cat), (len(files), len(cat))
bad = []
for f in files:
    sp = importlib.util.spec_from_file_location("idea", f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); I = m.IDEA
    name = os.path.basename(f)[:-3]
    if any(k not in I for k in REQ) or not callable(getattr(m, "run", None)): bad.append(f"{name}: missing fields/run")
    if I["file"] != name or name.split("_")[0] not in ("us", "in", "gl") or name != name.lower(): bad.append(f"{name}: bad name")
    if f"({name}.py)" not in readme: bad.append(f"{name}: not in README")
    for p in [x.strip().split(" ")[0].rstrip(",;") for x in (I["data"] + "," + I["script"]).split(",") if x.strip()]:
        if (p.startswith("data/") or p.startswith("scripts/")) and "*" not in p and "<" not in p and not os.path.exists(p): bad.append(f"{name}: missing {p}")
    if I["workflow"] and not os.path.exists(".github/workflows/" + I["workflow"]): bad.append(f"{name}: missing workflow {I['workflow']}")
assert not bad, "\n".join(bad)
print(f"ok   ideas catalogue: {len(files)} files, all import, named <market>_<strategy>_<tweak>, paths exist, all in README")
