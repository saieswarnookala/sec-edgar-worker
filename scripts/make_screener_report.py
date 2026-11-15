"""Builds site/static-data/screener_rules_report.pdf: the full findings behind the Screener tab's rules.
Reads data/screener_backtest.json, data/screener_backtest_qv.json, data/smallcap_backtest.json (if present), data/screen.json."""
import json, os, datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
J = lambda f: json.load(open(f)) if os.path.exists(f) else None
bt, qv, sc, scr = J("data/screener_backtest.json"), J("data/screener_backtest_qv.json"), J("data/smallcap_backtest.json"), J("data/screen.json")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, spaceAfter=4, alignment=0)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=12, spaceAfter=5, textColor=colors.HexColor("#1f3b70"))
P = ParagraphStyle("p", parent=ss["BodyText"], fontSize=9.5, leading=13.2, spaceAfter=5)
S = ParagraphStyle("s", parent=P, fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"))
B = ParagraphStyle("b", parent=P, leftIndent=12, bulletIndent=2)
def tbl(rows, widths, hl=()):
    t = Table([[Paragraph(str(c), S if r else ParagraphStyle("th", parent=S, textColor=colors.white, fontName="Helvetica-Bold")) for c in row] for r, row in enumerate(rows)], colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b70")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fb")])]
    for r in hl: st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#e5f4e4")))
    t.setStyle(TableStyle(st)); return t
pc = lambda v: "—" if v is None else f"{v:.1f}%"
E = []
E.append(Paragraph("Sentinel Screener: Quality at a Fair Price", H1))
E.append(Paragraph(f"Full findings behind the Screener tab rules · {datetime.date.today():%B %d, %Y} · Not financial advice", S))
E.append(Spacer(1, 8))
E.append(Paragraph("Summary", H2))
E.append(Paragraph("The Screener tab now lists up to 15 companies per size group that are <b>profitable, growing, earn a high return on shareholders' money, turn profits into real cash, carry modest debt and are not expensive</b>, ranked by a quality + value score. "
    "On S&amp;P 500 stocks from May 2013 to October 2026 this rule made <b>15.8% a year</b>, versus 14.0% for SPY, 12.8% for the same stocks bought equally and 11.2% for the old \"highest P/E\" list. "
    "It held up in both halves of the test (15.8% and 15.9%). Adding momentum or a 200-day trend filter made it worse.", P))
E.append(Paragraph("The rules", H2))
rules = [["Rule", "Setting", "Why"],
    ["Profitable both of the last two years", "Net income > 0", "Avoids one-off profits"],
    ["Sales growth, 3 years", "≥ 5% a year", "A growing business"],
    ["Sales last year", "Not shrinking", "Growth still intact"],
    ["Return on equity", "≥ 12%", "Earns well on shareholders' money"],
    ["Free cash flow", "> 0", "Operating cash flow minus capital spending"],
    ["Cash backing", "Operating cash flow ≥ 80% of net income", "Profits are real cash, not accounting"],
    ["Debt", "≤ equity", "Survives bad years"],
    ["Valuation", "P/E ≤ 40", "Not priced for perfection"],
    ["Price", "≥ $1", "Avoids penny stocks"]]
E.append(tbl(rules, [2.1 * inch, 2.2 * inch, 2.7 * inch]))
E.append(Spacer(1, 6))
E.append(Paragraph("<b>Score (0–100):</b> half quality (percentile of return on equity, net margin and free-cash-flow margin) and half value (percentile of earnings yield = 1/P/E and free-cash-flow yield = FCF ÷ market cap). "
    "Percentiles are taken only within the same size group (Mega $200B+, Large $10–200B, Mid $2–10B, Small $300M–2B, Micro $50–300M). The top 15 by score are shown.", P))
E.append(Paragraph("How we tested it", H2))
for b in ["Universe: S&amp;P 500 members at each date, including companies later removed or delisted (Johnbrick123/sp500-data).",
          "Each May (after annual reports are filed) we scored members using the previous calendar year's SEC numbers, bought the top 15 equally and held them for 12 months. 0.10% cost per trade.",
          "Period: May 2013 to October 2026. Halves: 2013–2019 and 2019–2026. Worst drop = largest peak-to-trough fall of the daily value.",
          "Fair benchmark: all scorable members bought equally (same data limits as the rule), plus SPY.",
          "Limitation: SEC's ticker file is today's, so companies whose ticker vanished can't be scored. The equal-weight benchmark shares this blind spot."]:
    E.append(Paragraph(b, B, bulletText="•"))
