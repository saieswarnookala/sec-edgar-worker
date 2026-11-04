# Sentinel research log - full record (through 2026-11-04)

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
