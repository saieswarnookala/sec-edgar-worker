"""Builds the ideas/ catalogue: one small file per strategy idea or tweak, plus ideas/README.md (index) and ideas/catalog.json.
Add a new idea = add one entry to CATALOG below and run:  python scripts/build_ideas.py
Each generated file holds the plain-English rules, the result, the verdict, where the data/script/workflow live, and a run() that reproduces it
with the shared engine (US: scripts/stack_and_rebound.py sim(); India: scripts/india_pit.py modes; others: their own script).
File names: <market>_<strategy>_<tweak>.py   market = us | in (India) | gl (global / crypto / currency)."""
import json, os, textwrap, pprint
ST = {"LIVE": "Live (real money)", "NEXT": "Next live candidate", "KEEP": "Paper bot, keep", "WATCH": "Watching / maybe later", "TESTING": "Test running",
      "MERGED": "Merged into a newer version", "TOOL": "Kept as a tool", "DROPPED": "Tested and dropped", "REF": "Reference / check"}
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003)
def sim(**kw): return {"kind": "sim", "kw": kw}
def script(path, env=None, args=""): return {"kind": "script", "path": path, "env": env or {}, "args": args}
def mode(m): return script("scripts/india_pit.py", {"MODE": m}, "run")
C = []
def add(file, title, market, status, date, rules, result, verdict, data="", src="", wf="", run=None, group=""):
    C.append(dict(file=file, title=title, market=market, status=status, date=date, rules=rules, result=result, verdict=verdict, data=data, script=src, workflow=wf, run=run, group=group))
# ======================================================================= US: the dip bot family
G = "US dip bot family"
add("us_dip_live_robinhood", "Live Robinhood dip bot (today's live rules)", "US", "LIVE", "2026-11-09",
    "S&P 500 stock above its 200-day average that fell 10%+ more than SPY over 5 days, 5-day volume not over 2x normal; biggest dips first, up to 10 x 10%; "
    "sell first close above the 5-day average or after 5 days; idle money in the Clear Leader ETF when SPY > 100-day average, else cash. 3:47 pm ET on an Oracle VM.",
    "1998-2026 realistic 14.9%/yr (ideal fills 22.0%), after tax ~11.9%, worst drop -25 to -28%. Live since Nov 2026 with ~$100; halts at -40% from peak.",
    "LIVE. Planned switch to v3.0 rules around Dec 3 if paper bot 10 stays clean.", "data/dip_curve.csv", "live/ (bot), scripts/stack_and_rebound.py (backtest)", "", sim(**LIVE), G)
add("us_dip_v3_0_etf_dips_bonds", "Dip bot v3.0 = live rules + ETF dips + bonds when weak (paper bot 10)", "US", "NEXT", "2026-11-19",
    "Live stock rules; free slots go to index/sector/country ETFs down 5%+ in 5 days and above their 200-day (held up to 10 days); idle money: Clear Leader when "
    "SPY > 100-day, else IEF bonds if IEF > its 100-day, else cash.",
    "1999-2026 realistic 16.6%/yr vs 13.4% for live rules (same test); ideal 22.8 vs 18.5. Better in both halves and with doubled costs. Worst drop ~ -27%.",
    "Next live version (~Dec 3).", "data/stack_and_rebound.json", "scripts/stack_and_rebound.py, scripts/paper-dip.mjs", "paper-dip.yml", sim(etf=True, bond=True, **LIVE), G)
add("us_dip_v3_1_drift2", "Dip bot v3.1 = v3.0 + 2 earnings-drift slots (paper bot 11)", "US", "WATCH", "2026-11-20",
    "v3.0 plus 2 of the 10 slots reserved for earnings-drift buys (stock beat SPY by 4-6%+ on its earnings day, hold 60 days).",
    "Adds ~0.5-1%/yr over v3.0 in 1999-2026 but the drift edge has faded since 2021 (v3.2 + 2 drift: 31.0% vs 30.5%, worse 2021-26).",
    "Watch on paper; not adopted.", "data/intraday_combo.json", "scripts/stack_and_rebound.py (drift=2)", "paper-dip.yml", sim(etf=True, bond=True, drift=2, **LIVE), G)
add("us_dip_v3_2_intraday_target5", "Dip bot v3.2 = v3.0 + intraday dip buys every 15 min + 5% profit target (paper bot 12)", "US", "WATCH", "2026-11-19",
    "v3.0, but dips are also bought during the day (checks every 15 minutes on 5-minute bars) and a position is sold intraday at +5%.",
    "2016-2026 5-minute replay 30.5%/yr vs v3.0 27.2%; 2x costs 27.9 vs 25.4; better in 9 of 11 years (worse 2023, 2024).",
    "Watch on paper (started late: Friday timer bug).", "data/intraday_final.json", "scripts/intraday_exits.py, scripts/paper-v32.mjs", "paper-v32.yml", script("scripts/intraday_exits.py"), G)
