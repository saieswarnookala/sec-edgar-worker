# Sentinel trading project: full handoff (as of Nov 14, 2026)

Read this first in any new chat. It holds the decisions, numbers and reasons from ~5 weeks of chats (Oct 6 to Nov 12, 2026).
Details live in this repo (scripts/, data/, live/), the doc and the dashboard. Not financial or tax advice.

- Owner: Sai, Dallas/Farmers Branch TX (no state income tax). Wants short, casual, example-driven answers; often uses voice.
- Repo: github.com/saieswarnookala/sec-edgar-worker (PUBLIC: never commit tokens, account numbers, IPs or keys).
- Dashboard: https://sentinel-web.saiesh-dev.workers.dev (site/dashboard/page.html; `node site/test.mjs` must pass 18 tests; "Deploy website" workflow deploys on push).
- Results doc: https://claude.ai/artifact/5NywFGd5djz8cSM3gJHg3m ("Buy the Dip in Strong Stocks: Backtest Results").
- GitHub access: Sai gives a token when needed. The old full-access token was pasted in chat and must be revoked; use a fine-grained, repo-only, short-expiry token.

## 1. History in one screen

| Dates | What happened | Outcome |
| --- | --- | --- |
| Oct 6–10 | "Ledger scan" same-day trading on a $200 Robinhood cash account (VWAP, ATR, relative volume); live AMPX and IBRX trades | Both lost; ~95 day-trading variants backtested, all rejected |
| Oct 13–24 | ORCU "red day" dip rule, factor ETFs, turn-of-month, first short-side tests, Stock Checkup + Sentinel Screener dashboards | No edge; screener kept |
| Nov 3–4 | RSI(2) dip v2.0, Top-3 momentum v2.0, Clear Leader v2.0 (124,416-combo grid); India Nifty + gold ETF mix | Clear Leader kept for parking; India ETF mix kept |
| Nov 6–8 | ORB "stocks in play" (576 + 2,304 combos), earnings drift (blend of 9, out-of-sample 2004–2015) | ORB rejected; drift kept, paper traded |
| Nov 9–10 | "Buy the dip in strong stocks" built: smart exit, Clear Leader parking, crash exit, volume filter | Main strategy; paper traded |
| Nov 10–11 | Intraday (SPY momentum, half-hour, ORB 1-min), dip filters, after-tax US + India, India dip strategy, dip + drift mix | Intraday dropped; volume filter adopted; 6+4 mix recommended |
| Nov 11–12 | Cloudflare timer for paper bots; Robinhood live bot on Oracle VM; future leaders; short selling; options | Live bot in dry run; shorts and options rejected |

## 2. Strategies we use or plan to use

All "realistic" = trading costs included; after tax = federal 24% short-term / 15% long-term, Texas.

| Strategy | Before tax | After tax | Worst drop | Status |
| --- | --- | --- | --- | --- |
| **US dip + volume filter + Clear Leader parking** (1998–2026) | 14.9% (ideal fills 22.0%) | 11.9% (ideal 17.6%) | −25 to −28% | Paper bot ($10k) + live Robinhood dry run |
| **Dip + drift 6+4 mix**, one account (2004–2026) | 15.8% (ideal 19.1%) | 12.3% | −24% | Recommended, not built |
| Earnings drift, blend of 9 | ~13% | ~10% (est.) | −51% | Paper bot ($100k) |
| Clear Leader v2.0 | 13.6% | untested | −43% | Used only to choose where idle dip money parks |
| India dip + Nifty trend, balanced (50% liquid fund + 50% gold when gold > 100d) | 15.0% | ~12% | −19% | Not traded; needs NRI/PIS/US-tax advice |
| India: Nifty + gold ETFs (70/30 NIFTYBEES/GOLDBEES) | see dashboard | | | Reference |
| Benchmarks: SPY | 9.2% | 8.4% | −55% | |
| Nifty 50 | 9.2% (with dividends) | 8.2% | −60% | |

