# Sentinel research status (updated 2026-11-04)

Research only. Nothing here places orders. Not financial advice.

## What works / current strategies
- **Clear leader v2.0 (ETFs)**: Jun 2008 -> Sep 2026: 14.6%/yr, max DD -43.2% ($10k -> $120,855) vs SPY $83,102. The one strategy that has held up. Next step: paper trade on Alpaca.
- **50/50 Clear leader + gold**: 11.9%/yr, DD -23.5% (smoother).
- **70/30 SPY + gold, yearly rebalance**: 11.5%/yr, DD -29.8%.
- **India (Nifty + GOLDBEES 70/30 yearly)**: 10.9%/yr, DD -17.3% (Oct 2010 -> Sep 2026).

## Tested and rejected (lost to holding SPY)
| Idea | Result | Benchmark |
|---|---|---|
| Clear leader on 10 biggest 2008 stocks | 12.6%/yr, 7/18 picks beat SPY | SPY 12.2%, equal-weight 13.1% |
| 100 Baggers traits via factor ETFs (IWM/IJR/IJS/XSHQ) | 7.7-8.7%/yr | SPY 10.8% |
| Turn-of-month | 8.9%/yr | SPY 14.9% |
| Quality dips, RSI(2) on S&P 500 + SEC quality filter (2016-26) | 12.7%/yr (all stocks 16.9%, survivorship bias) | SPY 15.1% |
| ORB "stocks in play", S&P 500, 5-min opening range, stop 0.1 ATR (2021-26) | worst case -47%/yr, best case +6.9%/yr, win rate 11-15% | SPY 13.1% |

Why ORB failed: stop (0.1 x ATR, ~0.25%) is too tight - normal noise stops ~85% of trades; and S&P 500 large caps are not what the study used (all US stocks, smaller "in play" names).

## Running / next
1. **ORB grid** (workflow `ORB grid`, `.github/workflows/orb-grid.yml`, started 2026-11-04): S&P 500, 2023 -> now, stop 0.25 / 0.5 / 1.0 x ATR x top 5 / 20 picks. Results: `data/orb_s*_t*.json`.
2. **Full ORB research grid** - NOT built yet. Build with Claude Code using the prompt below. Plan: test all combos on 2021-2024 only, check top 2-3 on unseen 2025-2026, then paper trade 1-2 months before real money. Beware: testing many combos makes one look good by luck.
3. Paper trade Clear leader on Alpaca meanwhile.

### Claude Code prompt for the full grid
```
Extend scripts/build-orb.mjs into a full ORB research grid. Research only, no orders.
1. Universe option: besides S&P 500, add "wide" = all active US common stocks from Alpaca /v2/assets
   (tradable, NYSE/NASDAQ/AMEX, exclude ETFs/funds), filtered daily: price > $5, 14-day avg volume > 1M, ATR14 > $0.50.
2. Parameters, each combo reported: OR_MIN 5/15/30; STOP 0.1/0.25/0.5/1.0 x ATR14; TOP 5/20 per day;
   MKT_FILTER off / longs only when SPY up since open, shorts when down; TARGET hold-to-close / 2R / trailing 1R;
   GAP off / only stocks gapping >= 3%; SIDE both / long only.
3. Split: IN-SAMPLE 2021-01-01..2024-12-31, OUT-OF-SAMPLE 2025-01-01..now, reported separately.
4. 1-minute bars for the day's picks; same-minute entry+stop = stopped (conservative).
   Costs $0.0035/share + 1 cent/share slippage each side. Sizing: risk 1% equity, max 4x leverage.
5. Matrix job per universe x year (max-parallel 4, backoff on 429) computing daily returns for all combos,
   then a merge job. Don't commit big per-chunk files; upload as artifacts.
6. Output data/orb_grid_summary.json + printed table: CAGR, max DD, Sharpe, trades, win rate, avg R,
   in-sample vs out-of-sample vs SPY. Rank by in-sample Sharpe; show top 10 with OOS.
7. Test with fake data offline first, then workflow .github/workflows/orb-research.yml (workflow_dispatch). Commit and push.
```

## Housekeeping
- Revoke the GitHub token shared in chat (github.com/settings/tokens).
- Push dashboard v22 to `site/dashboard/page.html` (website still v21).
- Add `SLACK_WEBHOOK_URL` repo secret for Clear leader alerts.
