"""Build the dashboard tab 'India: real numbers (NSE data)' from data/india_pit.json and insert it into site/dashboard/page.html
between <!-- INDIA-PIT START --> and <!-- INDIA-PIT END -->. Re-run after each new india_pit run."""
import json, html, re
D = json.load(open("data/india_pit.json")); P = "site/dashboard/page.html"
e = html.escape
def pct(x, sign=False):
    if x is None: return "—"
    s = f"{x:+.1f}%" if sign else f"{x:.1f}%"; return s.replace("-", "−")
def yrs():  # years covered
    return 17.9
def nifty_after(c):  # buy & hold: 12.5% long-term tax once at the end
    m = (1 + c / 100) ** yrs(); return round(((1 + (m - 1) * 0.875) ** (1 / yrs()) - 1) * 100, 1)
def tx(o, hold=False):
    b = o["cagr"]; a = nifty_after(b) if hold else o.get("after_tax_rough_cagr")
    return f'<span class="ip-bt">{pct(b)}</span><span class="ip-at">{pct(a)}</span>'
def per(o, k): return pct(o["per"].get(k))
def row(name, o, extra="", hold=False, bold=False):
    b = (lambda s: f"<b>{s}</b>") if bold else (lambda s: s)
    t = o["test_2019_2026"]
    return (f"<tr><td>{b(name)}</td><td>{b(tx(o, hold))}</td><td>{pct(o['dd'])}</td><td>{per(o, '2009-2009')}</td><td>{per(o, '2010-2015')}</td>"
            f"<td>{per(o, '2016-2020')}</td><td>{per(o, '2021-2026')}</td><td>{pct(t['cagr'])} / {pct(t['dd'])}</td><td>{extra}</td></tr>")
HEAD = ("<thead><tr><th>Strategy</th><th>Per year<br><span class='ip-bt'>before tax</span><span class='ip-at'>after tax (est.)</span></th><th>Worst drop</th>"
        "<th>2009</th><th>2010–15</th><th>2016–20</th><th>2021–26</th><th>2019–26<br>per yr / worst</th><th>Trading</th></tr></thead>")
def table(rows): return f'<div class="sx-tablewrap"><table class="sx-scr sx-wrap">{HEAD}<tbody>{"".join(rows)}</tbody></table></div>'
dip = D["dip"]; mom = D["momentum"]; pick = D["momentum_picked_on_2009_2018"]; mix = D["mixes"]; nif = D["nifty50_with_dividends"]; dual = D["dual_momentum_nifty_gold_liquid"]
def find(u, sc, n, fr, fl, hd): return next(r for r in mom if r["universe"] == u and r["score"] == sc and r["stocks"] == n and r["rebalance"] == fr and r["crash_filter"] == fl and r["hide_in"] == hd)
idx = find("top 200", "(6m+12m)/volatility", 30, "semi-annual", "none", "liquid"); t500 = find("top 500", "(6m+12m)/volatility", 30, "semi-annual", "none", "liquid")
tr = lambda o: f"{o.get('trades_per_year')} trades/yr" if o.get("trades_per_year") else (f"turnover {o.get('turnover_per_year')}×/yr" if o.get("turnover_per_year") else "")
summary = [row("Nifty 50 buy &amp; hold (with dividends)", nif, "none", hold=True),
           row("India dip bot (today's rules)", dip["dip bot today (5d, 12%, top 200)"], tr(dip["dip bot today (5d, 12%, top 200)"]), bold=True),
           row("Momentum ≈ real Nifty200 Momentum 30 index", idx, tr(idx)),
           row("Momentum, top 500, 30 stocks, every 6 months", t500, tr(t500)),
           row("Momentum, best version (picked on 2009–2018 only)", pick, tr(pick), bold=True)]
summary += [row(e(k), v, "rebalanced daily", bold=k.startswith("30%")) for k, v in mix.items()]
summary += [row("Nifty / gold / liquid switch (drop it)", dual, f"{dual.get('switches_per_year')} switches/yr")]
dips = [row(e(k), v, tr(v), bold=k.startswith("dip bot today")) for k, v in dip.items()]
same = lambda r: all(r[k] == pick[k] for k in ("universe", "score", "stocks", "rebalance", "crash_filter", "hide_in"))
mrows = [row(("★ PICKED · " if same(r) else "") + f"{r['universe']} · {e(r['score'])} · {r['stocks']} stocks · {r['rebalance']} · filter: {r['crash_filter']}{' (' + r['hide_in'] + ')' if r['crash_filter'] != 'none' else ''}", r, tr(r),
             bold=same(r)) for r in sorted(mom, key=lambda r: -r["cagr"])]