add("us_dip_vol_sizing", "Volatility-sized dip buys (paper bot 2)", "US", "WATCH", "2026-11-16",
    "Live rules, but position size scales with market jumpiness: 0.5x when calm, up to 1.5x when SPY is volatile.",
    "16.1%/yr, worst -25% vs 14.9% / -26% (gain mostly 2008-09); 4 of 4 versions better.", "Watch on paper.",
    "data/dip_filter_ev_vol.json", "scripts/stack_and_rebound.py (vol=True)", "paper-dip.yml", sim(vol=True, **LIVE), G)
add("us_dip_etf_sleeve", "ETF dips in free slots (paper bot 5)", "US", "MERGED", "2026-11-14",
    "Live stock rules + 29 index/sector/country ETFs: 5-day drop >= 5%, above 200-day, buy at the close, sell back above the 5-day average (max 10 days).",
    "Combined 17.1%/yr, worst -22.4% vs 14.9% / -26.7%; better in both halves.", "Merged into v3.0.",
    "data/combined_dip_etf.json", "scripts/combined_dip_etf.py, scripts/etf_dips.py", "", sim(etf=True, **LIVE), G)
add("us_dip_bonds_parking", "Bonds instead of cash when stocks are weak (paper bot 9)", "US", "MERGED", "2026-11-19",
    "Idle money in IEF (7-10 yr Treasuries) when SPY is below its 100-day average and IEF is above its own 100-day average.",
    "Adds ~0.5-1%/yr with the same worst drop.", "Merged into v3.0.", "data/stack_and_rebound.json", "scripts/stack_and_rebound.py (bond=True)", "", sim(bond=True, **LIVE), G)
add("us_dip_short_interest_filter", "Skip dips in heavily shorted stocks (paper bot 8)", "US", "WATCH", "2026-11-15",
    "Live rules, but skip a dip if days-to-cover (FINRA short interest, 12-day lag) is 5 or more. Data only from Dec 2017.",
    "Small, noisy gain on 2018-2026 only.", "Watch on paper.", "data/short_dips.json", "scripts/short_dips.py; stack_and_rebound.py (short=True)", "short-dips.yml", sim(short=True, **LIVE), G)
add("us_dip_tuned_etf", "Tuned dip settings + ETF dips (paper bot 6)", "US", "WATCH", "2026-11-16",
    "Tuned version of the dip rules (settings in scripts/paper-dip.mjs) plus the ETF sleeve.", "Backtest ~19.4%/yr in the 52-week-high test runs (ideal fills).",
    "Watch on paper.", "data/dip_rank_52w.json", "scripts/paper-dip.mjs", "paper-dip.yml", script("scripts/paper-dip.mjs"), G)
add("us_dip_drift_6_4_mix", "6 dip slots + 4 earnings-drift slots (paper bot 7)", "US", "MERGED", "2026-11-11",
    "One account: 6 dip slots + 4 drift slots (caps matter).", "2004-2026 realistic 15.8%/yr (ideal 19.1%), after tax 12.3%, worst -24%; 45 nearby versions beat SPY.",
    "Replaced by v3.1.", "data/v3_drift.json, data/paper_mix_state.json", "scripts/stack_and_rebound.py (drift=4)", "", sim(drift=4, **LIVE), G)
add("us_earnings_drift", "Earnings drift, blend of 9 (paper bot 3, Alpaca $100k)", "US", "WATCH", "2026-11-08",
    "Stock beat SPY by >= 4-6% on its earnings reaction day (SEC 8-K 2.02 timing); buy next open, hold 60 trading days.",
    "~13%/yr before tax, worst -51%; out-of-sample 2004-2015 ok, faded since 2021.", "Watch on paper.", "data/earnings_drift_pit.json, data/paper_drift_state.json", "scripts/paper-drift.mjs", "paper-drift.yml", None, G)
# --- tweaks tested on the dip bot
G = "US dip bot tweaks"
add("us_dip_v3_0_lev2x", "v3.0 with 1.5x / 2x leverage on dip stocks (2x ETF or margin)", "US", "TESTING", "2026-11-22",
    "Same signals; each dip stock held at 1.5x or 2x. Costs: 2x-ETF style (borrow + 1.1% fee) or margin (T-bill + 3%). Variant: leverage only when SPY > 100-day.",
    "Running (data/lev_single.json).", "Pending.", "data/lev_single.json", "scripts/lev_single.py", "lev-single.yml", sim(etf=True, bond=True, lev=2.0, lev_cost=0.016, **LIVE), G)
