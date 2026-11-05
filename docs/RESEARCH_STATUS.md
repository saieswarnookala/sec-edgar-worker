# Sentinel research status (updated 2026-11-05)

Research only. Not financial advice. Full record: `docs/RESEARCH_LOG.md`.

## What has held up
- **Clear leader v2.0 (ETFs)**: Jun 2008 -> Sep 2026: 14.6%/yr, max DD -43.2% ($10k -> $120,855) vs SPY $83,102.
- **50/50 Clear leader + gold**: 11.9%/yr, DD -23.5%. **70/30 SPY + gold yearly**: 11.5%/yr, DD -29.8%.
- **India (Nifty + GOLDBEES 70/30 yearly)**: 10.9%/yr, DD -17.3%.

## Being tested live
- **Earnings drift paper trading** (since 2026-11-05, automatic): buy S&P 500 stocks that beat SPY by >= 5% on earnings day, hold 60 trading days, 10 slots. Backtest (point-in-time S&P 500) 21.7%/yr vs SPY 15.1%, BUT the same rules on S&P 400 mid-caps made 12.7% vs 14.9% -> unproven. Log: `data/paper_drift_state.json`.

## Rejected (lost to SPY after costs)
Clear leader on single stocks; 100 Baggers factor ETFs; turn-of-month; RSI(2) quality dips; ORB (all ~3,500 versions incl. gappers: 0 of 2,304 neighbours beat SPY in every period, loses with 5c slippage).

## Next
1. Let paper trading run 3-6 months; compare to SPY monthly.
2. Optional: survivor-free data (Norgate ~$30/mo) to test earnings drift 2005-2015.
3. Add paper-trade Slack alerts once `SLACK_WEBHOOK_URL` exists.

## Housekeeping
- Revoke the GitHub token shared in chat (github.com/settings/tokens). Repo is now public.
- Add `SLACK_WEBHOOK_URL` repo secret; rotate old webhook.
- Check github.com/settings/billing for any Actions charge.
- Backlog: Discord call-tracker, walkforward.py, `.zshr` cron typo, trading log xlsx, repo cleanup, bump action versions (Node 20 warning), India alerts.
