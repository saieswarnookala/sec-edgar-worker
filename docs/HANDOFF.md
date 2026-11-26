# Sentinel trading project: full handoff (as of Nov 14, 2026)

Read this first in any new chat. It holds the decisions, numbers and reasons from ~5 weeks of chats (Oct 6 to Nov 12, 2026).
Details live in this repo (scripts/, data/, live/), the doc and the dashboard. Not financial or tax advice.

- Owner: Sai, Dallas/Farmers Branch TX (no state income tax). Wants short, casual, example-driven answers; often uses voice.
- Repo: github.com/saieswarnookala/sec-edgar-worker (PUBLIC: never commit tokens, account numbers, IPs or keys).
- Dashboard: https://sentinel-web.saiesh-dev.workers.dev (site/dashboard/page.html; `node site/test.mjs` must pass 18 tests; "Deploy website" workflow deploys on push).
- Results doc: https://claude.ai/artifact/5NywFGd5djz8cSM3gJHg3m ("Buy the Dip in Strong Stocks: Backtest Results").
- GitHub access: Sai gives a token when needed. The old full-access token was pasted in chat and must be revoked; use a fine-grained, repo-only, short-expiry token.

## TO-DO for Sai (open)
- [ ] Journal brain: console.anthropic.com -> ~$5 credit + spend limit -> API key 'sentinel-journal'. VM ~/.sentinel-live/config.env: ANTHROPIC_API_KEY=... and SEC_USER_AGENT="Sai <email>".
      Test: rm ~/.sentinel-live/journal.json; cd ~/sec-edgar-worker/live; node journal.mjs --date 2026-11-25; tail -2 ~/.sentinel-live/journal.md (Brain column shows a verdict).
- [ ] Crypto alerts: new ntfy topic + GitHub secret NTFY_TOPIC_CRYPTO.
- Shadow journal (VM only, live/journal.mjs, dip-journal.timer 4:50 pm ET, ~/.sentinel-live/journal.md): review ~monthly, judge after 6-12 months / 100+ dips.

## 0r. "Brain" tests (Nov 25; report: AI reasoning layer for trading bots) - nothing adopted
- Dip cause tags (dip-news-tags.yml -> data/dip_news_tags.json, v3.0 live-like 2016-26, 2,936 signals, 1,378 trades): Alpaca/Benzinga headlines
  effectively start 2021 for our tickers (0 tagged trades 2016-20; 2021-26 most trades still have no own headline) -> category samples tiny (downgrade 19, legal 17, guidance 2).
  Firm bad-news dips did NOT bounce worse (any bad news +1.30%/trade n48 vs +0.79; downgrade +1.85; legal +0.02 n17). Sector-wide dips (peers -5%+) +1.34 vs +0.73;
  8-K earnings dips +0.32 vs +0.95. Full bot 2016-26: today 27.3; skip firm bad news 26.6 (random skip 27.1-28.2); skip downgrade 26.7; skip stock-alone dips 24.4; skip no-headline dips 20.4. Keep taking every signal.
- India momentum brain (india-pit.yml MODE=brain -> data/india_brain.json): today 32.6/-23.8 (test 36.0). Crash flag half/out (2y<0, 1y<0, rebound, 15% below high): 25.6-31.9, same -23.8 drop.
  Steady risers (frog-in-pan) 29.0-29.7 (worse). Vol target 20/25%: 31.9/32.4 (dd -23.1). Combos 27-28. Keep the bot as is.
- Parking alternatives (park-alt.yml -> data/park_alt.json, live-like/realistic 1999-26): today IEF 21.9/16.6; + cash earns T-bills 22.1/16.8 (+0.2, = SGOV when IEF filter is off);
  always T-bills 20.7/15.5; always IEF 21.9 (2022 -13.8); TLT 21.6; GLD 21.2 (dd -28.9, but 2013-26 24.9); IEF-or-GLD 21.6. Keep IEF. Robinhood Gold ($60/yr) not worth it below ~$2k cash.

## 0q. Slot usage + return split (Nov 25; slot-usage.yml, return-split.yml; v3.0 daily 1999-2026)
- All 10 slots full ~4 times/yr, ~2 days each (10 days/yr, 4% of days); avg 1.8 slots used; 0 slots 43% of days. 2026 unusually busy (59 full days).
- Return split %/yr (1999-2026): full bot 21.9 live-like / 16.6 realistic; dips only with idle cash in T-bills 13.2 / 8.3. Parking adds ~8 pts/yr.

## 0p. Solana add-on test (Nov 25; crypto-sol.yml -> data/crypto_sol.json; SOL era 2020-06 to 2026-11)
- %/yr, worst drop: BTC+ETH 50/50 rule 57.9/-56.8 | thirds 108.4/-57.4 | 40/40/20 89.5/-57.1. 2022+: gap +8.5 pts/yr, bootstrap 83.5% >0 (range -4.4..23.4). Last 2 yrs: 2-coin 26.7 vs thirds 14.2.
- Correlation 2022+: BTC-ETH 0.85, BTC-SOL 0.76, ETH-SOL 0.77. SOL rule: 20 switches/yr, in 51% of days; today -23% below avg (out).
- BSOL (Oct 2025+, corr 0.92 to SOL): rule +6.0/-33.7 vs hold -59.0/-66.4. GSOL pre-2025 was an OTC trust (premium), ignore.
- Verdict: not added (fails the 95% bar; gain is the 2021 bubble). Recheck mid-2027 with more SOL ETF history.
- Crypto live idea (Sai): a separate Robinhood MCP account for crypto so it never mixes with the dip bot's 10 slots or trips its unknown-order halt.

## 0o. Crypto execution check (Nov 25; crypto-exec.yml -> data/crypto_exec.json; real IBIT/ETHA + hourly coins, Nov 2024-Nov 2026)
- BTC: backtest 11.7/-29.4 | ETF next close 11.1/-27.0 | 3 pm decision + same close 11.3/-25.1 | hold IBIT -21.6/-53.7. ETH: 27.5/-42.5 | 22.4/-42.7 | 43.3/-35.3 | hold -32.3/-67.9.
- Signal agreement with backtest 98-99%; IBIT vs BTC daily tracking std 0.66%, ETHA 1.09%. Yahoo range=max returns sparse daily bars -> always period1/period2.
- Paper bot 15 now: MODE=decide at 3:30 pm ET (Cloudflare marketJobs 19:30/20:30 UTC) -> fill at that day's close in the evening run; evening fallback decides + next close.

## 0n. Crypto lab round 4 (Nov 25; crypto-lab4.yml -> data/crypto_lab4.json): the 50-day rule is real
- 19 unseen coins (XRP..EOS, 0.10%/side): rule smaller worst drop 19/19, higher return 16/19 (e.g. ADA 42.9 vs -3.8, BNB 101 vs 56; XRP/LTC/XMR slightly worse).
- Rolling windows: BTC beats hold 59% (1y) / 65% (2y) of windows, smaller drop 81% / 86%; ETH 54/67, 87/90.
- Walk-forward picking the length yearly: BTC 49.1 vs fixed 50d 69.0 vs hold 51.2 (2017-26); ETH 68.6 vs 63.7 vs 44.3. Don't tune; keep 50.
- Late trading 1-3 days: BTC 62.8-64.2 vs on time 70.9 vs hold 50.1; ETH 31.5-46.8 vs 56.2 vs 21.1.
- Deflated Sharpe 0.9999 (57 trials), Sharpe 1.47 vs hold 1.07, t 5.0.