### Dip strategy rules (the main one)
- Universe: point-in-time S&P 500 members. Signal at ~3:45 pm ET.
- Buy: stock above its 200-day average AND fell ≥ 10% more than SPY over 5 days AND its 5-day volume is NOT more than 2× its 50-day normal (heavy-volume dips returned only ~8.9%/yr). Biggest dips first, up to 10 slots, ~10% each.
- Sell (smart exit): first close above the 5-day average, or after 5 trading days at most. No stop-loss (stops hurt).
- Idle money: parked in the Clear Leader ETF when SPY is above its 100-day average, else cash. This is the crash defense: dot-com +8.7%, 2008 +1.5%, 2020 −6.8%, 2022 +4.6% vs SPY −47/−55/−34/−25%.
- Fewer slots hurt (3 slots 7.8%/−57%, 10 slots best). ~14 dip buys a month on average.
- Robust: 54 nearby versions and volume filter at 1.75/2/2.5× and dip 8/10/12% all similar.

### Earnings drift rules
- Stock beat SPY by ≥ 4–6% on its earnings reaction day (SEC 8-K item 2.02 time decides same or next day); buy next open, hold 60 trading days, sell at the open; parking in SPY.

### 6+4 mix
- One account, 6 dip slots + 4 drift slots (caps matter: without caps drift crowds out dip and returns fall to ~11%). 45 nearby versions all beat SPY. ~80 dip + 15–20 drift trades/yr, ~half invested on average.

## 3. Tested and dropped (do not redo without a new idea)

| Idea | Result | Why dropped |
| --- | --- | --- |
| Day trading / intraday (ORB 5-min and 1-min, half-hour, SPY "noise area" momentum, Ledger scan rules) | ORB ≈ −8%/yr even at zero cost; SPY momentum 5%/yr, ~0% after May 2024 | Tiny edges wiped out by costs |
| RSI(2) dip, Top-3 momentum, SPY 10-month average | Below the dip strategy | Kept on Tested tab only |
| Dip filters: skip earnings, industry cap, stop-loss | No gain or worse | Only the volume filter kept |
| Future leaders ("let winners run" momentum) | Hindsight best 18.3% but settings picked on 1998–2011 made 12.8% in 2012–26 vs SPY 14.7% | Failed unseen years; a 30% slice next to dip adds ~1%/yr (maybe later) |
| All short selling (mirror dip, mirror drift, SPY short, lottery, volatility, losers, long/short, hedged dip) | −4% to −25%/yr; big crash gains | Market rises most years; short losses compound; edge is in small hard-to-borrow stocks |
| Buying options (calls, protective puts) | −1% to −14%/yr; puts cut returns | Buyers pay the premium |
| Selling options (Cboe PutWrite index, real data 1996–2026) | 8.6%/yr, −37% vs SPY 10.3%, −55% | Less than SPY and far less than dip; Robinhood agent can't trade options |
| Insider buying clusters (SEC Form 4, 2007–2026) | Best 13.3% vs SPY 10.8% but −50 to −63% drops; picked on 2007–15 → 12.3% in 2016–26 vs SPY 14.9% | Failed unseen years |
| Buy on joining S&P 500 / 52-week-high momentum (1998–2026) | Joins 4–8%, 52w high 6–11% vs SPY 9.2% | Below SPY |
| Buy on removal from S&P 500 | Up to 20% but all from 1998–2011; 2012–26 ≤ SPY | Edge is in the past |
| ATR swing: buy with a direction filter, sell at k×ATR(14) target, 1–3 day hold (Nov 12, 384 versions, data/atr_swing3.json) | Trend/momentum/down-day filters: lose (0 of 96 momentum versions positive). An earlier 134%/yr result was a daily-bar artifact (limit fill + same-day target); fixed in v3. Dip signal + ATR exit: 11–15%/yr but −47 to −54% drops | Edge comes from the dip signal, not the ATR exit; no better than the current dip rules |

Files: data/intraday_*.json, data/dip_filter_*.json, data/future_leaders*.json, data/short_side.json, data/short_research.json, data/options_research.json, data/india_*.json, data/dip_slots.json, data/dip_curve.csv (daily equity of the live dip strategy).

