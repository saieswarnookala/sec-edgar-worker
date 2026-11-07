# Sentinel research log - full record (through 2026-11-05)

Research only. Nothing here places orders. Not financial advice. Short summary: see `docs/RESEARCH_STATUS.md`.

## 0. Links and setup
- Website: https://sentinel-web.saiesh-dev.workers.dev (India tab `#trading-india`, Clear leader `#trading-clv2`)
- Dashboard artifact (Claude): files/index.html v22 (website still serves v21 - push pending)
- Clear leader v2.0 guide (Claude Doc): https://claude.ai/artifact/MopiTwqT24vdvs43vDEhh3
- Repo: saieswarnookala/sec-edgar-worker (private). Data: Alpaca SIP daily/intraday bars, SEC XBRL, AMFI NAVs (mfapi.in), Alpha Vantage.
- Workflows: Build strategies, Build screener, Build India data, Build stock history, Quality dips backtest, ORB backtest, ORB grid, Deploy website.
- Repo work via Claude Code (Claude app Code tab) or GitHub token. Token pasted in chat must be revoked (github.com/settings/tokens); prefer fine-grained tokens.

## 1. Clear leader v2.0 (ETF momentum) - KEEP
- Rotates into the ETF that is clearly leading; defaults to safety when no clear leader.
- Jun 2008 -> Sep 2026: **14.6%/yr**, max DD **-43.2%**, $10,000 -> **$120,855** in 18.3 yrs vs SPY $83,102.
- Ranking-window test (1/3/6/9/12 mo): 12.3% / 13.2% / 11.7% / 10.7% / 14.6% - 12 months best.
- Example in guide: 2021-2023 DBC (commodities) leadership.
- Alerts: Slack preview ~3:05pm ET + final after close, +/- half ATR ranges. Needs `SLACK_WEBHOOK_URL` secret (pending); rotate old webhook.
- Guide doc contains "In short", example, lookback table, alerts section. No India content in that doc (by choice).
- Engine bug fixed (cl_gen.js): DEF/SAFE copied into rows; result unchanged at 14.6%.

## 2. Other US allocation tests (Jun 2008 -> Sep 2026)
| Strategy | Per year | Max DD | $10k became |
|---|---|---|---|
| Clear leader | 14.6% | -43.2% | $120,855 |
| 50/50 Clear leader + gold | 11.9% | -23.5% | $78,447 |
| 70/30 SPY + GLD, yearly rebalance | 11.5% | -29.8% | $73,341 |
| SPY | ~11-12% | ~-50% (2008) | $83,102 |
| Gold | 8.1% | - | - |
- Turn-of-month (last 4 + first 3 days, 2016-2026): 8.9%/yr vs SPY 14.9% -> rejected.

## 3. India research - KEEP 70/30 for India investors
- Clear leader US rules on Indian ETFs (Nifty50, JuniorBees, BankBees, Midcap, GOLDBEES, MON100, 2012-26): 9.2%/yr vs Nifty 11.4%, DD -36.7% -> rejected. CPSEETF variant 15.1% = overfit.
- Literature: Nifty200 Momentum 30 index 18.8% vs 13.6% since 2005 (mostly backtest, weak live since 2020); Nifty/gold dual momentum; sector rotation weak.
- Oct 2010 -> Sep 2026 (15.9 yrs):
| Model | Per year | Max DD | Rs 10k became | Notes |
|---|---|---|---|---|
| **70/30 Nifty + GOLDBEES, yearly** | **10.9%** | **-17.3%** | Rs 52,179 | ex-2025 9.8%, 16 trades |
| 70/30 + trend filter | 9.8% | -11.0% | - | trend 2007-26: 10.8% vs 9.7%, DD -23% vs -55% |
| Dual momentum 12m | 11.2% | - | - | ex-2025 8.0%, 34 trades |
| Nifty buy & hold | 9.4% | -29.4% | Rs 41,746 | |
- Data: `scripts/build-india.mjs`, `.github/workflows/india.yml`, `data/india_monthly.csv`, `india_report.json`. Split fixes via fixSplits(). Fund matches for GOLD/GILT/DEBT poor.
- Website/dashboard tab "India: Nifty + gold": signal card (Sep 30 2026: hold 70/30; next rebalance Dec 31 2026), 4 model chips, results, periods, charts.

## 4. 100 Baggers (Chris Mayer) - lesson, not a strategy
- Traits: small size, high ROIC reinvested, earnings growth + rerating, moat, owner-operators, hold for years.
- ETF proxies Jun 2007 -> Sep 2026: SPY 10.8% ($72,118); IWM 7.9%; IJR 8.7%; IJS 7.9%. IWM beat SPY in only 11/112 rolling 10-yr windows.
- Sep 2017 -> Sep 2026: SPY 14.9%; IWM 8.6%; IJR 8.6%; IJS 8.0%; XSHQ (quality small caps) 7.7%.
- Lesson: traits describe winners after the fact; baskets do not beat SPY.