mixes = [row(e(k), v, "", bold=k.startswith("30%")) for k, v in mix.items()] + [row("Dip bot only (for comparison)", dip["dip bot today (5d, 12%, top 200)"], "")]
RULES = f"""
<div class="sx-pb-cols">
<div><h4>India dip bot (today's rules)</h4><ul>
<li>Universe: the 200 most-traded NSE stocks (re-picked every 6 months), price above Rs 20.</li>
<li>Buy when a stock fell <b>12%+ more than Nifty over 5 days</b>, is above its 200-day average, and trading volume isn't more than 2× normal.</li>
<li>Up to 10 stocks, 10% each, biggest dips first; bought at the next morning's open.</li>
<li>Sell when it closes back above its 5-day average, or after 5 days.</li>
<li>Idle money: Nifty while Nifty is above its 100-day average, else a liquid fund.</li>
<li>Optional NSE filters: skip stocks stuck at circuit limits on 20%+ of days, and the least-traded 10%.</li></ul></div>
<div><h4>Momentum basket (best version)</h4><ul>
<li>Universe: the {e(pick['universe'])} most-traded NSE stocks (ETFs excluded), price above Rs 20.</li>
<li>Rank by <b>{e(pick['score'])}</b>{' (6-month + 12-month gain, divided by volatility, like NSE\'s momentum indices)' if 'volatility' in pick['score'] else ''}.</li>
<li>Hold the top <b>{pick['stocks']}</b>, equal amounts; reshuffle <b>{e(pick['rebalance'])}</b>. A held stock stays while it ranks within the top {int(pick['stocks'] * 1.5)} (fewer trades).</li>
<li>Crash filter ({e(pick['crash_filter'])}): if Nifty is below its 200-day average at a reshuffle, sell everything and hold <b>{e(pick['hide_in'])}</b> (gold only while gold is above its 100-day average).</li>
<li><b>Since Nov 21 the live rules are different:</b> 20 stocks, reshuffled monthly, with a 100-day crash filter (see "Rules we use now" below).</li>
<li>Simpler alternative with a real track record: a <b>Nifty200 Momentum 30 index fund</b> (≈ the {pct(idx['cagr'])} row).</li></ul></div>
<div><h4>Mix</h4><ul>
<li>Split money between the momentum basket and the dip bot (30/70 or 50/50); top back up to the split about once a month.</li>
<li>They only partly move together (monthly correlation {D.get('correlation_monthly_momentum_vs_dip')}), so the mix has a smaller worst drop than momentum alone.</li></ul></div>
<div><h4>How the test was done</h4><ul>
<li>Data: NSE's daily price archive for <b>every</b> stock traded each day (including ones later delisted or merged), 2009 – Nov 2026. No survivorship bias.</li>
<li>Splits and bonuses fixed (gaps of −18% or worse treated as corporate actions); checked against Yahoo for 6 large stocks.</li>
<li>Costs: 0.30% per buy and per sell (charges + slippage). Prices exclude stock dividends (~1–1.5%/yr), so numbers are slightly conservative.</li>
<li>After tax (est.): 20% Indian short-term tax (+cess ≈ 20.8%) on each year's net gain, losses carried forward; Nifty buy &amp; hold taxed 12.5% once at the end. Indian-resident rules; not tax advice.</li>
<li>The best momentum version was picked from 96 using 2009–2018 only; 2019–2026 is the unseen check. Expect a bit less live.</li>
<li>For Sai (US tax resident): Indian funds/ETFs (NIFTYBEES, GOLDBEES, index funds) are PFICs — avoid; this tab is for friends in India.</li></ul></div>
</div>"""
PANEL = f"""<!-- INDIA-PIT START -->
    <div class="sx-tr-panel" data-panel="indiapit" id="trading-indiapit" hidden>
    <div class="sx-card ip-wrap" data-tax="bt"><div class="sx-ch"><h3>India: real numbers on survivorship-free NSE data (2009–2026)</h3></div>
    <p class="sx-cap">Every strategy tested on NSE's own daily archive of all stocks, including ones later delisted. Built {e(D.get('built', ''))} from data/india_pit.json. Research only, not financial or tax advice.</p>
    <div class="ip-ctl"><div class="sx-seg ip-tax" role="group" aria-label="Tax"><button type="button" data-v="bt" aria-pressed="true">Before tax</button><button type="button" data-v="at" aria-pressed="false">After tax (est.)</button></div>
    <select class="sx-exch ip-show" aria-label="Show"><option value="sum">Summary</option><option value="dip">Dip bot versions</option><option value="mom">Momentum: all 96 versions</option><option value="mix">Mixes</option><option value="rules">Rules and method</option></select></div>
    <div class="ip-sec" data-s="sum"><h4>Summary</h4>{table(summary)}
    <p class="sx-cap"><b>Takeaways:</b> the dip bot is solid (14% a year, small drops). Momentum is real and stronger, but drops 35–45% in bad stretches. <b>30% momentum + 70% dip</b> earned about 5 points a year more than the dip bot with a smaller worst drop. The Nifty/gold/liquid switch lost to plain Nifty.</p></div>
    <div class="ip-sec" data-s="dip" hidden><h4>Dip bot versions</h4>{table(dips)}</div>
    <div class="ip-sec" data-s="mom" hidden><h4>Momentum basket: all 96 versions (sorted by return; ★ = picked using 2009–2018 only)</h4>{table(mrows)}</div>
    <div class="ip-sec" data-s="mix" hidden><h4>Mixes: best momentum version + dip bot</h4>{table(mixes)}</div>
    <div class="ip-sec" data-s="rules" hidden><h4>Rules and method</h4>{RULES}</div>
    </div>
    <div class="sx-card" id="ip-rules"><h3>Rules we use now: India momentum basket (paper bot 13 / "this month's 20" tab)</h3><ol class="sx-notes"><li><b>Which stocks:</b> the 500 most-traded NSE stocks (highest median daily traded value over the last 120 days). No ETFs, price above ₹20. This list is refreshed every January and July.</li>
<li><b>Ranking:</b> (6-month gain + 12-month gain) ÷ volatility (how much the price swings, over 120 days). Rewards stocks that rose a lot <i>and</i> steadily.</li>
<li><b>Hold the top 20</b>, equal amounts (5% each).</li>
<li><b>Reshuffle once a month</b>, on the first NSE trading day, using that day's closing prices. A stock you hold stays while it ranks in the top 30; otherwise sell it and buy the best-ranked stock you don't own. Then top up or trim so each is about 5% again.</li>
<li><b>Crash filter (checked at each reshuffle):</b> if the Nifty 50 closes below its 100-day average, sell all 20. Hold GOLDBEES if gold is above its own 100-day average, else a liquid fund. Buy the basket again at the first reshuffle where Nifty is back above its 100-day average.</li>
<li><b>Nothing in between:</b> no trades between reshuffles and no stop-losses (both made results worse in tests). Exception: if a stock is suspended or delisted, it's sold.</li>
<li><b>Orders:</b> delivery (CNC), not intraday. Assume about 0.3% per buy and per sell for charges and slippage. Usually 4–6 swaps a month (8–12 orders).</li></ol>
    <p class="sx-cap">Backtest of exactly these rules: 32.6%/yr before tax, worst drop −23.8% (best case). Robustness tests: plan on 25–28%/yr with bad-year drops of −30 to −40%.</p></div>
    <style>.ip-ctl{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:6px 0 12px}} .ip-wrap[data-tax="bt"] .ip-at,.ip-wrap[data-tax="at"] .ip-bt{{display:none}}</style>
    <script>(function(){{const w=document.querySelector('#trading-indiapit .ip-wrap');if(!w)return;
      w.querySelectorAll('.ip-tax button').forEach(b=>b.addEventListener('click',()=>{{w.dataset.tax=b.dataset.v;w.querySelectorAll('.ip-tax button').forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));}}));
      const sel=w.querySelector('.ip-show');sel.addEventListener('change',()=>w.querySelectorAll('.ip-sec').forEach(s=>s.hidden=s.dataset.s!==sel.value));}})();</script>
    </div>
<!-- INDIA-PIT END -->"""
s = open(P).read()
if "<!-- INDIA-PIT START -->" in s: s = re.sub(r"<!-- INDIA-PIT START -->.*?<!-- INDIA-PIT END -->", lambda m: PANEL, s, flags=re.S)
else:
    a = '    <div class="sx-tr-panel" data-panel="v3all" id="trading-v3all" hidden>'; assert a in s; s = s.replace(a, PANEL + "\n" + a, 1)
b = '      <button type="button" data-sub="indiadip">India: dip + Nifty trend</button>'
if 'data-sub="indiapit"' not in s: assert b in s; s = s.replace(b, '      <button type="button" data-sub="indiapit">India: real numbers (NSE data)</button>\n' + b, 1)
s = s.replace("'indiadip', 'india', 'calc', 'live'];", "'indiapit', 'indiadip', 'india', 'calc', 'live'];", 1) if "'indiapit'" not in s else s
open(P, "w").write(s); print("ok", len(mrows), "momentum rows")