add("us_dip_vix_gate", "VIX gate on the dip bot", "US", "DROPPED", "2026-11-21", "Only buy dips when VIX is in a chosen band.",
    "Did not fix the weak 2013-2019 stretch (best ~9.3%/yr).", "Dropped.", "data/vix_gate.json", "scripts/vix_gate.py", "vix-gate.yml", script("scripts/vix_gate.py"), G)
add("us_dip_sector_relative", "Sector-relative dips", "US", "DROPPED", "2026-11-20", "Measure the dip against the stock's sector ETF instead of SPY (or both).",
    "Worse than vs-SPY dips.", "Dropped.", "data/three_tests.json", "scripts/three_tests.py (part A)", "three-tests.yml", script("scripts/three_tests.py"), G)
add("us_dip_stress_test", "Stress test: beta, alpha, kill switch", "US", "REF", "2026-11-20", "Split v3.0 returns into market (beta) and own edge (alpha); resampled 3-year drawdowns.",
    "Beta 0.45, alpha ~17%/yr but ~0 in 2013-2019; kill switch set at -40%.", "Reference (kill switch adopted).", "data/three_tests.json", "scripts/three_tests.py (part B)", "three-tests.yml", None, G)
add("us_dip_blend_spy_trend", "Blend: SPY + dip bot + Faber trend sleeve", "US", "DROPPED", "2026-11-20", "Mixes of SPY buy & hold, v3.0 and a 5-ETF 10-month trend sleeve, monthly rebalance.",
    "No mix beat the dip bot alone after tax.", "Dropped.", "data/three_tests.json", "scripts/three_tests.py (part C)", "three-tests.yml", None, G)
add("us_dip_same_day_sell5", "Same-day sell at +5%", "US", "DROPPED", "2026-11-20", "Sell a dip position the same day if it is up 5% intraday.",
    "31.1%/yr but better in only 3 of 11 years.", "Dropped.", "data/intraday_sameday.json", "scripts/intraday_exits.py (SAME_DAY=1)", "", script("scripts/intraday_exits.py", {"SAME_DAY": "1"}), G)
add("us_dip_slots_and_size", "Slot count and dip size", "US", "DROPPED", "2026-11-20", "3-15 slots; dip threshold 8-14%.",
    "10 slots and a 10% dip are the peak; 3 slots 7.8%/yr, -57% worst.", "Keep 10 slots, 10% dip.", "data/intraday_combo.json, data/dip_slots.json", "scripts/intraday_exits.py (COMBO=1)", "", script("scripts/intraday_exits.py", {"COMBO": "1"}), G)
add("us_dip_wash_sale_cooldown", "Wash-sale cooldown (no re-buy within 31 days of a loss)", "US", "DROPPED", "2026-11-20", "Skip re-buying a ticker within 31 days of a losing sale (or only in December).",
    "After tax unchanged (19.5% live-like).", "Not needed.", "data/tax_news_tests.json", "scripts/tax_news_tests.py; sim(cool='31d')", "tax-news.yml", sim(cool="31d", etf=True, bond=True, **LIVE), G)
add("us_dip_news_proxies", "News proxies (gaps, 8-K filings, shocks)", "US", "DROPPED", "2026-11-20", "Skip dips with earnings, 8-K news, one-day shocks, gaps, Fed days etc.",
    "All inside the random-skip range.", "Keep all signals.", "data/tax_news_tests.json, data/dip_filter_ev_*.json", "scripts/tax_news_tests.py", "tax-news.yml", None, G)
add("us_dip_stop_loss", "Stop-losses / trailing stops", "US", "DROPPED", "2026-11-10", "Exit a dip at a fixed loss or trailing stop.", "Cuts the winners; lower return.", "Dropped.", "data/dip_filter_*.json", "", "", None, G)
add("us_dip_insider_filter", "Insider buying as a dip filter", "US", "DROPPED", "2026-11-15", "Only buy dips with recent officer/director buying (SEC Form 4).",
    "No gain.", "Dropped.", "data/insider_dips.json", "scripts/insider_dips.py", "insider-dips.yml", None, G)
add("us_dip_52w_high_rank", "Rank dips by distance from the 52-week high", "US", "DROPPED", "2026-11-15", "Buy dips 20%+ below the 52-week high first.",
    "14.4 vs 14.9%/yr (noise).", "Dropped.", "data/dip_rank_52w.json", "scripts/dip_rank_52w.py", "", None, G)
add("us_dip_close_at_low_filter", "Candles: dips that closed at the low", "US", "DROPPED", "2026-11-15", "Prefer dips that closed at the day's low.",
    "17.4 vs 17.1%/yr with a deeper worst drop.", "Dropped.", "data/candles.json", "scripts/candles.py", "", None, G)