## 5. Clear leader on single stocks - not worth it
- 10 biggest stocks of mid-2008 (XOM GE MSFT T PG CVX JNJ WMT BAC GOOGL), data `data/stocks_monthly.csv`.
- 12.6%/yr, $87,465, DD -36.3%, 37 switches vs SPY 12.2% ($82,349, DD -41.8%); only 7/18 picks beat SPY; equal-weight all 10, yearly rebalance: 13.1% ($95,742).

## 6. Quality dips (RSI(2) on S&P 500) - rejected
- Rules: current S&P 500 (503), Alpaca SIP daily from 2016; quality = SEC 10-K point-in-time (3 yrs positive income, equity > 0, ROE top 40%, debt/equity below median). Entry close > 200d SMA and RSI(2) < 10, next-open fill; exit close > 5d SMA or 10 days; max 5 positions x 20%; 0.02%/side; idle cash in BIL.
| Oct 2016 -> Nov 2026 | Per year | $10k | Trades | Win |
|---|---|---|---|---|
| Quality only | 12.7% | $33,188 | 3,404 | 66% |
| All S&P 500 | 16.9% | $47,928 | 3,834 | 67% |
| SPY | 15.1% | $41,158 | - | - |
- 2016-20: 19.5 / 23.2 / 16.4. 2021-26: 8.1 / 12.6 / 14.2.
- Caveats: survivorship bias (current members) likely explains "all" edge; 42 of 57 2016 quality picks lacked debt tags.
- Files: `scripts/build-quality-dips.mjs`, `test-quality-dips.mjs`, `data/quality_dips.json`.

## 7. Opening-range breakout (ORB) on "stocks in play" - rejected so far
Idea (Zarattini, Barbon & Aziz 2024): each morning pick top 20 stocks by relative volume of the first 5 minutes; green first bar -> buy above its high, red -> short below its low; stop 0.1 x ATR14; exit at close; risk 1% per trade, max 4x leverage; costs $0.0035/share + slippage.
- v1 (5-min bars): broken test - stop and entry in same 5-min bar counted as stopped -> win rate 7%, -55%/yr. Not real.
- v2 (5-min opening bar + 1-min bars for picks), S&P 500, 2021 -> Nov 2026:
| Version | Per year | Max DD | Win rate | Trades |
|---|---|---|---|---|
| Long+short, worst case | -46.9% | -97.6% | 10.9% | 21,635 |
| Long only, worst case | -30.4% | -88.3% | 11.0% | 12,263 |
| Long+short, best case | +6.9% | -20.2% | 15.0% | 23,716 |
| Long only, best case | +4.5% | -18.4% | 15.1% | 12,297 |
| SPY | +13.1% | -25.4% | - | - |
- Why: stop ~0.25% is inside normal noise (~85% stopped); S&P 500 giants are efficient (study used all US stocks).
- Running: `ORB grid` workflow, 2023 -> now, stop 0.25/0.5/1.0 x ATR x top 5/20 -> `data/orb_s*_t*.json`.
- Next: full grid (see RESEARCH_STATUS.md prompt): wide universe, 5/15/30-min range, market filter, 2R target / trailing stop, 3% gap filter, long vs both; in-sample 2021-24, out-of-sample 2025-26; then paper trade.
- Warning: testing many combos makes one look good by luck - trust only what also wins out-of-sample.

## 8. Overall conclusions so far
- Short-term stock trading ideas tested (turn-of-month, RSI(2) dips, ORB) have not beaten holding SPY after costs.
- What has held up: Clear leader (ETFs) and simple stock/gold mixes.
- Plan: finish ORB grid -> full grid with out-of-sample check -> paper trade any survivor 1-2 months -> only then real money. Meanwhile paper trade Clear leader on Alpaca.

## 9. Pending / housekeeping
1. Revoke GitHub token pasted in chat.
2. Push dashboard v22 to `site/dashboard/page.html`.
3. Add `SLACK_WEBHOOK_URL` secret; test alert; rotate old webhook.
4. Optional: India alerts (trend flip + yearly rebalance); 50/50 Clear leader + gold on dashboard; 100-bagger watchlist screen.
5. Financial Datasets credits $0; regenerate FMP_API_KEY.
6. Backlog: Discord call-tracker; walkforward.py; `.zshr` -> `.zshrc` cron typo; Saiesh_Trading_Log.xlsx; repo cleanup; bump actions/checkout + setup-node (Node 20 deprecation).

