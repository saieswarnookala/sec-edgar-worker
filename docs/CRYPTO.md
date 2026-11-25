# Crypto: the 50-day trend rule (paper bot 15)

Research only, not financial advice. Last updated Nov 25 2026.

**Rule:** hold Bitcoin (via IBIT) and Ether (via ETHA), half the money each, only while each coin is above its 50-day average of daily closes; otherwise T-bills.
Decided at 3:30 pm ET with the live coin price, traded at that day's close. If the 3:30 run is missed, the evening run decides after the close and trades at the next close.

## Results

| | Per year | Worst drop | 2022-2026 |
|---|---|---|---|
| BTC + ETH, 50-day rule (2018-2026, weekdays, ETF costs) | 56% | -57% | +16%/yr |
| Hold BTC + ETH | 23% | -77% | -5%/yr |
| BTC only, 50-day rule (2015-2026) | 77% | -62% | +17%/yr |
| Hold BTC | 62% | -83% | +4%/yr |
| Real ETF prices Nov 2024-Nov 2026: BTC rule / hold IBIT | 11.3% / -21.6% | -25% / -54% | |
| Real ETF prices Nov 2024-Nov 2026: ETH rule / hold ETHA | 43.3% / -32.3% | -35% / -68% | |

Plan on 15-30% a year with big swings: the 56% comes mostly from 2018-2021. The rule trails holding in about 1 year in 3; its job is to cut crashes.

## What we tested (Nov 24-25 2026)

| Round | Script / data | What | Result |
|---|---|---|---|
| 1 | scripts/crypto_lab.py, data/crypto_lab.json | Trend rules, top-20 coin rotation, crypto dip bot, analogue patterns, calendar; 37 coins incl. dead ones | Only trend worked. Rotation 95%/yr 2017-26 with BTC filter but 23% since 2023 (watch); dip bot, patterns, calendar dropped |
| 2 | crypto_lab2.py | MA 20-200 grid x 3 costs, 300-run placebo, Fear & Greed, MVRV, funding | 30-150 days all beat hold; 0/300 random schedules beat 50d; F&G fails; MVRV<1 rare (3 episodes); funding data blocked |
| 3 | crypto_lab3.py | Weekday-only (ETF) execution, BTC+ETH 50/50, weekly checks, 2-5% buffers | Weekday trading keeps the edge; buffers/weekly don't help |
| 4 | crypto_lab4.py | 19 unseen coins, rolling 1/2-year windows, walk-forward MA choice, 1-3 days late, deflated Sharpe | Smaller worst drop 19/19, higher return 16/19; beats hold 54-67% of windows, smaller drop 81-90%; re-tuning worse; late still beats hold; DSR 0.9999, t 5.0 |
| 5 | crypto_exec.py | Real IBIT/ETHA + hourly coin prices, next close vs 3 pm same-day | Signals 98-99% same as backtest; same-day best |
| 6 | crypto_sol.py, data/crypto_sol.json | Add Solana? BTC+ETH 50/50 vs thirds vs 40/40/20, 2020-26; bootstrap luck check; real BSOL ETF | Thirds 108%/yr vs 58% overall, but that is SOL's 2020-21 bubble. From 2022: +8.5 pts/yr, only 84% chance it's real (bar 95%); last 2 years worse (14% vs 27%); same worst drop. BSOL rule +6% vs hold -59%. Not added; recheck mid-2027 |

## Example

The 50-day average of Bitcoin is $80,000. At 3:30 pm Bitcoin is $82,400 (+3.0%): alert "BUY IBIT at today's close"; the $5,000 Bitcoin half buys IBIT around 3:50 pm.
Weeks later Bitcoin is $78,000 while its average has risen to $79,500: alert "SELL IBIT at today's close"; money back to T-bills. Ether works the same through ETHA.

## Pros and cons

- Pros: cuts crashes (2022 about -51% vs -66% holding); works on coins it was never tuned on; tolerates trading 1-3 days late; spot ETFs make costs tiny.
- Cons: still -57% worst drop; trails holding in about 1 year in 3; ~16 switches a year per coin, so short-term tax (Roth is best; crypto ETFs follow wash-sale rules); Robinhood's ~1% crypto spread kills fast rules (on Robinhood only 120-140 day averages survive).

## Running it

- Paper bot: scripts/paper_crypto.py (+ test-crypto.py), .github/workflows/paper-crypto.yml, state data/paper_crypto_state.json.
- Timers: Cloudflare market timer 19:30/20:30 UTC (3:30 pm ET decision), evening timer 21:45/23:45 UTC (fills at the close); GitHub backup 22:30 UTC.
- Alerts: NTFY_TOPIC_CRYPTO secret only. Dashboard: Crypto tab.
