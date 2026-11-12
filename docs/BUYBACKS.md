# Net Buyback Strategy (Nov 2026)

**Rule:** on the first trading day of each month, rank S&P 500 members by how much their share count fell over the past year; buy the top 10 (shrinking only); hold at least 63 trading days, keep a stock while it stays in the top 10. Idle money in SPY.
- Share count: SEC XBRL cover-page shares outstanding (10-K/10-Q, all classes summed), latest filing vs one ~300-430 days earlier, known only from its filing date, split-adjusted; moves beyond ±40% ignored.
- Point-in-time S&P 500 members, buy at next open, 0.15% cost per side, Jan 2011 - Nov 2026 (~16 years; SEC data starts ~2009).
- Proxy for buybacks (share count shrinking), not buyback announcements (no free announcement data).

## Results (per year, before tax)
| | Top 10 | SPY |
|---|---|---|
| 2011-2026 | 17.8% | 13.9% |
| 2011-2018 | 13.1% | 11.1% |
| 2019-2026 | 22.7% | 16.9% |
| 2019-2024 (approx.) | ~12.7% | ~17.3% |
| Worst drop | -43% | -34% |
| Years beating SPY | 8 of 16 | |

## Number of stocks x hold (2011-2026, SPY 13.9%)
| Stocks | 21d | 63d | 126d | Worst drop (63d) |
|---|---|---|---|---|
| 3 | 21.6 | 25.5 | 28.5 | -43% |
| 5 | 18.6 | 18.2 | 21.8 | -55% |
| 7 | 17.9 | 16.5 | 20.3 | -49% |
| 10 | 17.6 | 17.8 | 18.2 | -43% |
| 15 | 15.7 | 15.9 | 16.5 | -43% |
| 20 | 14.6 | 15.2 | 15.2 | -42% |
| 30 | 13.7 | 14.4 | 15.1 | -40% |
| 40 | 14.1 | 14.9 | 15.2 | -43% |

Smooth: fewer stocks = more return and bigger drops; 30-40 stocks ~ SPY. The 1/3/5% minimum-shrink setting made no difference for the top 10.

## Honest checks
- Picked on 2011-2018 (top 20, 63d) -> 17.2% in 2019-2026 vs SPY 16.9%.
- Rebalance day 1/5/10/15 of the month: 16.9-17.8% (top 10).
- Filings assumed 10/30/60 days late: 18.4 / 18.2 / 19.2%.
- Luck test: top 10 beat 99% of 200 random 10-stock portfolios of shrinking companies (median 13.1%, below SPY) and 100% of random S&P picks (median 11.7%).

## Why it is lumpy
- WDC alone added ~30 points of excess return; GME (2020-21 squeeze) was #2. 169 stocks traded.
- Without the top 1 / 3 / 5 / 10 contributors: 15.7 / 14.8 / 13.8 / 11.1% (SPY 13.9%).
- 2025 +57% and 2026 +54% (vs SPY 18% / 11.5%) carry the recent edge; 2019-2024 trailed SPY.

## Verdict
The signal is real (not luck), but gains come in a few big bursts with long dry spells and a bigger worst drop. Not a replacement for the dip strategy (14.9%, -25%, steadier). Maybe later: a 20-30% sleeve beside dip, tested as a combo first. Not traded. Not financial advice.

Files: scripts/new_ideas.py (modes `buyback`, `buyback2`), .github/workflows/new-ideas.yml, data/new_ideas_buyback.json, data/new_ideas_buyback2.json.