add("us_dip_managed_futures_slice", "Managed-futures slice next to v3.0 (Roth)", "US", "DROPPED", "2026-11-22", "Add 10-30% AQMIX / DBMF / KMLM, monthly rebalance.",
    "Return falls in proportion (20.2 -> 17.2%/yr with 20% AQMIX since 2010), Sharpe +0.03. Next to SPY it helps a lot (worst -24 -> -13 to -16%).",
    "Not beside the dip bot; maybe beside an SPY core.", "data/mf_slice.json", "scripts/mf_slice.py", "mf-slice.yml", script("scripts/mf_slice.py"), G)
# ======================================================================= US: other strategies
G = "US other strategies"
add("us_spy_2x_trend200_band2", "2x S&P 500 with a 200-day trend filter (2% band)", "US", "WATCH", "2026-11-22",
    "Hold a 2x S&P fund (SSO) after SPY closes 2% above its 200-day average; T-bills after it closes 2% below. ~1.5 switches a year. Roth (no tax on switches).",
    "SPY 1994-2026: 14.4%/yr, worst -42% vs SPY 10.4% / -55%. Robustness: 16 nearby settings 7.7-15.4% (median 12.5); 10% of random schedules beat it; "
    "works on Nasdaq/intl, fails on small caps/EM/Dow; helps in slow bears (2000-02, 2008), hurts in fast ones (2020 -40%, 2018 -27%); 21 of 23 start years beat SPY.",
    "Watch: real but fragile; at most a small Roth sleeve.", "data/three_markets.json, data/lev_robust.json", "scripts/three_markets.py, scripts/lev_robust.py", "lev-robust.yml", script("scripts/lev_robust.py"), G)
add("us_single_stock_2x_trend", "2x single stocks (Oracle-style ETFs) with a trend filter", "US", "TESTING", "2026-11-22",
    "Hold a stock at 2x while it is 2% above its 200-day average, else T-bills. Fair test: every S&P 500 member on 2000-01-03 (incl. losers); hindsight list: ORCL, NVDA, TSLA...",
    "Running.", "Pending.", "data/lev_single.json", "scripts/lev_single.py", "lev-single.yml", script("scripts/lev_single.py"), G)
add("us_clear_leader_v2", "Clear Leader v2.0 (monthly ETF leader)", "US", "TOOL", "2026-11-04", "Monthly: hold the strongest of a small ETF set (124,416-combo grid).",
    "13.6%/yr, worst -43%.", "Kept only to choose where idle dip money parks.", "data/clear_leader*.json", "", "", None, G)
add("us_quality_screener", "Quality at a fair price screener", "US", "TOOL", "2026-11-14", "Profitable, growing, ROE >= 12%, FCF > 0, debt <= equity, P/E <= 40; rank half quality, half value; hold 12 months.",
    "2013-2026 15.8%/yr vs SPY 14.0%; 9 of 11 nearby versions beat SPY.", "Kept as the dashboard screener.", "data/screener_backtest*.json", "scripts/screener_backtest.py", "", script("scripts/screener_backtest.py"), G)
add("us_net_buybacks", "Net buybacks (top 10 share shrinkers)", "US", "WATCH", "2026-11-12", "Monthly: 10 S&P 500 stocks whose share count fell most over a year; hold >= 63 days.",
    "17.8%/yr vs SPY 13.9%, worst -43%; but one stock (WDC) added ~30 pts and it beat SPY in only 8 of 16 years.", "Maybe later as a small sleeve.", "data/new_ideas_buyback2.json", "docs/BUYBACKS.md", "", None, G)
