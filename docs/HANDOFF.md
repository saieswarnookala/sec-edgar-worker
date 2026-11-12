# Sentinel trading project: full handoff (as of Nov 12, 2026)

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

Files: data/intraday_*.json, data/dip_filter_*.json, data/future_leaders*.json, data/short_side.json, data/short_research.json, data/options_research.json, data/india_*.json, data/dip_slots.json, data/dip_curve.csv (daily equity of the live dip strategy).

### Promising, needs more checks: net buybacks (Nov 12)
- Rule: monthly, top 10 S&P 500 stocks whose share count fell most over the past year (SEC cover-page shares, split-adjusted, ~2011–2026), hold ≥ 63 days.
- 17.8%/yr vs SPY 13.9%, worst drop −43% vs −34%; 2011–18 13.1% vs 11.1%, 2019–26 22.7% vs 16.9%. Top 20: 15.2%, top 30 ≈ SPY (edge sits in the most extreme names).
- Next checks before any paper bot: which stocks drive it (concentration), random-picks luck test, after tax, as a sleeve beside the dip strategy. File data/new_ideas_buyback.json (scripts/new_ideas.py, new-ideas.yml).

## 4. Data and research setup
- Survivorship-free S&P 500: release snapshot-2026-11 of github.com/Johnbrick123/sp500-data (prices.parquet incl. delisted, membership_intervals.parquet). Cached in workflows.
- SEC 8-K 2.02 earnings times + SIC: scripts/sec_events_sic.py → data/sec_events_sic.json.
- Yahoo chart API works from GitHub Actions only (not from Claude's sandbox). Alpaca free plan: SIP data up to 15 min old.
- Main backtest scripts: scripts/dip_filters.py (modes earnings/volume/sector/peer/stop/combo/tax/both/both2/curve; workflow dip-filters.yml), scripts/india_dip.py (india-dip.yml), scripts/future_leaders*.py, scripts/short_side.py, scripts/short_research.py, scripts/options_research.py (options-research.yml), intraday_*.py.
- Honest-testing habits used: realistic vs ideal fills, after-tax, robustness grids, random-picks "luck" test, unseen-years (out-of-sample) check, point-in-time universe.

## 5. Paper bots (Alpaca paper, GitHub Actions)
- Dip bot $10k: scripts/paper-dip.mjs, workflow paper-dip.yml, state data/paper_dip_state.json. Market "day" orders 3:00–3:57 pm ET (paper MOC orders never filled). Syncs with broker positions each run. Tests: `node test-paper-dip.mjs`.
- Drift bot $100k: scripts/paper-drift.mjs (pre-market "day" orders; "opg" orders expired on paper).
- GitHub's own schedule was hours late, so a Cloudflare cron in site/src/index.js (TIMERS) dispatches the workflows: drift 11:05 + 12:35 UTC, dip 25 and 40 past 19/20 UTC (= 3:25 / 3:40 pm ET). Bots run at most once a day. Needs repo secret GH_DISPATCH_TOKEN.
- Known gap: the paper dip bot skips 1 pm half days.

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
