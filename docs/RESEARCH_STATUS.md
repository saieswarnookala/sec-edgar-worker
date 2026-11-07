# Research status (updated 2026-11-07)

## What held up
- **Clear leader v2.0 ETF momentum**: 14.6%/yr since Jun 2008, DD -43.2%.
- **50/50 Clear leader + gold**: 11.9%/yr, DD -23.5%. **70/30 SPY + gold** yearly: 11.5%/yr.
- **India 70/30 Nifty + GOLDBEES**: 10.9%/yr, DD -17.3%.
- **Earnings drift (S&P 500)**: signal is real (beats 100% of random-pick runs) but the edge is small. Blend of 9 nearby rules 15.6%/yr vs SPY 14.6% pre-tax; after tax with idle cash in SPY: 16.0% at 12%, 13.9% at 24%, 12.4% at 32% vs SPY 13.3%. Best fit: retirement account (18.1% vs 14.6%). The 21% single-rule result was a lucky peak (1/9 neighbours beat SPY every period).

## Live test
- Alpaca **paper** account, $100k, started 2026-11-05. Rule kept: 5% jump, 60-day hold, 10 slots; idle cash in SPY, market orders before the open, 4 backup morning runs. Judge after 3-6 months; compare with a replay of the blend of 9 on the same prices.

## Rejected
- ORB day trading (3,500+ variants, ~100M bars): none beat SPY after costs.
- Quality dips (RSI-2 + SEC quality): 12.7% vs SPY 15.1%.
- Earnings drift on S&P 400 mid-caps (12.7% vs 14.9%) and India Nifty 100 fair test (10.2% vs 10.4% after tax).
- Crypto funding-rate arbitrage: below T-bills since 2025. Merger-arb funds (MNA/ARB): ~1-2 pts over T-bills.

## Next
- Paper-trade the 5%/60-day rule; compare monthly with SPY and with a blend replay.
- Optional: pre-2016 test with paid survivorship-free data (Norgate ~$30/mo); exact Nifty 100 history from NSE press releases.

## Housekeeping
- Revoke the GitHub PAT pasted in chat (github.com/settings/tokens). Scheduled jobs use repo secrets.
- Check GitHub billing (private repo minutes exhausted); move Coverage Check deploy to its own repo after the reset.
- Bump actions/checkout and setup-node (Node 20 deprecation).

Research only. Not financial advice.