for f, t, d, r, res, data, src in (
    ("us_intraday_orb", "Opening-range breakout and intraday rules", "2026-11-08", "ORB 5-min/1-min, half-hour, SPY noise-area momentum, Ledger scan.", "ORB ~ -8%/yr even at zero cost; SPY momentum ~0% since May 2024.", "data/intraday_*.json", ""),
    ("us_intraday_rhythms", "Single-stock intraday rhythms", "2026-11-14", "~800 intraday / 1-3 day rules per stock (ORCL, NVDA, TSLA, AMD, PLTR, COIN).", "Nothing beat costs.", "data/rhythm_*.json", "scripts/single_stock_rhythm.py"),
    ("us_rsi2_dip", "RSI(2) dip", "2026-11-03", "Buy when 2-day RSI is very low.", "Below the dip strategy.", "", ""),
    ("us_atr_swing", "ATR swing trading", "2026-11-12", "Buy with a direction filter, sell at k x ATR target, 1-3 day hold (384 versions).", "Loses; an earlier 134%/yr was a data artifact.", "data/atr_swing3.json, data/atr_minute.json", "scripts/atr_minute.py"),
    ("us_short_selling", "Short selling (all kinds)", "2026-11-12", "Mirror dip, mirror drift, SPY short, lottery, losers, long/short, hedged dip.", "-4% to -25%/yr.", "data/short_side.json", ""),
    ("us_options_buying", "Buying options (calls, protective puts)", "2026-11-12", "Calls on signals; protective puts.", "-1% to -14%/yr.", "data/options_research.json", ""),
    ("us_options_putwrite", "Selling puts (Cboe PutWrite index)", "2026-11-12", "Sell monthly cash-secured S&P puts.", "8.6%/yr, -37% vs SPY 10.3%, -55% (1996-2026).", "data/options_research.json", ""),
    ("us_future_leaders", "Future leaders (let winners run momentum)", "2026-11-12", "Momentum leaders held long.", "Picked on 1998-2011 -> 12.8% in 2012-26 vs SPY 14.7%.", "data/future_leaders*.json", ""),
    ("us_insider_clusters", "Insider buying clusters", "2026-11-15", "Buy stocks with clusters of officer/director buying.", "Failed unseen years (12.3% vs SPY 14.9% in 2016-26).", "data/insider_dips.json", ""),
    ("us_index_changes", "S&P 500 additions / removals", "2026-11-15", "Buy joiners or removed stocks.", "Joiners lag; removal bounce only worked 1999-2012.", "data/index_changes.json", "scripts/index_changes.py"),
    ("us_52w_high_momentum", "52-week-high momentum", "2026-11-15", "Buy stocks at 52-week highs.", "6-11%/yr vs SPY 9.2%.", "", ""),
    ("us_spinoffs", "Spin-offs", "2026-11-15", "Buy new spin-offs, hold 1 year.", "Median -2.4% vs SPY; a few huge winners.", "data/spinoffs.json", "scripts/spinoffs.py"),
    ("us_overnight_effect", "Overnight-only SPY", "2026-11-16", "Buy at the close, sell at the open.", "9.9%/yr before costs; ~0 after 0.02%/side.", "data/calendar_effects.json", "scripts/calendar_effects.py"),
    ("us_pre_fomc", "Pre-FOMC drift", "2026-11-16", "Hold SPY on Fed announcement days.", "Faded after 2011.", "data/calendar_effects.json", "scripts/calendar_effects.py"),
    ("us_13f_best_ideas", "13F best ideas", "2026-11-16", "Top holdings of concentrated managers.", "No edge after the 45-day filing lag.", "data/thirteenf_best_ideas.json", "scripts/thirteenf_best_ideas.py"),
    ("us_chart_patterns", "Chart patterns", "2026-11-15", "Breakouts, flags, VCP, H&S, double bottoms.", "~0 after costs.", "data/chart_patterns_*.json", "scripts/chart_patterns.py"),
    ("us_nr7_breakout", "Crabel NR7 / NR4 breakout", "2026-11-17", "Narrowest range of 7 days, buy above its high.", "All 12 versions lose.", "data/nr7_breakout.json", "scripts/nr7_breakout.py"),
    ("us_pattern_matching", "Pattern matching / lookalikes", "2026-11-14", "Nearest-neighbour on the last 10-40 daily moves.", "Nothing real.", "data/pattern_match.json", "scripts/pattern_match.py"),
    ("us_volatile_bounce", "Volatile-stock bounce", "2026-11-14", "~10k bounce scenarios on volatile names.", "Filters help a little; no tradable edge.", "data/volatile_bounce_*.json", "scripts/volatile_bounce.py"),
    ("us_covered_call_etfs", "Covered-call ETFs (JEPI, QYLD)", "2026-11-22", "Hold covered-call income ETFs.", "Since 2020: JEPI 10.2%, QYLD 8.5% vs SPY 15.5%.", "", "research report")):
    add(f, t, "US", "DROPPED", d, r, res, "Dropped.", data, src, "", script(src) if src.startswith("scripts/") and src.endswith(".py") else None, G)
# ======================================================================= Global / crypto / currency
G = "Global, crypto and currency"
add("gl_bitcoin_10month_trend", "Bitcoin 10-month trend", "Global", "WATCH", "2026-11-20", "Hold Bitcoin (spot ETF) while above its 10-month average, else cash; checked monthly.",
    "2014-2026 ~60%/yr vs hold 49%; worst -72% vs -83%; 2022 +2% vs -65%. Robust for crash protection, not for extra return (only 2.8% of random schedules beat it).",
    "Maybe later: a 5% slice (10% max).", "data/crypto_trend.json, data/crypto_robust.json", "scripts/crypto_trend.py, scripts/crypto_robust.py", "crypto-robust.yml", script("scripts/crypto_robust.py"), G)
