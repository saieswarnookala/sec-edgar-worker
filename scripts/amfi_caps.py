"""AMFI large / mid / small cap list (SEBI categorisation) -> data/amfi_caps.json, used by the dashboard's India momentum tab.
AMFI publishes it twice a year (early Jan for Jul-Dec, early Jul for Jan-Jun): ranks 1-100 Large, 101-250 Mid, 251+ Small.
Tries the newest half-years first. FILE=path parses a local xlsx instead (test)."""
import os, io, json, datetime, urllib.request
import pandas as pd
OUT = os.environ.get("OUT", "data/amfi_caps.json")
def candidates():
    d = datetime.date.today(); out = []; ends = []
    for yy in range(d.year, d.year - 3, -1): ends += [datetime.date(yy, 12, 31), datetime.date(yy, 6, 30)]
    for e in [e for e in ends if e < d][:4]:
        tag = f"{e.day}{e.strftime('%b')}{e.year}"         # 30Jun2026 / 31Dec2025
        out += [f"https://portal.amfiindia.com/spages/AverageMarketCapitalization{tag}.xlsx",
                f"https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalization{tag}.xlsx"]
    return out
def parse(raw, src):
    x = pd.read_excel(io.BytesIO(raw), header=None, dtype=str)
    hdr = next(i for i in range(min(15, len(x))) if any("nse symbol" in str(v).lower() for v in x.iloc[i]))
    df = x.iloc[hdr + 1:].copy(); df.columns = [str(c).strip() for c in x.iloc[hdr]]
    col = lambda *ks: next(c for c in df.columns if all(k in c.lower() for k in ks))
    sym, sr = col("nse", "symbol"), col("sr")
    try: cat = col("categori")
    except StopIteration: cat = None
    caps = {}
    for _, r in df.iterrows():
        s = str(r[sym]).strip().upper()
        try: rank = int(float(r[sr]))
        except (TypeError, ValueError): continue
        if not s or s in ("NAN", "NONE", "-"): continue
        c = str(r[cat]).strip().split()[0].capitalize() if cat and str(r[cat]).strip() not in ("", "nan") else None
        if c not in ("Large", "Mid", "Small"): c = "Large" if rank <= 100 else "Mid" if rank <= 250 else "Small"
        caps.setdefault(s, {"cat": c, "rank": rank})
    assert sum(v["cat"] == "Large" for v in caps.values()) >= 80 and len(caps) > 500, f"parse looks wrong: {len(caps)} symbols"
    return caps
def main():
    if os.environ.get("FILE"): raw, src = open(os.environ["FILE"], "rb").read(), os.environ["FILE"]
    else:
        raw = src = None
        for u in candidates():
            try:
                raw = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
                if raw[:2] == b"PK": src = u; break
            except Exception as e: print("miss", u, e)
        if not src: raise SystemExit("no AMFI list found")
    caps = parse(raw, src); n = {k: sum(v["cat"] == k for v in caps.values()) for k in ("Large", "Mid", "Small")}
    asof = src.split("Capitalization")[-1].split(".")[0]
    json.dump({"note": "AMFI average market cap list (SEBI categorisation): rank 1-100 Large, 101-250 Mid, 251+ Small. Keyed by NSE symbol.",
               "asof": asof, "source": src, "built": str(datetime.date.today()), "counts": n, "caps": caps}, open(OUT, "w"), separators=(",", ":"))
    print("wrote", OUT, asof, n, len(caps), "symbols")
if __name__ == "__main__": main()