## 10. ORB research grid (2021 -> Nov 2026) - workflow `ORB research grid`
- 576 combos x 2 universes (S&P 500, "wide" = all active US common stocks passing price/volume/ATR filters) = 1,152 combos, ~60-70M bars (estimate).
- Opening range 5/15/30 min; stop 0.1/0.25/0.5/1.0 x ATR; top 5/20; SPY-direction filter; target close/2R/trail 1R; 3% gap filter; long vs both. In-sample 2021-24, out-of-sample 2025-26.
- S&P 500: no combo beat SPY.
- Wide: best robust pattern = gappers (|gap| >= 3%), top 5, long only, 5-min range, stop 1x ATR, 2R target: 14.2%/yr IS vs SPY 12.3%; 22.7% OOS vs 15.8% (DD 26.3% IS, 12.5% OOS). Wider stops raised win rate to ~48%; shorting hurt OOS.
- Results: `data/orb_grid_summary.json`. The earlier 6-version `ORB grid` run partly failed (Actions minutes ran out).

## 11. ORB gappers stress test (2017 -> 2026) - REJECTED
- 2,304 neighbour combos (range 5/10/15, stop 0.5-1.5 ATR, top 3/5/10, target 1.5/2/3R/close, gap 2-5%, gap-up only vs either, slippage 1c vs 5c).
- Reference on unseen 2017-20: 7.8%/yr vs SPY 13.6%. Full 2017-26: ~13.0% vs SPY ~13.2%.
- 0 of 2,304 combos beat SPY in all three periods. With 5c/share slippage the reference loses money every period (-20% / -14% / -8% a year).
- Conclusion: ORB does not beat holding SPY after realistic costs. Results: `data/orb_gappers_summary.json`.

## 12. Earnings drift (post-earnings-announcement drift) - UNPROVEN
Rules: SEC 8-K Item 2.02 earnings releases; reaction day = stock return minus SPY; buy next open if reaction >= threshold; equal slots; sell after N trading days; 0.05%/side.
- Current S&P 500 members only (biased): best ~31%/yr (8% jump, 60 days, 10 stocks) vs SPY 15.1%.
- Point-in-time S&P 500 (membership rebuilt from Wikipedia changes; 177 of 226 removed companies included; missing = mostly failed banks / no SEC 8-Ks):
| Version (2016-26) | Per year | Max DD | 2016-20 | 2021-24 | 2025-26 |
|---|---|---|---|---|---|
| 8% jump, 60 days, 10 stocks | 13.6% | -42% | 20.7 | 3.7 | 19.4 |
| **5% jump, 60 days, 10 stocks** | **21.7%** | -32% | 25.0 | 17.2 | 23.9 |
| 3% jump, 60 days, 10 stocks | 18.3% | -37% | 20.4 | 15.8 | 19.0 |
| SPY | 15.1% | -34% | 15.8 | 13.5 | 17.0 |
- Only 2 of 64 combos beat SPY every period; half the profit from ~10 trades.
- **S&P 400 mid-caps, point-in-time (405 of 510 removed included): same rules 12.7%/yr, DD -50% vs SPY 14.9%; 0 of 64 combos beat SPY over the full period.** Weakens the S&P 500 result - likely partly luck.
- Older years: Alpaca SIP starts 2016; Alpha Vantage free key = 25 requests/day and lacks delisted names (e.g. LEH). Survivor-free option: Norgate Data (~$30/month).
- Files: `scripts/earnings-drift.mjs`, `scripts/earnings-drift-pit.mjs`, `data/earnings_drift*.json`.

## 13. Paper trading (started 2026-11-05)
- Workflow `Paper trade earnings drift` (`.github/workflows/paper-drift.yml`), weekdays 13:20 UTC, market-on-open orders, Alpaca PAPER endpoint hard-coded. Rules: 5% jump, hold 60 trading days, 10 slots of 1/10 equity. State/log: `data/paper_drift_state.json`.
- First buys 2026-11-05 ($100k paper): MOS 462, XYZ 114, JKHY 55, BKNG 58, APO 81, HSIC 113.
- Plan: run 3-6 months as a free live test; treat as an experiment given the mid-cap result.

## 14. Infrastructure changes (2026-11-05)
- GitHub Actions free minutes ran out (private repo) -> repo made **public** (history scanned for secrets first; none found). Anyone can now see code, results and the paper-trading log.
- Website dashboard updated to v22 (time span on $10,000 tiles).