### Net buybacks (Nov 12): real signal, but lumpy; not traded
- Rule: monthly, top 10 S&P 500 stocks whose share count fell most over the past year (SEC cover-page shares, split-adjusted, 2011–2026), hold >= 63 days: 17.8%/yr vs SPY 13.9%, worst drop −43% vs −34%.
- Robustness (data/new_ideas_buyback2.json): smooth across 3–40 stocks (fewer = more return and bigger drops; 30–40 stocks ~ SPY); rebalance day and 10–60 day filing lag barely matter; beats 99% of 200 random 10-shrinker portfolios (random shrinkers median 13.1% < SPY).
- But: WDC alone added ~30 pts of excess; without the top 5 contributors 13.8% (= SPY). Beat SPY only 8 of 16 years; 2019–24 ~12.7%/yr vs SPY ~17.3%; the 2019–26 edge is mostly 2025–26 (+57%, +54%).
- Verdict: not a replacement for the dip strategy. Maybe later: a small sleeve beside dip, tested as a combo. Doc: docs/BUYBACKS.md; dashboard: Day trading → Buybacks.

### Nov 14 research (Sat)
- **ATR on 1-minute bars** (data/atr_minute.json, scripts/atr_minute.py, Alpaca SIP 2016-26): the old 134%/yr was fake. Real fill-then-target order: momentum and down-day setups lose on every target/hold (win ~50%, −0.1% per trade before costs). Dip signal + limit 0.5 ATR below close + 1–1.5 ATR target, 2–3 day hold: +0.6–0.9% per trade but only 31% of orders fill (~90 trades/yr) — weaker than the live dip rules. Dropped. (Coverage: 1,353 missing and 5,899 open-price mismatches skipped.)
- **Event filters on the live dip strategy** (data/dip_filter_ev_*.json, workflow dip-events.yml, SEC 8-K items cache scripts/sec_8k_items.py): skipping earnings (before/during hold), any 8-K company news, one-day shocks, gaps, Fed days, jobs-report eve, witching, Fridays, month-end — all inside the random-skip range (14.4–15.6% vs 14.9%). Skipping dips in a jumpy market HURTS (12.1%). None adopted.
- **Market volatility** (data/dip_filter_ev_vol.json): buying dips mainly when SPY is jumpy helps a little and broadly — skip-calm 10 of 12 versions ≥ baseline (best 16.4%, −20%); vol-scaled size all 4 versions better (0.5x calm → 1.5x jumpy: 16.1%, −25%). Gain ~+0.5–1.5%/yr, much of it 2008–09. Candidate for the paper dip bot (not built).

### Screener rebuilt: "Quality at a fair price" (Nov 14)
- Gate: profitable 2 yrs; sales 3Y CAGR >= 5% and 1Y >= 0; ROE >= 12%; FCF > 0; OCF >= 0.8 x net income; debt <= equity; P/E <= 40. Rank = half quality (ROE, net margin, FCF margin) + half value (earnings yield, FCF yield), percentiles within size bucket; top 15 per bucket. scripts/build-screen.mjs (QUALITY); old high-P/E list kept as rows_high_pe.
- Backtest (scripts/screener_backtest.py, data/screener_backtest*.json; S&P 500 point-in-time, pick each May, hold 12 months, 2013-2026): 15.8%/yr (15.8 / 15.9 halves) vs SPY 14.0%, equal-weight 12.8%, old high-P/E 11.2% (7.8% after 2019). Momentum (11.9%) and 200-day trend filter (10.5%) hurt. 9 of 11 nearby versions beat SPY; no debt limit tested 19.2% but kept the debt rule on purpose.
- Small/mid/micro test running: scripts/smallcap_backtest.py (weekly Alpaca bars + SEC, survivorship warning) -> data/smallcap_backtest.json; then rerun scripts/make_screener_report.py to add it to the PDF.
- Screener tab: summary card + backtest table on top, PDF download (site/static-data/screener_rules_report.pdf, built by scripts/make_screener_report.py).
- Refresh: Cloudflare cron '45 21,23 * * *' dispatches screen.yml daily (GitHub schedule ran 4-6 h late). Cloudflare free plan: 4 of 5 cron triggers used.
- Discussion brief for Sai's friend: https://claude.ai/artifact/7xSY9Xtx9YuszTaBYVEfUi