add("gl_ether_trend", "Ether trend rules", "Global", "DROPPED", "2026-11-20", "Same trend rules on Ether.", "Inconsistent.", "Dropped.", "data/crypto_trend.json", "scripts/crypto_trend.py", "crypto-trend.yml", script("scripts/crypto_trend.py"), G)
add("gl_usd_inr_timing", "When to send USD -> INR", "Global", "DROPPED", "2026-11-22", "Convert $1,000/month on the 1st vs when the dollar is strong (above 50-day / 60-day high, max wait 3 months).",
    "Every rule within -0.25..0% of converting on the 1st (2004-2026); rupee weakened 3.2%/yr.", "Send on schedule.", "data/three_markets.json", "scripts/three_markets.py", "three-markets.yml", script("scripts/three_markets.py"), G)
add("gl_india_via_us_etfs", "India via US-listed ETFs for the Roth (INDA / SMIN)", "Global", "DROPPED", "2026-11-22", "Hold or rotate INDA, SMIN, EPI, GLD, cash.",
    "INDA 6.7%/yr vs SPY 13.4% (2013-2026); no rotation beat SPY.", "Dropped.", "data/india_usproxy.json", "scripts/india_usproxy.py", "india-usproxy.yml", script("scripts/india_usproxy.py"), G)
# ======================================================================= India
G = "India (friends and family)"
add("in_momentum_bot13", "India momentum basket (paper bot 13, 'this month's 20')", "India", "KEEP", "2026-11-20",
    "Top 500 NSE stocks by traded value; score (6m+12m return)/volatility; hold top 20 equal weight; reshuffle on the 1st trading day of each month; keep while in the top 30; "
    "crash filter: Nifty below its 100-day average -> GOLDBEES (if gold above its 100-day) else liquid fund.",
    "2009-2026 survivorship-free: 32.6%/yr best case, ~27% realistic (honest), worst -24 to -34%; lot-level after tax 22.6% realistic vs Nifty 14.5%.",
    "Keep: main India strategy.", "data/india_pit.json, data/paper_india_mom_state.json", "scripts/paper_india_mom.py, scripts/india_pit.py", "paper-india-mom.yml", mode("momrobust"), G)
add("in_alpha50_bot14", "India Alpha 50, our version (paper bot 14)", "India", "WATCH", "2026-11-22",
    "Top 300 by traded value; 1-year Jensen's alpha vs Nifty; top 50 equal weight; quarterly (Jan/Apr/Jul/Oct); no crash filter.",
    "2009-2026 22.0%/yr, worst -47% (no trading costs); plan 17-20%; after tax barely above Nifty.", "Watch on paper.", "data/india_factor.json, data/paper_india_alpha_state.json", "scripts/paper_india_alpha.py", "paper-india-mom.yml", mode("factor"), G)
add("in_dip_bot", "India dip bot (virtual Rs 10 lakh)", "India", "DROPPED", "2026-11-18", "India version of the US dip rules (5-day 12% vs Nifty, top 200, 200-day).",
    "14.0%/yr (worst -19.5%) = Nifty 14.5%; loses after tax.", "Weak; paper only.", "data/india_pit.json", "scripts/india_dip.py, scripts/paper_india.py", "paper-india.yml", mode("run"), G)