if bt:
    names = {"spy": "SPY", "ew_all": "All S&amp;P members, equal weight", "ew_scorable": "Scorable members, equal weight", "old_high_pe": "Old rule: highest P/E (profitable, growing)",
             "gate_quality": "Gate + quality score", "gate_qv": "Gate + quality + value (chosen)", "gate_qvg": "Gate + quality + value + growth", "gate_qvgm": "… + momentum",
             "gate_qvg_trend": "Q+V+growth, only above 200-day avg", "gate_qvgm_trend": "… + momentum, only above 200-day avg", "score_only_qvgm": "No gate, score only (Q+V+G+M)"}
    rows = [["Rule (top 15)", "Per year", "2013–19", "2019–26", "Worst drop", "Worst year"]]
    hl = []
    for k, n in names.items():
        r = bt["results"].get(k)
        if not r: continue
        rows.append([n, pc(r["cagr"]), pc(r["2013_2019"]), pc(r["2019_2026"]), pc(r["max_dd"]), pc(r["worst_year"])])
        if k == "gate_qv": hl.append(len(rows) - 1)
    E.append(KeepTogether([Paragraph("Results: which rule worked", H2), tbl(rows, [2.9 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 0.85 * inch, 0.85 * inch], hl)]))
    E.append(Spacer(1, 4))
    E.append(Paragraph("Takeaways: quality alone matched SPY; adding value (cheapness) lifted it to 15.8%. Growth and momentum as extra ranking factors pulled it down, and the 200-day trend filter hurt the most — it kept selling good companies right before they recovered. The old high-P/E list did well in 2013–19 but fell to 7.8% a year after 2019.", P))
if qv:
    lab = {"qv_top15": "Chosen rule (top 15)", "qv_top10": "Top 10", "qv_top25": "Top 25", "qv_roe10": "ROE ≥ 10%", "qv_roe15": "ROE ≥ 15%", "qv_pe30": "P/E ≤ 30", "qv_pe60": "P/E ≤ 60",
           "qv_no_debt_rule": "No debt limit", "qv_de0.5": "Debt ≤ half of equity", "qv_sg3_0": "Sales growth 3Y ≥ 0%", "qv_sg3_10": "Sales growth 3Y ≥ 10%", "spy": "SPY", "ew_scorable": "Scorable members, equal weight"}
    rows = [["Version", "Per year", "2013–19", "2019–26", "Worst drop"]]
    for k, n in lab.items():
        r = qv["qv_robust"].get(k)
        if r: rows.append([n, pc(r["cagr"]), pc(r["2013_2019"]), pc(r["2019_2026"]), pc(r["max_dd"])])
    E.append(KeepTogether([Paragraph("Is it luck? Nearby versions", H2), tbl(rows, [2.9 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch], [1]), Spacer(1, 4),
        Paragraph("9 of 11 nearby versions beat SPY, so the result doesn't hinge on one exact setting. Being too strict hurt: requiring 10%+ sales growth (10.9%) or debt below half of equity (13.4%). "
                  "Removing the debt limit tested best (19.2%), but we kept the debt rule on purpose: picking the single best result of a test usually disappoints later, and low debt protects in bad years.", P)]))