## 0m. Paper bot 15: crypto trend (Nov 25) - scripts/paper_crypto.py, paper-crypto.yml, data/paper_crypto_state.json, test-crypto.py
- 50/50 BTC (IBIT) + ETH (ETHA), $10k virtual; weekday after close: coin > 50-day avg of daily closes -> hold ETF else T-bills; trade at NEXT US close; 0.05%/trade.
- Started on its first run (no back-fill); catches up missed days; never repeats a day. Alerts only on NTFY_TOPIC_CRYPTO secret (Sai adds it), on switches + Friday summary.
- Timers: Cloudflare eveningJobs 21:45/23:45 UTC + GitHub backup 22:30 UTC weekdays. Dashboard: new top tab 'Crypto' (#crypto, drawCrypto) + bot 15 card.

## 0l. Crypto lab round 3 (Nov 25; crypto-lab3.yml -> data/crypto_lab3.json): how to run it
- ETF route, weekday-only trading (weekend signals wait for Monday) keeps the edge: BTC 50d 76.9/-62 (7-day 80.9); BTC 100d 79.4/-56 (2022-26 21.2/-39 vs hold 4.0/-67).
- 50/50 BTC+ETH (2018-06+): hold 23.3/-76.5; 50d weekdays 56.3/-56.8 (2022-26 15.6 vs -4.8); 100d 47.5/-52; 140d 44.2/-51.
- Weekly checks: lower drops sometimes, lower return; buffers 2-5% don't help the 50d. Robinhood direct: BTC 140d 67.6/-63 vs hold 62.1/-83 (slow rules only).
- Pick for paper bot: 50/50 BTC+ETH, 50-day average, decided at weekday close, traded next weekday close, via IBIT/ETHA; T-bills when out.

## 0k. Crypto lab round 2 (Nov 25; crypto-lab2.yml -> data/crypto_lab2.json)
- Trend is REAL: BTC every MA 30-150 beats hold (ETF route 63-83%/yr vs hold 61.9%, worst ~-60 vs -83); placebo 0% of 300 random schedules beat the 50-day (ETH 0.7%). ETH all lengths beat hold (31-62 vs 12.6).
  BTC 50d ETF route 80.9/-61 (2023-26 49.6/-29 vs hold 37.9/-53); Robinhood 0.95%: 50d 54.0, 120-140d 67-68 best (fewer switches).
- Fear & Greed: contrarian timing loses (fear-only -12.8%/yr); savings-plan tilt buys 4.9% cheaper. DROP as timing.
- MVRV < 1 (452 days, ~3 episodes): median fwd 90d 28.8% vs 10.0, 365d 127% vs 75%. Trend OR MVRV<1: 71.0/-71.5 vs trend 67.1/-65.6 (0.5%/side). Rare-bottom add-on, few events.
- Funding (BitMEX) not reachable from GitHub runners; skipped.
- Candidate: BTC+ETH 50-day trend via IBIT/ETHA (Roth), or 120-140 day on Robinhood. Not started; paper bot possible.

## 0j. Crypto lab round 1 (Nov 24; crypto-lab.yml -> data/crypto_lab.json; Yahoo daily, 37 coins incl. LUNC/FTT/BSV; trade next day's close)
- BTC trend (from 2015, per yr / worst): hold 59.7/-83. 50d: 77.0/-62 (0.10%/side), 64.5/-66 (0.50%), 51.3/-70 (0.95% Robinhood). 100d+40% vol target 39.4/-42 (0.5%). 20d dies at Robinhood cost (19.9).
- ETH (from 2018): hold 13.6/-86; 50d 45.3/-62 (0.5%); 200d+vol target 25.9/-43. Trend helps ETH most (2022: -46 vs -68).
- Rotation (top 20 coins by volume, weekly): no filter loses (-94..-98% drops). With BTC>50d filter: top 3 by 28d 95.3/-70 vs BTC 50.7/-83 (2017+), BUT 2023-26 23.2 vs BTC 38.7. Watch.
- Dip bot on coins: win 45-49%, avg -0.5%/trade at 0.5% -> DROP (crypto trends, doesn't mean-revert in 5 days).
- Analogue patterns: BTC hit rate 53%, ~0 at 0.5%; ETH noise. Calendar: weekday effects flip between halves; weekend-only ~0. DROP.
- Research notes: /home/claude/research_notes/Crypto trading strategy evidence/ (onchain: funding<0 90-day buy, MVRV bands, F&G tilt; calendar: 10-day-high overnight; costs: Robinhood ~2% round trip, ETFs 0.25%/yr; no wash-sale on direct crypto as of May 2026).

## 0i. India buyback tender offers (Nov 24) - not backtested by us (no free deal dataset; list pages are JS-loaded)
- Independent study (Ganesh S, Oct 2026, 346 tender offers since 2012, Rs 1 lakh per deal, tender all, sell rest on settlement): from cum date 74% profitable, median 3.6%, 50 days, ~28% annualised; worst decile -13 to -15%.
  Small-holder acceptance 95% (2012-19) -> 43% (2020+) -> 37% (2023+). Premium bands: 0-10% 3.5%/90% profitable; 10-20% 6.2%/74%; 20-30% 5.3%/79%; >30% 4.1%/69%. Market at/above offer: 27 deals, none profitable (median -8.2%).
- Tax: before Oct 2024 tax-free to holder; Oct 2024-Mar 2026 whole payout = dividend at slab (bad); from Apr 2026 capital gains on the gain only (20% STCG). Rs 2 lakh small-holder test per PAN.
- Verdict: optional small side trade for family; added to the friend doc. A forward 'buyback watcher' alert is possible if wanted.

## 0h. Last tests (Nov 24; last-tests.yml) -> no changes
- Daily step time (5-min replay 2016-26): v3.0 3:15 25.6 | 3:30 25.6 | 3:45 27.2 | 3:55 26.1. v3.2 3:15 29.9 | 3:30 29.1 | 3:45 30.3 | 3:55 30.8 (16-20 23.1 vs 21.9, 21-26 37.8 vs 38.1). Keep 3:47.
- US short-term momentum (last month's top 10/20, most-traded third): 0.5-3.8%/yr, worst -82 to -88% (1999-2012 negative); blends with dip worse. Classic 12-1 top 20: 8.5-9.1%. DROP.
- India value proxy (3/5-year losers): best 7.3%/yr, worst -64%; blends 80/20 23.1 / 70/30 21.3 vs momentum 26.7. DROP.
- Summary doc for Sai's friend: https://claude.ai/artifact/4p7QCQgvtcyQr6SsMayb2E

## 0g. Next 3 tests (Nov 24; next3.yml -> data/next3.json, data/intraday_wf.json) -> no changes
- Pre-earnings buys in idle slots (realistic, v3.0 16.8/-27.3): 5d before, sell day before 11.9/-35; hold through 10.5/-52; 1d before hold through 1.8/-83 (turnover); max 2 slots 14.0/-29. DROP.
- FOMC even-week parking: 9.7/-27 vs 16.8 (placebo odd weeks 11.1). Parking all the time beats both. DROP.
- Walk-forward v3.0 daily 2004-26 realistic: fixed 10%/5d/200 13.4%; pick-by-all-past 11.3 (stuck on 8%/7d); pick-by-last-5y 13.4; best in hindsight 14.9 (10%/7d/100). Fixed settings not overfit.
- Walk-forward v3.2 replay 2017-26: fixed dip 10% +5% 31.7%; pick-by-past 28.6-29.3. Grid: dip 8% 23.6-25.3 (worse), 10% 29.2-30.9, 12% 28.5-29.2. Keep fixed; plan ~2-3 pts below backtest.

## 0f. Trailing stop vs +5% target (Nov 24; trail-test.yml -> data/intraday_trail.json) -> KEEP +5% every 15 min
- Live-exact v3.2 (target +5%, checks every 15 min from 10:00): 30.3%/yr, worst -16.8 (16-20 21.9, 21-26 38.1); old replay (5 min from 9:35) 30.5. v3.0: 27.2.
- Trailing (arm / drop / interval): 5/1/15 29.9 | 5/1/5 30.4 | 5/2/15 30.5 | 5/2/5 30.9 (16-20 21.7, worst -17.0) | 3/1 29.7-29.8 | 7/2 29.6-29.7. None wins both halves without a deeper drop.

## 0e. Busy vs quiet dips, full sims (Nov 24; vol-quality.yml -> data/vol_quality.json, data/intraday_volq.json) -> KEEP 2x
- v3.0 daily realistic (per yr / worst): today 16.6/-27.3 | skip>1.6x 17.0/-28.4 | skip>1.4x 17.0/-29.6 | skip>1.2x 16.6/-31.3 | half>1.4x 16.7/-28.1 | tilt 17.8/-28.8 (gain all 1999-2012; 2013-26 17.6 vs 17.8).
- 5-min replay 2016-26 (volume known at the time): v3.0 27.2 -> 27.1-27.2 (skip), 25.5-26.4 (half); v3.2 30.5 -> 30.3-30.5 (skip), 28.9-29.8 (half).
- Per-trade average rises (0.82 -> 1.01%) but fewer trades and the freed money earns about the same, so no gain per year. Tag edge is real, portfolio edge is not.

## 0d. Research tests Nov 24 (research-nov24.yml -> data/park_turnover.json, luck_check.json, india_taxexec.json)
- Dip quality (v3.0 trades, realistic avg/trade): abnormal volume over the dip (5d/50d, all < 2x): low third +0.84/+0.87% (99-12 / 13-26), middle +0.31/+0.37, high 0.00/+0.20.
  Big-company dips (60d dollar volume rank top third) +0.75/+0.94 vs bottom third +0.02/+0.16. Both hold in both halves. Queue by low abnormal volume: +0.3-0.5 pt/yr (16.6 -> 16.9-17.1).
  NEXT: on v3.0 skip/half-size dips with volume ratio > 1.4 or bottom-third dollar volume (earlier tighter-cutoff test was v1, with empty slots in cash).
- Parking vol target (v3.0 realistic, ref 16.8%/-27.3 with T-bill interest): 20% -> 16.3/-22.4; 15% -> 15.4/-21.6; 10% -> 13.9/-21.5. Cuts the worst drop (all from 1999-2012), costs 0.5-3 pts.
- Luck check: trial Sharpe spread 0.14; luck bar Sharpe 0.34 (N=70). v3.0 realistic Sharpe 0.95, t 5.0, DSR 0.999; v1 0.80 / t 4.2; v3.0 2013-26 only 1.11 / t 4.1. All pass.
  India 120-variant grid: train(08-18) vs test(19-26) rank corr 0.74; best-in-train at 78th pct in test; top-10 median test 42% vs all 31%.
- India tax execution (honest): old engine 22.6% after tax; with Apr-Mar year + gold/liquid leg taxed at slab 31.2% -> 20.8% (dd -39%). hold366 / March LTCG harvest / ST loss harvest / arbitrage fund: all within +-0.1. Dashboard best case after tax 26.4 -> 25.5.

## 0c. Hold-length + target test (Nov 23; scripts/hold_test.py, intraday_exits.py HOLD=1, hold-test.yml -> data/hold_test.json, data/intraday_hold.json)
- Daily 1999-2026, v3.0 realistic: max hold 3d 15.2% | 5d 16.6% | 7d 17.8% | 10d 17.8% | 40d 18.3%; worst drop ~-26/-27% for all. v1: 13.4% (5d) -> 15.3% (40d).
  BUT the gain is all 1999-2012 (v3.0 5d 15.4 -> 7d 18.0); 2013-2026: 5d 17.8, 7d 17.6, 10d 17.2, 40d 17.6 (no gain).
- 5-min replay 2016-2026: v3.0 3:45 5d 27.2 | 7d 27.0 | 10d 26.4 | 40d 26.4; v3.2 +5% 5d 30.5 | 7d 30.5 | 10d 30.1 | 40d 30.2. 2021-26 favours 5d.
- Target (v3.2, 5d hold): v3.0 +3% 30.9 | +5% 30.5 | +7% 30.4 | +10% 30.4; v1 +3% 27.3 | +5% 28.1 | +7% 27.9 | +10% 27.8. Within noise.
- Forced 5-day exits: 28% of trades, avg -5.2%; with 10d: 5% of trades, avg -10.5%. Win rate ~62-66%.
- Verdict: keep 5 days and +5%. Longer holds only helped before 2013.

## 0b. Live bot v3.2 built (Nov 23) - rollout: v3.0 live now -> one DRY v3.2 day -> live v3.2
- live/live-dip.mjs: LIVE_STRATEGY=v32 + `intraday` / `preview-intraday` commands. intradayPlan() = paper-v32 v32Intraday rules on real holdings
  (+5% target only age>=1; stock then ETF dips into free slots; fund from cash then partial park sells; target money with no buys -> park, 2% buffer).
- Buys now record entry_px (trade + intraday). Inherited positions: entry_px fallback = Robinhood average_buy_price (orders.mjs readAvgPrices), then dollars/qty.
- Same safety as trade: HALT, lock, drawdown breaker, checkLimits, per-slot idempotency key, never re-buy/re-sell a symbol already traded today (parking excepted).
- 3:47 run under v32: today's intraday order ids (state.intraday[].placed) are excluded from the duplicate check; verify counts them as ours (no false "stranger" HALT).
- setup-vm.sh: dip-intraday.timer Mon..Fri 10..15:00/15 ET (no-op unless LIVE_STRATEGY=v32). test-live.mjs: v32intra + v32preview (rules, handover from v3.0, 2nd check places nothing, final run sells nothing bought today).
- Dry-day check: `journalctl --user -u dip-intraday` and state.intraday[].holding (every position needs entry_px).

## 0a. Live bot -> v3.0 (Nov 23)
- live/live-dip.mjs: LIVE_STRATEGY=v3 = paper bot 10 rules (ETF dips via decide(etfScores), IEF via bondParkSymbol). ETF dips skip today's parking ETF / ETFs held as parking.
  Strategy buys (incl. ETF dips, kind 'etf') are recorded as positions by plan.buys, not by 'not a parking ETF' (SPY/QQQ/IWM/EFA/EEM are in both lists).
- FIX (affects v1 too): checkLimits capped EVERY buy at 20% of the account, so a big parking buy/switch would halt the bot; parking buys now capped at the account value.
- New `node live-dip.mjs preview`: full plan on real data, forced dry, no state saved, no HALT. Tests: test-live.mjs 27 ok (livev3 + preview + parking-limit cases).
- Sai switches on the VM: git pull; node test-live.mjs; echo 'LIVE_STRATEGY=v3' >> ~/.sentinel-live/config.env; node live-dip.mjs preview. Update dashboard Start here / Live bot rules once confirmed.

## 0. Ideas catalogue (Nov 22)
- `ideas/` has one file per strategy idea or tweak (77 so far): rules, result, verdict, data/script/workflow, and a `run()` using the shared engine. Index: ideas/README.md.
- Add a new idea: one entry in `scripts/build_ideas.py` CATALOG, then `python scripts/build_ideas.py && python test-ideas.py`. Do this after every new test.

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
| **Dip + drift 6+4 mix**, one account (2004–2026) | 15.8% (ideal 19.1%) | 12.3% | −24% | Virtual paper bot 7 (from Nov 16) |
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
- Refresh: Cloudflare cron '45 21,23 * * *' dispatches screen.yml daily (GitHub schedule ran 4-6 h late). Cloudflare free plan: 5 of 5 cron triggers used (5th = India Bot B).
- Discussion brief for Sai's friend: https://claude.ai/artifact/7xSY9Xtx9YuszTaBYVEfUi

### Rhythm and volatile-bounce research (Nov 14) - nothing new to trade
- Single-stock rhythm test (scripts/single_stock_rhythm.py, workflow rhythm-test.yml, data/rhythm_<sym>.json): ~800 intraday/1-3 day rules per stock incl. research ideas (same half-hour persistence HKS 2010, first->last half-hour Gao et al. 2018, yesterday's last 30 min). ORCL, NVDA, TSLA, AMD, PLTR, COIN: intraday rhythms did not survive 2023-26; only "buy after a 3%+ down day, hold 1 day" stayed positive vs a random day on 5 of 6 stocks (~+0.3-0.4%/trade).
- Volatile bounce (scripts/volatile_bounce.py, workflow volatile-bounce.yml, data/volatile_bounce_{sp500,popular}.json): ~10k scenarios on point-in-time S&P 500 (2004-26) + 45 popular names (2016-26, hindsight-biased). Filters help a little (quiet volume, 200-day uptrend, skip earnings drops, 3-day/smart exit ~+0.1%/trade each) = same as the dip bot. Picking the best version on train didn't predict test (rank corr ~0). 1%/trade versions trade too rarely; none beat SPY as a strategy on the unbiased list. Popular-list "gap down 7%+, hold 2 days" looked great but is ~0 on the S&P list -> hindsight. Conclusion: keep the dip bot; no new bot.
- Pattern matching / lookalikes (scripts/pattern_match.py, workflow pattern-match.yml, data/pattern_match.json): nearest-neighbor on the last 10/20/40 daily moves, own-stock or pooled history, 26 stocks incl. losers, 2017-22 pick / 2023-26 check. Detector validated on random (finds nothing) and planted data (finds it). Real data: 0 of 324 pooled versions beat luck even on train; per stock 0-2 vs ~7 expected by luck; direction calls no better than guessing 'up'. Dead end.
- Candles (Nov 14-15): scripts/candles.py, data/candles.json (PIT S&P 500 1999-2026): classic patterns ~0 after costs (only 'inside day', ~1 bp). Dip-bot trades that CLOSED AT THE LOW bounced more (+1.54%/trade vs +0.71% for dips with a lower tail; both halves), but as a bot filter only 17.4% vs 17.1%/yr with a deeper worst drop -> not adopted. Month-end timing (scripts/month_end.py, data/month_end.json, SPY/QQQ/IWM 1993-2026): turn-of-month window still a bit better in 2016-26 (SPY 8.9 vs 4.6 bps/day, t~1, not significant) and gone since Jun 2024 (T+1); deposit day (-4 vs +1 vs +4) makes no difference (16.2 vs 16.2%/12m); pension-rebalancing signal inconsistent (worked 1993-2008 and 2016-26, reversed 2009-15). Not adopted. Dip universe (scripts/dip_universe.py, data/dip_universe_{us_all,sp500,us_all_spcheck}.json): S&P 500 ~18 dip signals/month (median 9), bot takes ~9; the same rules on ~5,000 non-S&P US stocks LOSE (-28%/yr 2016-26) while Alpaca data limited to S&P members gives +18.5%/yr (data verified) -> the S&P list itself is the quality filter. One-at-a-time tweaks (S&P 1999-2026): 150-day trend 14.8% vs 14.1%, 8% dip 17.4%, hold 7-10 days ~15.4%, no trend filter -73% worst drop. Combination grid (data/combined_dip_tuned.json): +ETF, 8% dip, 150-day, hold 7 = 20.9%/yr, worst -19% (both halves better; with 3x costs 2013-26 edge gone; 2022 -11%) -> paper bot 6 'tuned' (virtual, data/paper_dip_tuned_state.json, TUNED in paper-dip.mjs). 52-week-high & same-month seasonality tilts (scripts/tilts_52w.py, data/tilts_52w.json, PIT S&P 500): both LOST to equal weight in 1999-2016 and 2017-26 (52w-high top 10%: -0.47%/month). Dead for large caps. But dip-bot signals 20%+ below the 52w high bounced more (+1.5-2.3%/trade) than dips near the high (+0.5-1.0%) in both halves: possible ranking tweak, untested in the full bot. 100-stock rhythm test (Nov 15; workflow rhythm-batch.yml, picker scripts/pick_rhythm_universe.py = top non-S&P stocks by 2022 dollar volume, data/rhythm_universe.json, data/rhythm_<sym>.json, throttled Alpaca 15 req/min/job x 10 jobs): ~950 rules x 100 stocks. Intraday families (time of day, breakouts, gaps, VWAP, half-hours, 1-30 min candles): 939 early winners, 24 still significant in 2023-26 vs ~22 expected by luck, only 41% even positive -> dead. Multi-day 1-3 day swings: 61% of early winners beat a random-day buy later (median +0.11%/trade) -> weak stock-specific persistence, not tradable alone. CVNA 1-min 'survivors' = CVNA's 100x rally, not a pattern. Per-stock candles (daily/30-min/15-min) in the rhythm test: 0 of ~420 versions survived 2023-26 on ORCL/NVDA/TSLA/AMD/PLTR/COIN.
- More-trades research (Nov 14): (a) ETF dip sleeve (scripts/etf_dips.py, data/etf_dips.json; 29 index/sector/country ETFs, Yahoo 1999-2026): '5-day drop >= 5%, above 200-day, buy at close, sell back above 5-day avg (max 5-10 days)' on all ETFs = ~3 trades/mo, 73% win, +0.84%/trade (+0.37% vs SPY same days); with idle money in SPY ~+1.3%/yr over SPY in BOTH halves (1999-2012 4.7 vs 2.9; 2013-26 15.5 vs 14.5); sleeve alone worst drop -7%. RSI(2) on ETFs ~0 vs SPY (decayed). Candidate add-on to the dip bot (paper first). (b) Industry-relative dips (volatile_bounce sp500, triggers '... vs industry', SIC2 leave-one-out): not better than the dip bot's own 10%/5-day trigger, which held up best (2016-26 ~21%/yr with SPY parking vs SPY 14.9%).
- Combined test (scripts/combined_dip_etf.py, data/combined_dip_etf.json; live dip rules on PIT S&P 500 + ETF rule sharing 10 slots, buy at close, SPY parking with 100-day crash rule, 1999-2026): today's bot 14.9%/yr, worst -26.7%; + ETF 5-day 5% dips filling free slots (hold <= 10 days) 17.1%/yr, worst -22.4%; better in both halves (12.1->14.6, 17.6->19.5) and with stress costs (12.3->14.4). All ETF variants B-E helped (+1.9 to +2.2/yr). Next: add ETF sleeve to the paper bot, paper-trade before Robinhood.
- Insider buying as a dip filter (Nov 15; scripts/insider_dips.py, workflow insider-dips.yml, data/insider_dips.json): SEC Form 3/4/5 data sets 2006q1-2026q3 (83 quarters, 1.27M buy/sell filings, cached in R2 as sec/form4/<q>.json.gz), officers/directors only, filing counted from the next trading day. Dry runs passed (random fake buys = no edge; planted = found). 3,709 dip trades 2006-26: dips with an insider buy in the prior 1/3/6 months bounced the SAME or worse (+0.16/+0.88/+1.03%/trade vs +0.99% without); buying into the drop -0.18%; 2+ insiders or $100k+ no better; insider dips won in only 9 of 18 years. Bot: 'insider buyers first' 14.4 vs 14.3%/yr (noise), 'insider only' 9.4%/yr (1 trade/mo). Dips at companies where 3+ insiders SOLD bounced a bit more (+1.45%), so skipping sellers hurts (10.4%/yr). Insiders are known to help small caps over months, not S&P 500 dips over days. Dropped. (Earlier standalone test, data/new_ideas_insider.json: cluster buys vs SPY ~ no edge.)
- 52-week-high ranking (Nov 15; scripts/dip_rank_52w.py, data/dip_rank_52w.json, PIT S&P 1999-2026): dips 20%+ below the 52w high do bounce more per trade (+1.72% vs +0.86%, both halves), but ranking them first doesn't help the bot: today's rules 14.4 vs 14.9%/yr (biggest-drop-first), bot 6 19.7 vs 19.4 (= noise; random order gives 14.3-14.9). Slots are rarely full (93 crowded days in 27 yrs for today's rules), so order barely matters. 'Only deep dips' = 12.3%/yr (too few trades). Not adopted.
- Short interest as a dip filter (Nov 15; scripts/short_dips.py, workflow short-dips.yml, data/short_dips.json): FINRA free twice-monthly short interest files exist only from Dec 2017 (earlier 403; probe scripts/finra_probe.py); 212 reports cached in R2 (finra/si/<date>.json.gz + finra/si_index.json.gz), counted 12 days after settlement. Dry runs passed. 2018-26: dips in heavily shorted stocks (days to cover >= 5) bounced far less (+0.08% vs +1.21% avg, t -4.4; most-shorted 20% t -5.6); lightly shorted (< 2 days) bounced more (+1.80%, t +4.2). Same direction for bot 6 rules and in both 2018-22 and 2023-26, but much stronger in 2023-26. Bot: skip days-to-cover >= 5: 24.0 vs 22.7%/yr (2018-22 13.4 vs 14.0, 2023-26 39.4 vs 35.2); bot 6 skip >= 3: 23.9 vs 21.0%/yr, worst -16.7 vs -20.4 (2018-22 equal). Only 8 years -> promising, not proven; now virtual paper bot 8 (from Nov 16).
- Short VOLUME check (Nov 15; scripts/short_volume_dips.py, workflow short-volume.yml, data/short_volume_check.json + data/short_volume_full.json): FINRA free daily short-sale volume (TRF files FNSQ/FNYX/FNQC) goes back to Aug 2009 (R2 finra/shvol/<YYYYMM>.json.gz; one 2010 file has no header and is read by its known layout). Agreement with days-to-cover 2018-26: short RATIO correlates (rank 0.32) and high-ratio dips barely bounce (-0.08% vs +1.22%, t -6.9), like DTC>=5 (+0.09%); the short JUMP during the dip is a different, weaker signal. 2009-2017: dips after a big short-selling jump bounced worse (-0.84% vs +0.14% avg, t -2.3); high ratio weaker there (t -0.9, only 98 dips). Bot gain is small in both halves (skip jump >= 10 pts: 15.6 vs 15.1%/yr 2009-26; 7.6 vs 7.2 early; 23.5 vs 22.8 late) because skipped dips mostly leave money parked. Supports bot 8's idea (short sellers are usually right), but expect +0.5-1%/yr, not more.
- Chart patterns (Nov 15; scripts/chart_patterns.py, workflow chart-patterns.yml, data/chart_patterns_{sp500,us_all}.json): 52w-high breakout on volume, bull flag, high tight flag, tight-base/VCP breakout, inverse H&S, double bottom, H&S top; close-based detectors, no look-ahead, one signal per stock per 20 days, costs by liquidity, vs the average eligible stock and vs a RANDOM-pick bot (dry run showed SPY is the wrong yardstick). Dry runs passed. Result: nothing works. All US stocks 2016-26 (5,101 stocks, ~45k signals): every pattern trailed the average stock after costs at 20 days (-0.2% to -0.8%), worse in smaller stocks; bots -18% to +7%/yr vs random-pick bot 6.3%. S&P 500 1999-2026: all within +-0.5% of the average stock; inverse H&S slightly negative. H&S top didn't predict weakness either. Dropped.
- S&P 500 additions/removals (Nov 15; scripts/index_changes.py, data/index_changes.json): added stocks run up +1.9% vs SPY in the 5 days before joining (needs announcement dates we don't have), then lag SPY after joining (-1.2% 5d, -1.7% 20d). Removed stocks that keep trading bounced strongly in 1999-2012 (+29% vs SPY at 60d, mostly 2009) but not in 2013-2026 (~0). No trade.
- Spin-offs (Nov 15; scripts/spinoffs.py, workflow spinoffs.yml, data/spinoffs.json): EDGAR Form 10-12B 2015-26 -> 103 new stocks (SEC tickers; smoke found AMRZ, RAL, SOLS, VSNT, FDXF). Day-1 buy, 1-year hold: avg +26% vs SPY but MEDIAN -2.4%, only 49% beat SPY; 2016-20 +1.5%, 2021-26 +50% -> a few huge winners. Bot (day 20, hold 1 yr, 10 slots) 28.3%/yr vs SPY 14.8% but worst -43%. Dry runs on random data swing +-7% with ~120 events. Lottery-like; watch, don't trade.
- Overnight effect (Nov 16; scripts/calendar_effects.py, data/calendar_effects.json): SPY 1995-2026 close->open 9.9%/yr vs open->close 1.1% vs buy & hold 11.1%; with 0.01%/side costs (2 trades a day) 4.5%, 0.02%/side -0.6%. Real but untradeable.
- Pre-FOMC drift (same script; 222 scheduled announcement days 1999-2026, dates parsed from federalreserve.gov 1999-2016 + listed 2017+): announcement-day SPY +0.39% (t 2.9) in 1999-2011, only +0.11% (t 0.5) in 2012-2026 -> faded after publication. Fed-days-only 1.5%/yr recently. No trade.
- 13F best ideas (Nov 16; scripts/thirteenf_best_ideas.py, workflow thirteenf.yml, data/thirteenf_best_ideas.json): SEC 13F data sets 2015q4-2026 (cached R2 sec/13f/*), managers with 20-400 positions, top holding <= 40%; CUSIP->ticker via OpenFIGI (6,695 CUSIPs, cached sec/cusip_figi.json.gz; ETFs dropped). 42 quarters, ~459 best-idea stocks per quarter, equal weight, rebalanced at each 13F deadline. 2016-26: best ideas 12.9%/yr, consensus (3+ managers) 13.3%, large-cap best ideas 14.0% vs equal-weight all stocks 10.3%, equal-weight top 500 12.1%, SPY 15.6%. Beats the average stock by ~2%/yr but loses to just holding SPY. Dropped.
- India: US bots 5 and 6 (Nov 16; scripts/india_dip.py bots, data/india_bots.json): NSE 2008-2026 realistic (next open, 0.30%/side stocks, 0.15% sector ETFs). India best (12% dip, 200-day, hold 5) 14.7% (Nifty 100-day parking) / 16.3% (150-day, else gold/liquid); + sector dips 13.6 / 15.3 (21 Nifty sector indices; Yahoo index opens often missing -> close-to-close fallback); US bot 1 rules 12.7 / 14.1; bot 6 tuned 5.0 / 6.6 (costs); parking only 12.4 / 14.3; Nifty with dividends 9.3%, -59%. Keep the India 12% version; sector dips and tuned rules dropped for India. No India short-interest data (bot 8 untestable). Live India would need NRI NRO non-PIS + Zerodha Kite Connect from the Oracle VM's fixed IP (daily login; US-resident eligibility to confirm).
- Crabel NR7/NR4 breakout (Nov 17; scripts/nr7_breakout.py, data/nr7_breakout.json): narrowest range of 7 (or 4) days, buy next day above its high, stop at its low; exits close / 2R / 3 days; PIT S&P 500 1999-2026, daily OHLC, 0.05%/side + 0.05% stop slippage. Dry runs passed. All 12 versions lose: NR7 -0.27% to -0.32% per trade (win 33-38%, profit factor 0.54-0.75), worse than the same breakout on ordinary days (-0.17% to -0.23%); both halves. Contraction adds nothing. (Opening range breakout itself was already rejected Nov 6-8: 1,152 + 2,304 versions incl. 'stocks in play'.)

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

### Bot 7: dip + drift 6+4 (virtual, from Nov 16)
- mixStep in scripts/paper-dip.mjs (MIX), state data/paper_mix_state.json, runs in the 3:45 pm dip run. 6 dip slots (today's rules, smart exit) + 4 drift slots (hold 60 trading days), 10% each, Clear Leader/cash parking, fractional, $10k. Drift signals: the morning paper-drift run writes data/paper_drift_signals.json; bot 7 fills them at the ~3:45 pm price (backtest: open). Dashboard card 7. Test in test-paper-dip.mjs.

### Nov 19: v3.2 = v3.0 + intraday dip buys + 5% profit target (write-up https://claude.ai/artifact/BAX5ngN5XBvkiu2ppgobjr; dashboard tab "v3.0 -> v3.2: all numbers")
- scripts/intraday_exits.py on Alpaca SIP 5-minute bars 2016-2026 (R2 alpaca/m5day closes, alpaca/m5vol volumes; ~10.4k calls each). Base (3:45 only) matched the 1-minute replay (24.9/27.9 vs 25.1/28.0).
- Run 1 (data/intraday_exits.json; candidates = close-based dips only, full-day volume): intraday exits (sell above avg every 5/15/30 min, no-rebuy, lock-ins, +2/3% targets) tie or lose; +5% target +1-1.5; placebo worst; intraday buys +2.1/+3.6.
- Run 2 (data/intraday_confirm.json; + stocks whose daily low was 8%+ worse than SPY): v3.0 intraday buys 31.4 vs 27.9; +7%/+10% targets shrink smoothly; combo 32.2.
- Run 3 (data/intraday_fairvol.json; FAIR_VOL=1: volume so far x live curve, 86% of checks used it): v3.0 base 27.1, intraday buys 15/30/60 min 30.7/30.1/30.0, + 5% target (= v3.2) 31.0% (halves 22.7 vs 17.9, 38.7 vs 35.5; 2x costs 28.4 vs 25.3; worst -16.8 vs -15.8; 19 vs 13 trades/mo). Robinhood rules: 24.2 -> 28.8.
- Known small gaps (net est. +-0.5%/yr): parking return not split by time of day; ETF intraday-only dips partly missing (ETF candidates close-based <= -3%); low-based list uses SPY close move; half-days. A final run with these fixed is pending; then paper bot 12 (v3.2, 5-15 min checks).
- Calculator rows v3.1/v3.2 are estimates (v3.0 1999-2026 + measured gains): v3.2 19.5 realistic / 26.7 ideal.

### Bot 11: Dip bot v3.1 = v3.0 + 2 earnings-drift slots (virtual, from Nov 20)
- paper-dip.mjs v31Step (V31: 2 slots, 60-day hold, 10% each, on top of v3.0's 10; drift signals from data/paper_drift_signals.json, same-day ~3:45 fill; cash raised from parking), state data/paper_v31_state.json; virtualStep got extraEquity so slot sizes include drift value. Test in test-paper-dip.mjs.
- Evidence scripts/v3_drift.py (data/v3_drift.json, 2004-2026 since SEC 8-K dates start Aug 2004): live-like v3.0 18.4% (-18.7%) -> +2 drift 20.0% (-17.6%), +3 drift 21.2% (-20.3%); halves 12.7->14.9, 23.5->24.6; realistic 14.3->16.3; 4%/6% beat and 40-day hold variants +1.3..+2.2; ~0.7 drift trades/month, ~+5.3%/trade. Cash T-bill interest +0.1-0.2%/yr (Robinhood sweep pays it anyway). Tuning (scripts/v3_tuning.py) and sector cap: rejected (walk-forward pick 8%/200/7 earned 20.1 vs 22.4 on unseen 2013-26; cap no gain, bigger drop). Minute replay of tuned versions agrees.
- Calculator row v3.1 = estimate (v3.0 1999-2026 + measured drift gain): 18.6 realistic / 24.4 ideal.

### Bot 10: Dip bot v3.0 (virtual, from Nov 19)
- paper-dip.mjs, state data/paper_v3_state.json: Robinhood stock-dip rules + ETF dip sleeve (bot 5, stocks first, ETFs fill free slots, max hold 10) + bond parking (bot 9) in one $10k virtual account. Candidate to replace the live rules after paper time.
- Evidence (scripts/stack_and_rebound.py, data/stack_and_rebound.json, PIT S&P 1999-2026, real Clear Leader daily parking): realistic (next open, 0.15%/side) today's rules 13.4% -> ETF+bonds 16.6% (halves 10.4->15.5, 16.5->17.8; 2x costs 9.1->11.6); ideal (close, 0.05%) 18.5 -> 22.8%; worst drop ~ same (-27% realistic). +short 17.0, +vol 17.6, all four 17.9 (small, kept out for simplicity). Rebound sleeve (worst sectors after a 15/20% drop, 13 events since 1999) beat SPY in only ~7/13 and lowered returns -> dropped.

### Nov 18: live replay + what to expect (v3.0 doc: https://claude.ai/artifact/6GA9fqscsYJZhTqbNjUhyu)
- scripts/live_replay.py (data/live_replay.json; Alpaca 1Min 15:40-16:00 raw bars cached in R2 alpaca/m1540/<YYYY-MM>; 3,355 calls): 2016-2026 decide 15:45 / fill avg 15:46-15:50 = 25.1% vs ideal close 24.5% (Robinhood rules), v3.0 28.0 vs 28.1; 15:55 decide no better; 2x spread -1.7%/yr; next open 18.8/20.7. 10.6% of signals differ 3:45 vs close; 7.7% minute prices fell back to the close. => plan with ideal minus ~1%: v3.0 ~21-22%, rules ~17-18% (1999-2026, before tax).
- scripts/mc_expect.py (data/mc_expect.json; 5,000 block-bootstrap paths, 21-day blocks): v3.0 realistic 12m losing 16%, p10 12m -3%, worst 12m -18%, 5/28 losing years, longest below high 27 mo, P(20%+ dd in 3y) 33%, P(30%+) 5%, 5y lose 1%; rules 25%/42 mo/39%; SPY 22%/79 mo/62%. Breaker suggestion 40% (live MAX_DRAWDOWN default 0.35).
- stack_and_rebound.py is importable (main block guarded); IDEAL/REAL dicts at module level.

### Bot 9: bonds instead of cash (virtual, from Nov 19)
- In paper-dip.mjs (BOND='IEF', BOND_MA=100, bondParkSymbol), state data/paper_bond_state.json, runs in the 3:45 pm dip run (wrapped in try/catch so it can't break bots 1-8). Bot 1 rules; idle money = Clear Leader when SPY > 100-day avg (as now), else IEF if IEF > its own 100-day avg, else cash. Identical twin keeps cash (same prices/fills). Dashboard card 9. Tests in test-paper-dip.mjs.
- Evidence: scripts/cash_alternatives.py (data/cash_alternatives.json, PIT S&P 1999-2026, SPY stand-in for Clear Leader): cash 13.4%/yr worst -28%; IEF checked 15.1%, -19% (1999-2012 12.5 vs 9.6; 2013-26 17.7 vs 17.3; 2022 0% vs -1%); gold 16.0% but -32% and mostly 2024-26; India plain 10.4%, -73% (2008 -70%); intl/emerging worse than cash. Random fake alternatives spread 11.7-14.7%, so only gaps > ~1.5%/yr count.
- scripts/crash_flows.py (data/crash_flows.json): 12 SPY drops of 10%+ since 1997: mid/long Treasuries up in 8/12 (avg +12.5% in the 4 bears), short Treasuries 9/12, dollar 7/12, gold 4/7, yen 7/12; utilities/staples/low-vol/REITs/intl/India/emerging fall (India 0/7). 2022 = inflation crash: bonds fell, only energy/oil/dollar rose. After bottoms, beaten sectors rebound most (+22-33% in 3 months). FRED times out from Actions (yields/VIX from Yahoo instead).
- Japan check (scripts/japan_tests.py, data/japan_tests.json; idea from Bengal Asset Management, a Japan long/short fund): Clear Leader + EWJ 13.6 vs 13.5 (never picked), + DXJ 12.6 (worse); EWJ already in the ETF dip list (28 trades, +0.94%); dip bot on today's Nikkei 225 (survivorship): +0.71%/trade, 63% win vs random picks ~0%, cash-parked 4.9%/yr -12% vs ~0% random, both halves -> dip effect is real in Japan too, not tradable from Robinhood. Nikkei-ETF-parked version broken by bad 1321.T Yahoo data.

### Bot 8: dip + short-interest filter (virtual, from Nov 16)
- In paper-dip.mjs (SHORT_CUT=5, siCandidates/parseSI/fetchShortInterest/shortFilter), state data/paper_short_state.json, runs in the 3:45 pm dip run. Bot 1 rules but skips dips with FINRA days-to-cover >= 5; an identical unfiltered twin runs on the same prices. FINRA file fetched live each run (newest report >= 12 days old, as in the backtest); if FINRA fails nothing is skipped and si_error is logged. Live fetch verified via finra-probe.yml (Nov 15: report 2026-10-15, 22,537 symbols). Dashboard card 8. Tests in test-paper-dip.mjs.

### India bot (virtual Rs 10 lakh, from Nov 18) - separate from the US bots
- ONE bot (Sai, Nov 17): before-close orders + a morning status message, to avoid two different alerts. scripts/paper_india.py, workflow paper-india.yml ("India bot"), test scripts/test_paper_india.py. Alerts ONLY to secret NTFY_TOPIC_INDIA (no secret = no alert).
- Rules = India best: top 200 NSE by traded value (re-picked Jan/Jul), 12% dip vs Nifty over 5 sessions, above 200-day, volume <= 2x (today's volume is partial at 3 pm), smart exit (close > 5-day avg or 5 sessions), 10 x 10%, whole shares; idle money NIFTYBEES if Nifty > 150-day avg, else GOLDBEES if gold > 100-day avg, else liquid fund (cash at ~6%/yr). Costs 0.30%/side stocks, 0.15% ETFs. Backtest with close fills ~18.3%/yr before tax (next-open fills 16.3%).
- MODE=close ~3:05 pm IST: decides on the latest prices and fills at once, like placing orders before the 3:30 pm close; only 2:45-3:25 pm IST, refuses quotes older than 20 min. Started by the Cloudflare timer '20,40 9 * * 1-5' (5th and last free cron trigger), GitHub backup 09:30 UTC; runs once a day. State data/paper_india_close_state.json.
- MODE=morning 8:15 am IST (GitHub cron 02:45 UTC): holdings, watchlist (8-12% worse than Nifty), account vs Nifty; no orders, no state change.
- MODE=open (next-open variant) kept for manual tests only (bot=A).
### Bot 12: Dip bot v3.2 (virtual, from Nov 20) - scripts/paper-v32.mjs, .github/workflows/paper-v32.yml, data/paper_v32_state.json
- Started by the Cloudflare market clock (site/src/index.js marketJobs; cron */5 14-20 UTC, also starts paper-dip at :25/:40) every 15 min + 3:50/3:55;
  GitHub schedule only a 3:55 backup. Script decides by NY time + Alpaca calendar:
  intraday (10:00 to close-20): v32Intraday = +5% target sells (held >=1 day), dip buys into free slots funded from parking, proceeds re-parked;
  final (close-20 .. close-2, once a day): virtualStep (v3.0 rules, IEF parking) + plain v3.0 twin on the same prices.
- Manual test: dispatch with dry_run=1 phase=intraday|final (does not save state). Tests in test-paper-dip.mjs ("bot 12").
- Backtest: data/intraday_final.json (final run Nov 19: idle money valued by time of day, ETF intraday-only dips via Yahoo lows,
  stock list = day's low vs SPY's day high, year-by-year). v3.0 27.2 -> v3.2 30.5 (2x costs 25.4 -> 27.9), better 9/11 years,
  worse 2023 (-4.6) and 2024 (-7.1). Half-day detection in the replay did NOT trigger (Alpaca shows after-hours bars) - ~3 days/yr, ignored.

### Nov 22 Leverage on single stocks (data/lev_single.json, scripts/lev_single.py; sim(lev=, lev_cost=, lev_trend=) added, default 1x)
- Dip bot v3.0 realistic 1999-2026: 1x 16.6/-27, 1.5x 20.2/-34, 2x 23.7/-41 (ETF-style or margin costs ~same); 2x only when SPY > 100-day 19.7/-41. Return and drop scale together.
- 2x single stocks + 200-day trend, fair (317 S&P members on 2000-01-03, to delisting): 4.8%/yr = 1x hold 4.8; 2x hold 1.9 (142 wiped); 2x trend beat 1x hold in 25% of stocks.
  Hindsight 2x-ETF list: 2x trend 39.4%/yr (pure hindsight). ORCL 2000-2026: 1x 6.6, 2x trend -3.7.
- Real 2x ETFs vs simulation: NVDL +830% vs +1,799% sim, MSFU +53 vs +101, AMZU +35 vs +57, AAPU 125 vs 132, TSLL -65 vs -77, ORCX -85 vs -82 -> real single-stock 2x costs are higher than modeled.

### Nov 22 Robustness of 2x S&P + 200-day trend (data/lev_robust.json) - real but fragile, WATCH
- 16 nearby settings (100-250 day, 0-3% band) on SPY 1994-2026: 7.7-15.4% (median 12.5; chosen 14.4 near the top), 11/16 beat SPY 10.4%; worst drop median -49%.
- Placebo: 10.3% of 1,000 random schedules (same switches/time in) beat it (median 10.6%) -> signal helps, weakly.
- Other markets (2x, 200-day, 2% band vs 1x hold): Nasdaq QQQ 11.4 vs 8.1, NDX 16.4 vs 13.6, EFA 8.6 vs 7.4; FAILS on IWM 5.6 vs 8.0, EEM 5.3 vs 7.4, DIA 4.1 vs 8.2.
- Crashes: much better in slow bears (2000-02 -24 vs -47, 2008 -20 vs -55); worse in fast ones (1998 -25 vs -18, 2011 -22 vs -18, 2015-16 -21 vs -13, 2018Q4 -27 vs -19, 2020 -40 vs -33, 2022 -28 vs -24).
- Start years 1994-2016: beat SPY in 21/23. Costs 0.2%/switch + 1.5% borrow: 13.2%. Verdict: at most a small Roth sleeve.

### Nov 22 Three tests: India after-tax reshuffle/score tweaks (data/india_slowtax.json), managed futures next to v3.0 (data/mf_slice.json), three markets (data/three_markets.json)
- India lot-level tax (current rules all period, Rs 10 lakh): bot 13 best 32.7 -> 27.5 after tax; honest 26.8 -> 22.6. Slower reshuffles do NOT win after tax:
  every 2 months 20.7-21.9, every 3 months 22.2-22.7 (same as monthly, half the trading) but worst drop -39 to -44 vs -34. Letting winners run: +0-0.2 pt, deeper drops. Keep bot 13.
- Score tweaks (honest after tax vs 22.6): skip-month 21.7, 2x6m 21.3, no vol divisor 20.0, residual 19.6 (drop -26), Clenow 14.8, smooth-trend filter 21.6 (drop -26.6). None better; residual/smooth = lower return, smaller drops.
- Managed futures (monthly data; Roth): next to v3.0 a 10-30% AQMIX/DBMF/KMLM slice lowers return roughly in proportion, Sharpe +0.02-0.06, worst drop slightly smaller -> not worth it beside the dip bot.
  Next to SPY it helps a lot (20% MF: worst drop -24 -> -13 to -16, 2022 -18 -> -9/-10). Correlation of MF with v3.0 ~0, with SPY -0.15 to -0.36.
- Leverage + trend (sim validated vs real SSO 14.6 vs 14.4%/yr): SPY 1994-2026 1x hold 10.4/-55; 2x with 200-day+2% band 14.4/-42; 3x band 18.2/-57.5; 2x 10-month 14.0/-45.
  1960-2026 price index: 1x 7.3/-57, 2x band 9.5/-45, 3x band 10.4/-64. 2020 whipsaw (-3.5% for 2x band), 2022 -28 to -31%. Candidate for the Roth core; needs robustness (other MAs, Nasdaq/intl, placebo).
- USD->INR timing (2004-2026, $1k/month, rupee FD 6.5% while waiting is counted): every rule within -0.25..0% of converting on the 1st -> no edge; rupee weakened 3.2%/yr. Send on schedule.
- Nifty vs gold (2009-2026; GOLDBEES Yahoo history starts 2009): Nifty 14.1/-38 (after tax 13.3), gold 11.9/-30, 50/50 13.9/-23, ratio rule 15.3/-26 (after tax 12.2 because switching is taxed yearly).
  Ratio rule: best before tax with a much smaller drop, but loses to plain Nifty after tax. z-score now -0.87 (Nifty not expensive vs gold).
### Nov 22 Research shortlist #1-3 on India momentum (data/india_ideas3.json, india_pit.py MODE=ideas3) - nothing worth changing bot 13 for
- Base bot 13: best 32.6 / -23.8, honest (days 1/6/11/16, next-day) 26.7 / -33.5.
- #2 junk filters (circuit-locked share, bottom-10% turnover, -10% days, -10% on 3x volume, all): all within +-0.5 pt (circuit 20%+ of 60 days +0.5/+0.4 = noise). ASM/GSM/pledge/insider untestable (no history).
- #3 per-slot check (12m > 6% AND above own 200-day): with Nifty filter, fill from next qualifying: best 33.2, honest 27.3 / -32.3 (+0.6, slightly smaller drop - small, consistent); slots to gold: no gain.
  WITHOUT the Nifty filter: honest 29.2 but worst drop -45 -> no.
- #1 low vol (lowest 1-yr vol, top 200/500, 30/50 stocks): 13.2-15.6%/yr (no dividends, so ~1-2 pts low), drops -23 to -33; ~ Nifty. Correlation with momentum 0.49, but blends 70/30, 50/50,
  30/70 = 23.6/21.4/19.0% with drops -29 to -31 (honest momentum alone -33.5) -> blending costs return without cutting drops much. Not adopted.
- Dashboard Nov 22: new top tabs "Start here" (live vs paper vs dropped, paper results) and "Live bot rules" (one-page cheat sheet). Update both when the live rules change (v3.0 switch).
### Nov 22 Paper bot 14: India Alpha 50 (our version) - scripts/paper_india_alpha.py
- Rules = india_pit.py factor-mode rebuild: top 300 by 120-day median traded value (Jan/Jul), 1-yr Jensen alpha vs Nifty (252 days, 200+ traded), top 50 equal weight,
  quarterly on the 1st NSE trading day of Jan/Apr/Jul/Oct, no buffer, no crash filter, 0.3%/side. Twin FILTER=1 (100-day Nifty filter, gold/liquid) -> data/paper_india_alpha_filter_state.json, no alerts.
- Runs inside paper-india-mom.yml (7:15 pm IST) after bot 13; tests: test-india-alpha.py. Alerts: NTFY_TOPIC_INDIA only, quarterly. Started Nov 22 on the Nov 20 close: 50 stocks
  (36 small / 8 mid / 5 large by AMFI), 11 overlap with bot 13. Backtest 22.0%/yr, dd -47 (no trading costs, one version, untested robustness) -> plan 17-20%; after tax ~13.5-16 vs Nifty 13.7.
- Dashboard: card #14 (pb-inalpha), tab 'inalpha' ("India Alpha 50: this quarter's 50", drawInAlpha), calculator row inalpha 22.0/17.9/-47. Doc: https://claude.ai/artifact/TqdML5zaL3kTo7DZK1uLtt
### Nov 22 India factor rotation (#5) + size switch (#7) (data/india_factor.json, india_pit.py MODE=factor) + NIFTY BENCHMARK FIX
- BUG FIXED: summ() measured benchmark curves (Nifty, built from 2007) from 2007 but divided by years since 2009 -> Nifty showed 11.9%; correct 2009-2026 = 14.5% (after tax ~13.7).
  Strategy curves were unaffected (they start at 1 on START). Consequence: India dip bot (14.0%) only MATCHES Nifty (half the drop); after tax Nifty buy & hold wins. Dashboard/calculator fixed.
- Rebuilt (equal-weight, from NSE data) hold 2009-26: Alpha 50 22.0 (dd -47), Momentum 30 20.3 (-39), Low Vol 30 14.3 (-28), Nifty 14.4 (-38). Factors move together (corr 0.78-0.94).
- Best rotation: top factor by 6m return, monthly, crash filter 19.6 / -32; top 2 by 6m monthly + filter 18.8 / -25. Rotation adds ~0-1 pt over holding; the filter cuts drops.
- Size switch (#7, large/mid/small, monthly): 5-9%/yr -> FAILS, drop it.
- VALIDATION vs official NSE TRI (3y/5y to Oct 30 2026): Nifty 7.8/6.5 vs 7.74/6.70 (exact), Low Vol 9.4/8.2 vs 9.79/9.13 (close), Momentum 20.1/14.0 vs 9.41/7.93 and Alpha 20.8/18.2 vs 14.88/11.56 (ours far HIGHER:
  equal weight + traded-value universe tilts to small high-flyers). So the rebuilt Momentum/Alpha numbers OVERSTATE the real ETFs. Official Alpha 50 TRI since 2003: ~20%/yr (back-calculated pre-2012), 5y 11.6%.
- Real funds: Kotak Nifty Alpha 50 ETF (NSE: ALPHA, 0.30%, ~Rs 892 cr), Kotak Nifty Alpha 50 Index Fund (direct 0.35%, since Aug 2025). For friends; PFIC for Sai.
### Nov 22 India via US-listed ETFs for Sai's Roth (#10, data/india_usproxy.json) - NOT worth it
- 2013-03..2026-11, USD, adjusted closes: INDA 6.7%/yr (dd -45), SMIN 10.6 (-60), EPI 8.4, INDY 7.0 vs SPY 13.4 (-34). Rupee fell ~4.4%/yr vs USD -> eats most of India's local return.
- Best rotation: SMIN/GLD/cash best 6-month 13.3% (dd -45, 2020-26 only 9.8); INDA/GLD/cash 6-month 10.8 (-31); global SPY/INDA/GLD/cash 4.5-6.1 (worse than SPY). Nothing beats plain SPY.
- INDA tracks Nifty 50 in USD closely (monthly corr 0.97). Verdict: in the Roth keep the US bot / SPY; India exposure only as a small diversifier if wanted.
- niftyindices.com TRI API (Backpage.aspx/getTotalReturnIndexString) now 302-redirects to a login (Nov 2026) -> official factor TRIs not downloadable; factor test (#5) rebuilt from NSE data instead (india_pit.py MODE=factor).
### Nov 21 India momentum split reshuffle + next-day trading (data/india_momsplit.json) - keep day 1, don't split
- Trade the day AFTER the signal (what friends do): 31.1% / dd -25.7 vs same-day 32.6 / -23.8 -> costs ~1.5 pts.
- Reshuffle day 1..18 (single): median 24.5%, range 20.8-32.6, worst-drop median -41 (worst -55). Best cluster = month turn: day 17/18/1/2 (27-33%); mid-month (days 7-14) worst (20-25%, drops -41 to -55). Smooth cluster, not one spike -> day 1 not pure luck (maybe early-month SIP inflows), but unproven.
- Split money into 2/3/4 parts on different days: 26.7-29.2% (100-day filter), drops -27 to -34. Splitting just AVERAGES the day luck; it does NOT cut drops below day 1 and doubles orders -> not worth it.
- 100-day filter beat 200-day in all 8 split versions (+1.5-2.5 pts, smaller drops). Confirms the Nov 21 switch.
- Honest planning number (4 parts, next-day): 26.7%/yr (~21.6 after tax), worst -33.5. Dashboard "25-28%, -30 to -40%" stays right.
### Nov 21 India momentum robustness (data/india_momrobust.json) - edge is REAL, headline number is optimistic
- Placebo: 200 runs of 20 RANDOM top-500 stocks with the same filter: median 12.4%, max 17.5%, worst drop median -51% -> 0% beat the basket (32.6%).
- 27-version nearby grid: 27.9-32.6% (median 29.7), worst drop median -32.6 (worst -40.5); paper-bot setting is the grid max. All beat Nifty by 5+ pts.
- Start years 2009/12/15/18/21/23: basket 30-33% vs Nifty 11-14% every time. Costs 0.6%/0.9% per side: 30.2 / 27.8%.
- WARNING: reshuffle day matters: day 1 32.6% (dd -24) vs day 5/10/15: 24.1/24.3/24.9% (dd -42/-35/-48). Friends trade the day after the alert ->
  realistic expectation ~25-28% before tax, worst drop -30 to -40%. Next: test signal-on-last-day/trade-day-1 and splitting the reshuffle across days.
### Nov 21 India momentum risk controls (data/india_momrisk.json, 2009-2026, NSE survivorship-free)
- Base (paper bot, 200-day filter at reshuffle): 30.5% dd -37.5 (test 28.4/-26.1). WINNER: 100-day filter at reshuffle: 32.6% dd -23.8, test 36.1/-21.1;
  50/50 with dip 23.4% dd -16.2. 50-day: 27.6/-32.3. Daily filter checks, weekly/2-week reshuffles, stops, trailing stops, basket stops, vol targets,
  30 stocks: all worse or no better (weekly 20.2% dd -58.8). Picked among 19 variants -> some luck; 100-day is the middle MA choice.
### India momentum paper bot (from Nov 20 2026) - scripts/paper_india_mom.py, .github/workflows/paper-india-mom.yml, data/paper_india_mom_state.json
- Picked rules: top 500 NSE by traded value (Jan/Jul re-pick), (6m+12m)/vol, 20 stocks equal weight, first trading day each month at close, buffer top 30,
  crash filter Nifty < 100d (FILTER_MA, changed Nov 21 from 200d; twin with 200d in data/paper_india_mom200_state.json, no alerts) -> GOLDBEES (if gold > 100d) else liquid 6%. 0.30%/side. Rs 10 lakh virtual. Daily 7:15 pm IST cron, catches up missed days.
- Data from NSE bhavcopy R2 cache (tops up the last 40 days). Alerts to NTFY_TOPIC_INDIA (sells / buys with shares per Rs 1 lakh / keeps). Tests: test-india-mom.py.
### Nov 21 India on SURVIVORSHIP-FREE NSE bhavcopy (data/india_pit.json, 2009-2026, R2 nse/bhav/<year>.json.gz; price only, 0.30%/side)
- Splits/bonuses: bhavcopy PREVCLOSE unadjusted -> gaps <= -18% treated as corporate actions (8,442 days); checks vs Yahoo match within dividends.
- Nifty 50 +div 11.9% (dd -38). Dip bot today 14.0% (dd -19.5, ~11.2 after tax, 2019-26 16.1%). NSE filters +0.2; 10-day/17% 13.1% dd -14.1; top 500 worse (7.1%).
- Momentum (6m+12m)/vol, 30 stocks, semi-annual, top 200, no filter = 18.0% (matches NSE's real Nifty200 Momentum 30 ~19% incl. div) -> validates data.
  Top 500 same rules 26.4% (dd -42); crash filters don't cut worst drop much (-42 -> -35 test). Picked on 2009-18 (top 500, vol-adj, 20, monthly, filter, gold): 30.6%, test 28.4/-26.1.
- Mix (picked momentum + dip, corr 0.38): 30/70 19.2% dd -16.8; 50/50 22.5% dd -23.2 (after tax ~18). Nifty/gold/liquid dual momentum 7.9% (< Nifty) -> drop it.
### Nov 21 VIX gate (data/vix_gate.json, v3.0 1999-2026) - not adopted
- No gate 21.9% live-like (13-19: 7.8%). VIX>=15 & calming 22.4% (13-19 8.8, worst -21.0 vs -24.7, 9.6 vs 11.7 trades/mo); realistic 16.6 = same.
- Stricter gates (VIX>=20/25/30, SPY vol>=20/25) lower returns (20.1 -> 15.1). Best 2013-19 only ~9.3% -> gate does NOT fix the dead period.
- Mild version (VIX>=15 calming or SPY 20d vol>=12%) is a wash: slightly smaller worst drop, fewer trades. Optional, not a breakthrough.
### Nov 21 India momentum test (data/india_momentum.json) - NUMBERS INFLATED by survivorship (today's Nifty 500 list)
- Momentum basket raw: top 500 22-39%/yr, top 200 median ~22% (crash-filtered); NSE's real Nifty200 Momentum 30 index = 19.2% vs 15.1% parent (2005-26).
- Crash filter: median worst drop -41% -> -34%, costs ~3-6 pts; hiding in gold-if-trending beats liquid. Monthly > semi-annual here.
- Train-picked (2008-18): top 500, (6m+12m)/vol, 30 stocks, monthly, filter at rebalance, liquid: 32.4% dd -22.7 (test 33.9/-18.3) - inflated.
- Mix with dip bot (13.8%/-18.5): 50/50 23.1% dd -14.1; 30/70 19.3% dd -15.8. Mixing lowers worst drop (low correlation) - this part is robust.
- Practical: friends could hold a Nifty200 Momentum 30 index fund (real track record) next to the dip bot. Sai: no Indian funds (PFIC).
### Nov 21 India time-frame test (data/india_timeframe.json, 2008-2026, realistic fills, before tax)
- Today's India bot (5-day, 12%, smart exit max 5): 13.8%/yr, worst -18.6%, 40 trades/yr. Faster dips are WORSE (1-day 4-6%, 2-day 10-12%).
- 10-day look-back / 17% drop: 13.5-14.7%, worst ~-16%, only 23-27 trades/yr (fewer costs + tax events). Fixed 5-day hold 15.7% but no gain in 2019-26.
- Winners (trend side, 60d look-back, hold 40d): 19.4%/yr, 2019-26 27.9%, but worst -47% (others -48..-62%) and survivorship bias -> needs a crash filter test.
### Nov 20 evening (data/three_tests.json, data/crypto_trend.json)
- Sector-relative dips: all versions worse than vs-SPY (live-like 21.9 -> 19.2-20.4). Keep SPY.
- Stress: v3.0 beta 0.45, own edge ~17%/yr (t 5.4) 1999-2026, BUT ~0 in 2013-2019 (bot 7.8% vs SPY 14.6%). Kill switch 40% confirmed.
- Blend: trend sleeve alone 7.2% (< SPY); blends cut return far more than drawdown. Blend after-tax figures are per-sleeve unrebalanced (not comparable) - ignore.
- Crypto: BTC 10-month rule 60.1%/yr vs hold 48.7 (2014-26), worst -72 vs -83, 2022 +2 vs -65, 1.2 trades/yr; Robinhood Crypto cost barely matters for it.
  ETH rules inconsistent (10-month worse than hold) -> skip.
- BTC robustness (data/crypto_robust.json): lengths 6-14 mo give 44-62%/yr vs hold 48 (7-9 mo below hold -> 10 is a lucky peak); worst drop -66..-73 vs -83 for 6-11 mo;
  check day 49-60%; 1-7 days late 53-58%; daily 100-300 day 55-71% with worst -61..-70; placebo: only 2.8% of random schedules beat it. Start 2023: rule 31 vs hold 37.
  Verdict: reliable crash protection, extra return NOT reliable. 90% SPY + 10% BTC 10-month rule: 18.7% vs SPY 12.9 (2015-26), worst -21.6 vs -23.9.
### Nov 20 tests (data/tax_news_tests.json, v3.0 1999-2026) - no rule changes
- Wash sales: ~16% (live-like) / 22% (realistic) of losing sales washed, but after-tax return unchanged (19.5% live-like, 15.2% realistic;
  17.1% / 12.9% if parking gains are also taxed yearly). 31-day cooldown slightly worse; December cooldown no effect. Real after-tax ratio ~0.78-0.89.
- News proxies (per trade): heavy volume 0.49% vs 0.87% rest; overnight-gap drops 0.63% vs 0.79%; market-up dips 0.47% vs 1.24%; market down 3%+ 2.6%.
  All groups positive; skipping any of them lowers total return (e.g. skip market-up 21.9 -> 18.5). Keep taking all signals.
### Nov 19 late tests (no action taken)
- COMBO (data/intraday_combo.json, 2016-2026 replay): v3.2 30.5 | +2 drift 31.0 (2016-20 24.4 vs 21.9, 2021-26 36.9 vs 38.4, 5/11 years,
  worst -17.6) | +3 drift 30.5. v3.1 vs v3.0 here only +0.3 (2021-26 worse by 2.8) -> drift edge weak lately; not added to v3.2.
  Slots: 8x12.5% 31.2 (deeper drop), 12x8.3% 29.1, 15x6.7% 28.4, 12x10% 31.0 -> keep 10x10%. Dip size: 9% 28.7, 10% 30.5, 11% 29.5, 12% 29.0 -> keep 10%.
- Same-day selling (data/intraday_sameday.json, SAME_DAY=1): v3.2 30.5 -> 31.1 with same-day +5% sells, but only ~5 such sells a year and
  better in just 3 of 11 years (gain = 2020 + 2026); +3% same-day target worse (30.3); 3-per-5-days cap changes nothing. Not adopted
  (also H-1B caution: Sai keeps no same-day round trips on the live account).
- India intraday (data/india_intraday.json, 60 days of Yahoo 5-min, Aug 25-Nov 20 2026): the India bot itself lost ~8.6% in that window
  (17 trades, 35% wins); intraday buys / +5% target ~same (-8.8 / -9.1). Per signal: waiting until 3:10 was 0.38% cheaper (t -1.45);
  dips that recovered by 3:10 made +2.8% next day (n 13). No case for intraday in India; friends trade by hand anyway.

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

## Nov 22 FIX: Cloudflare cron weekdays
- Cloudflare cron weekday numbers are 1 = SUNDAY ... 7 = Saturday (docs). Every '* * 1-5' timer ran Sun-Thu: Fridays were skipped (paper dip bots, v3.2, drift pre-market, India dip bot) and Sundays fired (harmless: bots exit off-hours).
  Fixed to MON-FRI in site/wrangler.toml AND the matching keys in site/src/index.js (the worker maps jobs by the exact cron string). The live Robinhood bot (VM systemd timers) was not affected.

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