for f, t, d, r, res, data, m in (
    ("in_momentum_100day_filter", "Momentum crash filter: 100-day vs 200-day", "2026-11-21", "Nifty vs its 100- or 200-day average at each reshuffle.", "100-day 32.6% / -23.8 vs 200-day 30.6% / -37.5; 100-day wins in all split tests.", "data/india_momrisk.json", "momrisk"),
    ("in_momentum_weekly_reshuffle", "Momentum: weekly reshuffle", "2026-11-21", "Reshuffle weekly instead of monthly.", "Worse; worst drop -58.8%.", "data/india_momrisk.json", "momrisk"),
    ("in_momentum_stops_voltarget", "Momentum: stops, daily checks, vol targets", "2026-11-21", "Stop-losses, trailing stops, drawdown stop, volatility targeting.", "None helped.", "data/india_momrisk.json", "momrisk"),
    ("in_momentum_split_reshuffle", "Momentum: split the reshuffle across days", "2026-11-21", "2-4 parts reshuffled on different days.", "Averages day luck (26.7-29.2%), no smaller drops, double the orders.", "data/india_momsplit.json", "momsplit"),
    ("in_momentum_junk_filters", "Momentum: junk filters", "2026-11-22", "Skip circuit-locked stocks, bottom-10% turnover, -10% days (on 3x volume).", "All within +-0.5 pt.", "data/india_ideas3.json", "ideas3"),
    ("in_momentum_slot_check", "Momentum: per-stock check (12m > liquid and above own 200-day)", "2026-11-22", "Fill a slot only with stocks passing the check.", "+0.6 pt (27.3%); without the Nifty filter worst drop -45%.", "data/india_ideas3.json", "ideas3"),
    ("in_lowvol_basket", "Low-volatility basket and blends", "2026-11-22", "Lowest 1-year volatility, top 200/500, 30/50 stocks; blends with momentum.", "13-15.6%/yr (~Nifty); blends cost return without cutting drops.", "data/india_ideas3.json", "ideas3"),
    ("in_momentum_every2_3months", "Momentum: reshuffle every 2 or 3 months (after tax)", "2026-11-22", "Slower reshuffles, buffers top 30/40/50, lot-level tax.", "After tax 20.7-22.7% vs 22.6% monthly; quarterly = half the trading but worst drop -41%.", "data/india_slowtax.json", "slowtax"),
    ("in_momentum_let_winners_run", "Momentum: let winners run (no trims)", "2026-11-22", "Kept stocks are not trimmed back to 5%.", "+0-0.2 pt after tax, deeper drops.", "data/india_slowtax.json", "slowtax"),
    ("in_momentum_skip_month", "Momentum score: skip the last month", "2026-11-22", "(6-1 + 12-1)/vol.", "21.7% vs 22.6% after tax (honest).", "data/india_slowtax.json", "slowtax"),
    ("in_momentum_6m_weight", "Momentum score: more weight on 6 months", "2026-11-22", "(2 x 6m + 12m)/vol.", "21.3% after tax.", "data/india_slowtax.json", "slowtax"),
    ("in_momentum_no_vol_divisor", "Momentum score: no volatility divisor", "2026-11-22", "6m + 12m.", "20.0% after tax.", "data/india_slowtax.json", "slowtax"),
    ("in_momentum_residual", "Momentum score: residual momentum", "2026-11-22", "12-1 return beyond what Nifty explains / residual vol.", "19.6% after tax, worst drop -26% (smaller).", "data/india_slowtax.json", "slowtax"),
    ("in_momentum_clenow", "Momentum score: Clenow 90-day slope x R-squared", "2026-11-22", "Exponential trend slope x fit.", "14.8% after tax.", "data/india_slowtax.json", "slowtax"),
    ("in_momentum_smooth_trend", "Momentum: smooth-trend filter (frog in the pan)", "2026-11-22", "Top 40 by score, keep the 20 smoothest climbers.", "21.6% after tax, worst drop -27%.", "data/india_slowtax.json", "slowtax"),
    ("in_factor_rotation", "Factor index rotation (Momentum / Alpha / Low Vol)", "2026-11-22", "Rotate between rebuilt factor indices by 6/12-month return.", "Adds 0-1 pt over holding one; factors move together.", "data/india_factor.json", "factor"),
    ("in_size_switch", "Large vs mid vs small switch", "2026-11-22", "Monthly switch to the best size index.", "5-9%/yr.", "data/india_factor.json", "factor"),
    ("in_dual_momentum_nifty_gold_liquid", "Nifty / gold / liquid switch", "2026-11-21", "Hold the best of Nifty, gold, liquid by trailing return.", "7.9%/yr.", "data/india_pit.json", "run")):
    add(f, t, "India", "DROPPED" if f not in ("in_momentum_100day_filter",) else "KEEP", d, r, res, "Adopted (in bot 13)." if f == "in_momentum_100day_filter" else "Dropped.", data, "scripts/india_pit.py (MODE=" + m + ")", "india-pit.yml", mode(m), G)
add("in_nifty_gold_ratio", "Nifty vs gold ratio rule", "India", "WATCH", "2026-11-22", "Monthly: 30/70 Nifty/gold when Nifty is expensive vs gold (z > 1 vs 5-year average), 100% Nifty when cheap, else 60/40.",
    "2009-2026 15.3%/yr, worst -26% vs Nifty 14.1% / -38%; after tax 12.2% vs 13.3% (switching taxed yearly).", "Better for tax-free money; maybe later.", "data/three_markets.json", "scripts/three_markets.py", "three-markets.yml", script("scripts/three_markets.py"), G)