E.append(Paragraph("Mid, small and micro caps", H2))
if sc:
    E.append(Paragraph("Same rule tested on all SEC filers with Alpaca prices (2017–2026), sized each May, liquid stocks only (≥ $500k traded a day, price ≥ $2), 0.30% cost per trade. "
                       "<b>Warning:</b> companies that went bust or were bought and lost their ticker are missing, which flatters results. The fair comparison is the rule versus all liquid stocks of the same size equally weighted (same blind spot); "
                       "IWM (Russell 2000), IJR (S&amp;P 600) and MDY (S&amp;P 400) are real funds that did hold the losers.", P))
    rows = [["Size group", "Rule top 15", "2017–21", "2021–26", "Worst drop", "All same-size, equal wt", "Avg. passing"]]
    for b, o in sc["buckets"].items():
        r, e = o["rule_top15"], o["all_equal_weight"]
        npass = [x["passed"] for x in o["log"] if x["passed"] is not None]
        rows.append([b, pc(r["cagr"]), pc(r["2017_2021"]), pc(r["2021_2026"]), pc(r["max_dd"]), pc(e["cagr"]), f"{sum(npass) / max(len(npass), 1):.0f}"])
    E.append(tbl(rows, [0.9 * inch, 0.9 * inch, 0.8 * inch, 0.8 * inch, 0.85 * inch, 1.5 * inch, 0.9 * inch]))
    E.append(Spacer(1, 4))
    rows = [["Fund (same dates)", "Per year", "2017–21", "2021–26", "Worst drop"]] + [[k, pc(sc[k]["cagr"]), pc(sc[k]["2017_2021"]), pc(sc[k]["2021_2026"]), pc(sc[k]["max_dd"])] for k in ("SPY", "MDY", "IJR", "IWM") if k in sc]
    E.append(tbl(rows, [2.0 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch]))
    rows = [["Size group", "Top 10", "Top 25", "No debt limit", "ROE ≥ 10%", "P/E ≤ 30", "Sales 3Y ≥ 0%"]]
    for b, o in sc["buckets"].items():
        rows.append([b] + [pc(o[k]["cagr"]) for k in ("top10", "top25", "no_debt_rule", "roe10", "pe30", "sales3y_0")])
    E.append(Spacer(1, 6)); E.append(Paragraph("Nearby versions (per year):", P)); E.append(tbl(rows, [0.9 * inch] + [1.0 * inch] * 6))
    E.append(Spacer(1, 4)); E.append(Paragraph(sc.get("verdict") or (
        "<b>Verdict (Nov 14, 2026):</b> mixed. <b>Mid caps:</b> the rule worked, 13.3% a year vs 10.5% for all mid caps and 9.0% for MDY, ahead in both halves, but with a deeper worst drop (−50%). "
        "<b>Small caps:</b> it did not, 8.6% vs 11.3% for all small caps; nearby versions were mixed (top 10 did 11.8%). "
        "<b>Micro caps:</b> only 0–10 companies passed each year, too few to judge. "
        "<b>Large+ in this broader universe</b> trailed equal weight (8.6% vs 12.1%), unlike the S&amp;P 500 test (15.8% vs 12.8%); this test starts in 2017, misses failed companies and has fewer years, so the S&amp;P 500 test remains the main evidence. "
        "Treat the Small and Micro lists as ideas to research, not proven picks."), P))
else:
    E.append(Paragraph("Not tested yet: free data for smaller companies leaves out the ones that failed, so any result would look better than reality.", P))
if scr:
    E.append(Paragraph(f"Today's list ({scr['generated_at'][:10]})", H2))
    for b in ["Mega", "Large", "Mid", "Small", "Micro"]:
        rs = [r for r in scr["rows"] if r["bucket"] == b]
        if rs: E.append(Paragraph(f"<b>{b}</b> ({len(rs)}): " + ", ".join(f"{r['symbol']} ({r['score']})" for r in rs), P))
    E.append(Paragraph(f"{scr['counts'].get('quality_passed', '?')} of {scr['counts'].get('with_financials', '?')} companies with SEC numbers passed every rule. Numbers in brackets are the 0–100 score.", S))
E.append(Paragraph("Caveats", H2))
for b in ["Past results don't guarantee future returns. The rule's worst drop (−36%) was about the same as SPY's: these are stocks, not a safe haven.",
          "SEC data can contain errors or unusual items (e.g. a one-off gain making a P/E look very low). Always open the stock in Stock analysis before acting.",
          "Banks and insurers often pass because their debt is reported differently; judge them with care.",
          "Rebalancing once a year is what was tested. Taxes were not modeled here.",
          "Scripts: scripts/screener_backtest.py, scripts/smallcap_backtest.py, scripts/build-screen.mjs. Data: data/screener_backtest*.json, data/smallcap_backtest.json."]:
    E.append(Paragraph(b, B, bulletText="•"))
os.makedirs("site/static-data", exist_ok=True)
SimpleDocTemplate("site/static-data/screener_rules_report.pdf", pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                  title="Sentinel Screener: Quality at a Fair Price", author="Sentinel").build(E)
print("wrote site/static-data/screener_rules_report.pdf")