## 15. Earnings drift: taxes and idle cash (2026-11-06)
Files: scripts/tax-sim.mjs, scripts/test-tax-sim.mjs (used by earnings-drift-pit.mjs and india-drift.mjs).
Model: realized gains netted per calendar year, taxed at year end, losses carried forward; idle cash optionally parked in the benchmark ETF (its gains taxed at the same rate, conservative); benchmark = buy and hold, taxed once at the end at the long-term rate. Dividend taxes ignored both sides.
US S&P 500 full point-in-time, rule thr5|hold60|n10 (SPY after 15% LT tax = 13.3%/yr):
| Rate | Idle cash | Parked in SPY |
|---|---|---|
| 0% | 21.2% | 22.3% |
| 12% | 18.9% | 19.9% |
| 22% | 16.9% | 17.8% |
| 24% | 16.5% | 17.4% (DD -38.9%) |
| 32% | 14.9% | 15.7% |
Parking adds ~1 pt/yr, deepens worst drop ~2 pts.

## 16. Robustness grid (2026-11-07) — FAILS the neighbour rule
4/5/6% jump x 50/60/70-day hold, 10 slots, S&P 500 full PIT. SPY 14.6% (periods 15.8 / 13.5 / 14.3).
| Jump | 50d | 60d | 70d |
|---|---|---|---|
| 4% | 12.5 | 19.1 | 13.6 |
| 5% | 11.9 | 21.3 | 12.8 |
| 6% | 14.6 | 16.8 | 14.3 |
- Beat SPY every period: 1/9 (thr5 hold60 only). After 24% tax + park: 6/9 beat SPY, 3 of them by 0.1-0.4 pts.
- 2025-26: hold60 21.4%/yr vs hold50 1.3%/yr. ~Half of profit from ~10 trades; hold length changes slot timing (domino effect). Lone peak = luck. Sai's success rule (4% and 6% must also work): not met.

## 17. Blend of 9 + random-picks test (2026-11-07)
Blend (equal money across all 9): 15.6%/yr vs SPY 14.6%, DD -34.5%; periods 19.5 / 13.3 / 11.5 vs 15.8 / 13.5 / 14.3 (not every period).
Blend after tax, parked in SPY: 0% 18.1 | 12% 16.0 | 22% 14.3 | 24% 13.9 | 32% 12.4 (SPY 13.3 after 15% LT; 14.6 untaxed).
Random picks (same signal days/slot counts, stock replaced by random PIT S&P 500 member, seeded): thr5/hold60 21.3% beat 100% of 1,000 runs (median 10.9, p95 15.3); blend 15.6% beat 100% of 200 runs (median 9.5, p95 12.6).
Conclusion: the earnings-jump signal is real (beats chance), but the structure (cash drag, 3-month holds, short-term tax) eats most of it. Net ≈ SPY at 22-24% tax; +2.5 to +3.5 pts/yr at 12% or in a retirement account; behind at 32%.

## 18. India earnings drift (2026-11-06/07)
Files: scripts/nse-probe.mjs, scripts/india-drift.mjs, scripts/test-india-drift.mjs, .github/workflows/india-drift.yml -> data/india_drift.json.
Data: NSE corporates-financial-results (exact broadcast times, to Jan 2025) + corporate-announcements (results filings from Dec 2024) — free, reachable from GitHub Actions; Yahoo daily prices; members from niftyindices.com CSV. Reaction day = same day if filed before 15:30 IST else next session. Costs 0.15%/side. 20% STCG vs 12.5% LTCG on the index. Bad ticks and unadjusted splits removed (NIFTYBEES had one; benchmark fell back to Nifty 50 price index, no dividends).
| Universe | Pre-tax (5%/60/10) | After 20% tax | Parked, after tax |
|---|---|---|---|
| Today's Nifty 100 (biased) | 19.3% | 15.6% | 19.7% |
| Approx PIT (top 100 by traded value each half-year, Nifty 500 + ~75 former names) | 12.6% (DD -32%) | 10.2% | 14.3% (DD -40%) |
| Nifty 50 | 11.4% | 10.4% | — |
PIT beat-every-period: 0/18. Parked version's gain is mostly index exposure (few signals, ~half slots empty). India does not confirm.

## 19. Paper trading fixes (2026-11-06/07)
- 2026-11-05: 6 opg buys submitted 07:52 ET; only BKNG filled, 5 expired (Alpaca paper opg unreliable). 2026-11-06 run started ~15:00 ET (GitHub delay); 9 opg orders rejected.
- Fixes: market 'day' orders; crons 12:05, 12:35, 13:05, 13:20 UTC with once-per-day guard; idle cash parked in SPY (2% cash buffer, skip moves <0.5% of equity).
- 2026-11-07: switched to the blend of 9 (4/5/6% x 50/60/70 days), 10 slots per version, 1/90 of equity per position; BKNG kept as legacy, sold on its 60-day schedule.

## 20. Other notes
- "Day Trader skill" (github.com/Jakeschincariol/day-trader-skill, viral reel): a toolkit, not an edge; its Time Machine resamples the last 60 days of 5-min bars (odds of stop vs target), not a test of whether a setup beats the market. Its own TSLA example was a coin flip. Fine for paper learning only.