add("in_intraday", "India intraday (60-day test)", "India", "DROPPED", "2026-11-19", "Intraday rules on NSE 5-minute data.", "No edge.", "Dropped.", "data/india_intraday.json", "scripts/india_intraday.py", "india-intraday.yml", script("scripts/india_intraday.py"), G)
# ----------------------------------------------------------------------- writer
def body(e):
    st = ST[e["status"]]
    hdr = f'''"""{e["title"]}
Market: {e["market"]} | Status: {st} | First tested: {e["date"]} | Group: {e["group"]}

RULES
{textwrap.fill(e["rules"], 140)}

RESULT
{textwrap.fill(e["result"], 140)}

VERDICT
{e["verdict"]}

WHERE
  data:     {e["data"] or "-"}
  script:   {e["script"] or "-"}
  workflow: {(".github/workflows/" + e["workflow"]) if e["workflow"] else "-"}

RE-RUN
  python ideas/{e["file"]}.py        (US/India engines need the price data from R2; easiest is the GitHub workflow above)
Generated by scripts/build_ideas.py - edit the entry there, not this file.
"""
'''
    idea = {k: e[k] for k in ("file", "title", "market", "status", "date", "rules", "result", "verdict", "data", "script", "workflow", "group")}
    r = e["run"]
    if r is None:
        code = 'def run():\n    print("No standalone re-run for this idea; see WHERE above (data file and script).")\n'
    elif r["kind"] == "sim":
        code = ("SETTINGS = " + repr(r["kw"]) + "\n\ndef run():\n"
                "    import os, sys\n    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))\n"
                "    import stack_and_rebound as S\n    curve, trades = S.sim(**SETTINGS)\n    out = S.summ(curve, trades)\n"
                "    for k, v in out.items(): print(f'{k:28s} {v}')\n    return out\n")
    else:
        code = (f"COMMAND = {r['path']!r}\nENV = {r['env']!r}\nARGS = {r['args']!r}\n\ndef run():\n"
                "    import os, subprocess, sys\n    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')\n"
                "    if COMMAND.endswith('.mjs'): cmd = ['node', COMMAND] + ARGS.split()\n    else: cmd = [sys.executable, '-u', COMMAND] + ARGS.split()\n"
                "    return subprocess.call(cmd, cwd=root, env={**os.environ, **ENV})\n")
    return hdr + "IDEA = " + pprint.pformat(idea, width=150, sort_dicts=False) + "\n\n" + code + "\nif __name__ == '__main__':\n    run()\n"
def main():
    os.makedirs("ideas", exist_ok=True)
    for f in os.listdir("ideas"):
        if f.endswith(".py") and f != "__init__.py": os.remove(os.path.join("ideas", f))
    names = [e["file"] for e in C]; assert len(names) == len(set(names)), "duplicate file names"
    for e in C: open(f"ideas/{e['file']}.py", "w").write(body(e))
    json.dump([{k: e[k] for k in e if k != "run"} for e in C], open("ideas/catalog.json", "w"), indent=1, ensure_ascii=False)
    order = ["LIVE", "NEXT", "KEEP", "WATCH", "TESTING", "TOOL", "REF", "MERGED", "DROPPED"]
    md = ["# Ideas catalogue", "", "Every strategy idea or tweak we tested, one file each. Built by `scripts/build_ideas.py` (add an entry there, then run it).", "",
          "File names: `<market>_<strategy>_<tweak>.py` (us = US, in = India, gl = global / crypto / currency). Each file has the rules, result, verdict, where the data and script live, and a `run()` that re-runs it with the shared engine.", "",
          "## Where everything lives", "",
          "| Folder | What's in it |", "| --- | --- |",
          "| `ideas/` | This catalogue: one file per idea or tweak (generated by `scripts/build_ideas.py`) |",
          "| `live/` | The live Robinhood bot (runs on the Oracle VM). Nothing else touches it. Guide: `live/README.md` |",
          "| `scripts/` | Shared engines (`stack_and_rebound.py` = US S&P 500 backtests, `india_pit.py` = India NSE backtests, `intraday_exits.py` = 5-minute replays), paper bots (`paper-*.mjs`, `paper_india_*.py`) and one script per test |",
          "| `data/` | Every test result (JSON) and paper-bot state file |",
          "| `.github/workflows/` | One workflow per test or bot (Actions tab -> Run workflow) |",
          "| `site/` | The Sentinel dashboard (Cloudflare Worker; deploys on every push) |",
          "| `docs/HANDOFF.md` | Running notes: every result in date order, pending items |",
          "| `test-*.py` | Checks (`python test-ideas.py` checks this catalogue) |", "",
          "| Status | Count |", "| --- | --- |"] + [f"| {ST[s]} | {sum(e['status'] == s for e in C)} |" for s in order if any(e['status'] == s for e in C)] + [""]
    for g in dict.fromkeys(e["group"] for e in C):
        md += [f"## {g}", "", "| Status | Idea | Result | File |", "| --- | --- | --- | --- |"]
        for e in sorted([e for e in C if e["group"] == g], key=lambda e: order.index(e["status"])):
            res = e["result"].replace("|", "/")
            md.append(f"| {ST[e['status']]} | {e['title']} | {res[:180]}{'...' if len(res) > 180 else ''} | [{e['file']}.py]({e['file']}.py) |")
        md.append("")
    open("ideas/README.md", "w").write("\n".join(md))
    print(f"wrote {len(C)} idea files + ideas/README.md + ideas/catalog.json")
if __name__ == "__main__": main()