### Rhythm and volatile-bounce research (Nov 14) - nothing new to trade
- Single-stock rhythm test (scripts/single_stock_rhythm.py, workflow rhythm-test.yml, data/rhythm_<sym>.json): ~800 intraday/1-3 day rules per stock incl. research ideas (same half-hour persistence HKS 2010, first->last half-hour Gao et al. 2018, yesterday's last 30 min). ORCL, NVDA, TSLA, AMD, PLTR, COIN: intraday rhythms did not survive 2023-26; only "buy after a 3%+ down day, hold 1 day" stayed positive vs a random day on 5 of 6 stocks (~+0.3-0.4%/trade).
- Volatile bounce (scripts/volatile_bounce.py, workflow volatile-bounce.yml, data/volatile_bounce_{sp500,popular}.json): ~10k scenarios on point-in-time S&P 500 (2004-26) + 45 popular names (2016-26, hindsight-biased). Filters help a little (quiet volume, 200-day uptrend, skip earnings drops, 3-day/smart exit ~+0.1%/trade each) = same as the dip bot. Picking the best version on train didn't predict test (rank corr ~0). 1%/trade versions trade too rarely; none beat SPY as a strategy on the unbiased list. Popular-list "gap down 7%+, hold 2 days" looked great but is ~0 on the S&P list -> hindsight. Conclusion: keep the dip bot; no new bot.
- Pattern matching / lookalikes (scripts/pattern_match.py, workflow pattern-match.yml, data/pattern_match.json): nearest-neighbor on the last 10/20/40 daily moves, own-stock or pooled history, 26 stocks incl. losers, 2017-22 pick / 2023-26 check. Detector validated on random (finds nothing) and planted data (finds it). Real data: 0 of 324 pooled versions beat luck even on train; per stock 0-2 vs ~7 expected by luck; direction calls no better than guessing 'up'. Dead end.
- Candles (Nov 14-15): scripts/candles.py, data/candles.json (PIT S&P 500 1999-2026): classic patterns ~0 after costs (only 'inside day', ~1 bp). Dip-bot trades that CLOSED AT THE LOW bounced more (+1.54%/trade vs +0.71% for dips with a lower tail; both halves), but as a bot filter only 17.4% vs 17.1%/yr with a deeper worst drop -> not adopted. Month-end timing (scripts/month_end.py, data/month_end.json, SPY/QQQ/IWM 1993-2026): turn-of-month window still a bit better in 2016-26 (SPY 8.9 vs 4.6 bps/day, t~1, not significant) and gone since Jun 2024 (T+1); deposit day (-4 vs +1 vs +4) makes no difference (16.2 vs 16.2%/12m); pension-rebalancing signal inconsistent (worked 1993-2008 and 2016-26, reversed 2009-15). Not adopted. 52-week-high & same-month seasonality tilts (scripts/tilts_52w.py, data/tilts_52w.json, PIT S&P 500): both LOST to equal weight in 1999-2016 and 2017-26 (52w-high top 10%: -0.47%/month). Dead for large caps. But dip-bot signals 20%+ below the 52w high bounced more (+1.5-2.3%/trade) than dips near the high (+0.5-1.0%) in both halves: possible ranking tweak, untested in the full bot. Per-stock candles (daily/30-min/15-min) in the rhythm test: 0 of ~420 versions survived 2023-26 on ORCL/NVDA/TSLA/AMD/PLTR/COIN.
- More-trades research (Nov 14): (a) ETF dip sleeve (scripts/etf_dips.py, data/etf_dips.json; 29 index/sector/country ETFs, Yahoo 1999-2026): '5-day drop >= 5%, above 200-day, buy at close, sell back above 5-day avg (max 5-10 days)' on all ETFs = ~3 trades/mo, 73% win, +0.84%/trade (+0.37% vs SPY same days); with idle money in SPY ~+1.3%/yr over SPY in BOTH halves (1999-2012 4.7 vs 2.9; 2013-26 15.5 vs 14.5); sleeve alone worst drop -7%. RSI(2) on ETFs ~0 vs SPY (decayed). Candidate add-on to the dip bot (paper first). (b) Industry-relative dips (volatile_bounce sp500, triggers '... vs industry', SIC2 leave-one-out): not better than the dip bot's own 10%/5-day trigger, which held up best (2016-26 ~21%/yr with SPY parking vs SPY 14.9%).
- Combined test (scripts/combined_dip_etf.py, data/combined_dip_etf.json; live dip rules on PIT S&P 500 + ETF rule sharing 10 slots, buy at close, SPY parking with 100-day crash rule, 1999-2026): today's bot 14.9%/yr, worst -26.7%; + ETF 5-day 5% dips filling free slots (hold <= 10 days) 17.1%/yr, worst -22.4%; better in both halves (12.1->14.6, 17.6->19.5) and with stress costs (12.3->14.4). All ETF variants B-E helped (+1.9 to +2.2/yr). Next: add ETF sleeve to the paper bot, paper-trade before Robinhood.

## 4. Data and research setup
- Survivorship-free S&P 500: release snapshot-2026-11 of github.com/Johnbrick123/sp500-data (prices.parquet incl. delisted, membership_intervals.parquet). Cached in workflows.
- SEC 8-K 2.02 earnings times + SIC: scripts/sec_events_sic.py → data/sec_events_sic.json.
- Yahoo chart API works from GitHub Actions only (not from Claude's sandbox). Alpaca free plan: SIP data up to 15 min old.
- Main backtest scripts: scripts/dip_filters.py (modes earnings/volume/sector/peer/stop/combo/tax/both/both2/curve; workflow dip-filters.yml), scripts/india_dip.py (india-dip.yml), scripts/future_leaders*.py, scripts/short_side.py, scripts/short_research.py, scripts/options_research.py (options-research.yml), intraday_*.py.
- Honest-testing habits used: realistic vs ideal fills, after-tax, robustness grids, random-picks "luck" test, unseen-years (out-of-sample) check, point-in-time universe.

### Before launching any new test or bot (Sai's rule, Nov 14)
1. Dry run on fake data first: random prices must show no edge; a planted pattern must be found.
2. Check every ticker returns data before the full run (bad tickers skipped and listed, never a crash).
3. Smoke run on real data (1 ticker or a short window) before the full GitHub Actions job.
4. Known traps: Alpaca free plan rejects SIP data newer than ~15 min (end date >= 1 day back, full timestamp); Alpaca rejects a whole 100-symbol batch if one ticker is unknown (filter to /v2/assets, split on 4xx); SEC submissions fields are lists (index them); new workflows can 404 for a few seconds after push.

## 5. Paper bots (Alpaca paper, GitHub Actions)
- Dip bot $10k: scripts/paper-dip.mjs, workflow paper-dip.yml, state data/paper_dip_state.json. Market "day" orders 3:00–3:57 pm ET (paper MOC orders never filled). Syncs with broker positions each run. Tests: `node test-paper-dip.mjs`.
- Drift bot $100k: scripts/paper-drift.mjs (pre-market "day" orders; "opg" orders expired on paper).
- GitHub's own schedule was hours late, so a Cloudflare cron in site/src/index.js (TIMERS) dispatches the workflows: drift 11:05 + 12:35 UTC, dip 25 and 40 past 19/20 UTC (= 3:25 / 3:40 pm ET). Bots run at most once a day. Needs repo secret GH_DISPATCH_TOKEN.
- Known gap: the paper dip bot skips 1 pm half days.

### Volatility-sized dip bot (virtual, from Nov 16) + Paper bots tab (Nov 14)
- Runs inside the paper dip run (no broker): same signals/exits, slot = 10% × (0.5 calm … 1.5 jumpy) from SPY 20d volatility rank vs past year. State: data/paper_dip_vol_state.json ($10k virtual, fractional, fills at the ~3:45 pm price). Tests in test-paper-dip.mjs.
- Dashboard tab "Paper bots" (#paper): rules, example, backtest, live status vs SPY, holdings for dip / vol / drift bots + Robinhood bot notes; data/paper_status.json is built in site/build.mjs on every deploy (bot commits to data/** redeploy).
- /api/timers (signed in) and the tab's health badges show the last Cloudflare timer start per bot (status + error).
- PROBLEM found Nov 14: no timer dispatches since ~Nov 12 midday (dip bot missed Nov 12 + 13; drift ran only on GitHub's late schedule). Most likely GH_DISPATCH_TOKEN was revoked/expired. Fix: new fine-grained token (this repo, Actions read+write), set repo secret GH_DISPATCH_TOKEN, re-run "Deploy website"; then check the Paper bots tab badges.

## 6. Live bot: Robinhood (live/, guide live/README.md)
- Account: Robinhood agentic (MCP) account, LIMITED MARGIN (so sale proceeds are usable the same day), opened Nov 11–12, ~$10 in it. Plan $1,000.
- Runs on an Oracle Cloud Always Free VM (VM.Standard.A1.Flex, 1 OCPU, 6 GB, Ubuntu 24.04, Chicago, user `ubuntu`, Sai's SSH key). Account upgraded to pay-as-you-go; $1 budget alert set.
- Plain code decides and places every order via Robinhood's official MCP (https://agent.robinhood.com/mcp/trading). Fallback EXECUTOR=claude routes calls through Claude Code with each call checked.
- Config ~/.sentinel-live/config.env (LIVE_MODE dry|live, RH_ACCOUNT, Alpaca data keys from a separate paper account, NTFY_TOPIC, MAX_DRAWDOWN 0.35). The code parses it itself (systemd kept inline comments in values).
- Timers (New York time): health 8:45 am (alert only on problems); trade 3:47 pm + 3:52 backup (12:47/12:52 on 1 pm half days, from the market calendar's real close), last order by close −1.25 min; verify 4:35 pm (fills vs close, unfilled, stranger orders; live only).
- Safety: sells first, buys sized to real buying power; max $ per order (20% of account); strategy stocks only; never sells more than held; ≤ 25 orders; one run at a time; once a day; stable ref_id per order per day; halts on unknown orders, failed safety checks or −35% from peak; never opens login pages unattended (alerts instead). Amounts sent as strings ("99.99"), rounded down; gfd, regular_hours.
- Alerts (ntfy): dry plan = low/silent; live trades and fills = normal; failures = high; login expired / halted / unknown orders = urgent.
- VM shortcut: `dip status|health|doctor|login|halt|resume` (alias in ~/.bashrc). Update: `cd ~/sec-edgar-worker && git pull`. Re-run setup safely: `curl -fsSL https://raw.githubusercontent.com/saieswarnookala/sec-edgar-worker/main/live/setup-vm.sh | bash`. Login needs an SSH tunnel: `ssh -L 8765:localhost:8765 ubuntu@<vm-ip>` then `dip login`.
- Tests: `cd live && node test-live.mjs` (13 unit tests + dry/live/expired-login/Claude-mode runs on a fake broker).
- Lessons from other builders that shaped it: bots silently not running, cash stuck in settlement (cash accounts), login expiring mid-day (one bot opened 67 tabs), AI sizing bugs, double orders, trusting "success" replies.
- Robinhood login first done Nov 12 (valid ~158 h, so ~Nov 18); automatic refresh not yet proven.
- Rollout: 1) dry week (now) → 2) live, $1,000, Robinhood trade approvals ON for a week → 3) hands-off.

## 7. Pending
1. Review daily dry-run alerts vs the paper dip bot.
2. ~Nov 17: confirm the Robinhood token refreshed itself (`dip status` shows token hours).
3. After a clean dry week: fund $1,000, set LIVE_MODE=live, approvals on.
4. ~~Paper dip bot: handle 1 pm half days.~~ Done Nov 12 (window from calendar close; dip timers now one Cloudflare cron `25,40 16,17,19,20 * * 1-5`, free plan allows 5 triggers).
5. Build the 6+4 dip + drift capped paper bot.
6. India balanced strategy: paper tracking; NRI/PIS/US tax advice first.
7. Maybe later: 30% "future leaders" slice beside the dip strategy.
8. Sai: revoke the old GitHub token AND the classic ghp_ token pasted Nov 12 (all repos, expires Feb 2027); confirm the $100 Oracle card hold was released.
9. Backlog: remove old DIP_KEY_ID/DIP_SECRET_KEY from the claimsure-demo repo; drift bot blend-of-9 switch; bump actions/checkout + setup-node (Node 20 deprecation); SLACK_WEBHOOK_URL; walkforward.py; cron typo.

## 8. Things Sai has asked about (short answers)
- Pattern-day-trader $25k rule: removed June 4, 2026 (phase-in to Oct 2027); our bots rarely day trade.
- Fidelity has no trading API and forbids automation; Schwab, Robinhood (agentic beta, stocks only), Alpaca and IBKR allow bots.
- App idea (selling a bot-builder as a subscription): feasible small-scale, crowded market (Composer, TradersPost, QuantConnect); keep it a tool that runs users' own rules; revisit after a few months of real results.
- "Ideal" fills = trading exactly at the close/open with zero cost; it's a ceiling, not beatable on average.
- Nvidia CEO resignation (Nov 12, 2026): news-driven, heavy-volume dips are skipped by our volume filter.
