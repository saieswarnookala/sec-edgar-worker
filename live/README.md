# Live dip bot on Robinhood (Oracle Cloud VM)

Runs the **dip + smart exit + parking** strategy with real money in a Robinhood **agentic (MCP) account**.
The strategy code (`scripts/paper-dip.mjs`) decides every order, the same code the backtest and the Alpaca paper bot use.
This folder only checks limits, places that exact list through Robinhood's official MCP tools, and verifies it.
No AI picks stocks or sizes orders. Not financial advice; you can lose the money in the account.

## Lessons from other people's bots, and what this does about them

| What went wrong for others | What this bot does |
|---|---|
| Bot silently didn't run (laptop asleep, app closed) | Always-on Oracle VM, systemd timers, healthchecks.io dead-man alert if the VM goes quiet |
| Cash account stuck waiting for settlement | Open the agentic account as **limited margin**; buys are sized to real buying power after sells |
| Login expired mid-day, bot opened 67 sign-in tabs | Refreshes the token itself; if sign-in is needed it **never opens a browser**, places nothing and alerts you |
| AI picked stocks, sizing bugs | Plain code places orders; hard limits: max $ per order, stock universe only, can't sell more than held, max 25 orders |
| Double orders from overlapping runs | One run at a time (lock), once per day, skips any order Robinhood already has for today |
| "Success" reply but nothing happened | Verify step after the close reads Robinhood's order history; unfilled orders and fill vs closing price are reported |
| Unknown orders appear | Verify halts the bot if the account has orders it didn't place |
| A bad day keeps going | Drawdown breaker: halts if the account falls 35% from its peak (backtest worst was -28%) |

## Schedule (New York time, weekdays)
- 8:45 am  `health`: login + account check, phone alert if anything is wrong
- 3:47 pm  `trade` (backup run 3:52): sells first, then buys, all done before 3:58:45 so they fill near the close
  (on 1 pm half days, like the day after Thanksgiving, the same happens at 12:47 / 12:52, using the market calendar's real close)
- 4:35 pm  `verify`: fills vs close, unfilled orders, stranger orders

A missed run is never re-run late.

## Set up the VM (about 20 minutes)
1. **Oracle Cloud account** at cloud.oracle.com (Always Free). Pick a home region near Dallas (US East Ashburn or US West Phoenix are fine).
2. **Create instance**: Compute, Instances, Create. Image **Canonical Ubuntu 24.04**. Shape **VM.Standard.A1.Flex** (Ampere, 1 OCPU, 6 GB, free) or **VM.Standard.E2.1.Micro** if A1 is out of capacity. Add your SSH public key. Keep the default network (only SSH open).
3. **Connect**: `ssh ubuntu@<public-ip>`
4. **Install**: `curl -fsSL https://raw.githubusercontent.com/saieswarnookala/sec-edgar-worker/main/live/setup-vm.sh | bash`
5. **Config**: `nano ~/.sentinel-live/config.env` (Alpaca data keys, ntfy topic, optional healthchecks URL). Leave `LIVE_MODE=dry`.
6. **Optional dead-man alert**: free check at healthchecks.io, schedule "weekdays 8:45 am New York", grace 1 hour, ntfy integration; put the ping URL in `HC_PING_URL`.

## Connect Robinhood (once)
1. On a computer: robinhood.com, open the **agentic / MCP account** as **limited margin**, fund it ($1,000 planned).
2. In the MCP account's Agent Settings turn **Trade approvals ON** for the first week.
3. From your laptop: `ssh -L 8765:localhost:8765 ubuntu@<public-ip>`, then on the VM: `cd ~/sec-edgar-worker/live && node live-dip.mjs login`, open the printed link on your laptop and sign in.
4. `node live-dip.mjs doctor`: put the agentic account number in `RH_ACCOUNT`, send Claude the `place_equity_order_schema` and the two mapping lines (no balances needed).

## Fallback: official Claude Code connection
If the direct connection has any trouble, switch every Robinhood call to the official Claude Code + Robinhood MCP route.
Our code still decides every order; each call runs Claude Code allowed to use exactly one Robinhood tool, and the bot checks
from Claude Code's own event log that it made exactly one call, to that tool, with exactly our arguments.
Any difference halts the bot. (It can only be caught after the call, so keep Robinhood trade approvals ON in this mode at first.)
1. On the VM: `claude` and sign in to your Claude account, then `/exit`.
2. `claude mcp add -s user --transport http robinhood https://agent.robinhood.com/mcp/trading`
3. `claude`, then `/mcp`, select robinhood, authenticate (use the SSH tunnel if it asks for a localhost callback), `/exit`.
4. In `config.env` set `EXECUTOR=claude`, then `node live-dip.mjs doctor`.
Each run makes about 15-30 short Claude Code calls, which count toward your Claude usage.

## Rollout
1. **Dry week**: `LIVE_MODE=dry`. Daily phone alerts show exactly what it would have traded. Compare with the paper bot.
2. **Approval week**: `LIVE_MODE=live` with Robinhood trade approvals ON: you tap approve on each order.
3. **Hands-off**: approvals OFF. Watch the 4:35 pm verify alerts.

## Strategy version (Nov 23 2026)
`LIVE_STRATEGY=v1` (default): S&P 500 dips + idle money in the Clear Leader ETF, cash when SPY is weak.
`LIVE_STRATEGY=v3`: paper bot 10 rules: same stock dips, plus ETF dips (29 index/sector/country ETFs down 5%+ in 5 days, max 10 days) in free
slots, and IEF bonds instead of cash when SPY is below its 100-day average (if IEF is above its own). An ETF that is today's parking ETF is never also an ETF dip.
Switch: `echo 'LIVE_STRATEGY=v3' >> ~/.sentinel-live/config.env`, then `node live-dip.mjs preview`. Back: delete that line.
`preview` = today's full plan on real data right now, sent to your phone as PREVIEW: places nothing, saves nothing, never halts.
Parking buys (Clear Leader / IEF) may be most of the account; only dip buys have the 20% per-order cap (fixed Nov 23: a parking switch used to halt the bot).
`LIVE_STRATEGY=v32`: v3 at 3:47 pm, plus `intraday` every 15 min (systemd `dip-intraday.timer`, 10:00 ET to 20 min before the close) = paper bot 12 rules:
sell a dip position at +5% over its buy price only if held >= 1 trading day (never a same-day round trip); buy new stock dips, then ETF dips,
into free slots (10% each), funded from cash, then by selling part of the parking ETF. Positions from v3.0 have no recorded buy price: Robinhood's
average buy price is used. The 3:47 run treats today's intraday orders as its own (not duplicates) and never sells what was bought today.
One error alert per problem per day; a dry day alerts only when the plan changes. `preview-intraday` = one check now, nothing placed or saved.
Dry day first: also add `INTRADAY_MODE=dry` (3:47 run stays live with v3.0 rules, daytime checks only send what they would do). Remove that line to go live.
Switch: `sed -i 's/^LIVE_STRATEGY=.*/LIVE_STRATEGY=v32/' ~/.sentinel-live/config.env`, re-run setup-vm.sh once (adds the timer). Logs: `journalctl --user -u dip-intraday -n 50`.

## Commands (on the VM, in ~/sec-edgar-worker/live)
`node live-dip.mjs status` · `preview` · `preview-intraday` · `health` · `doctor` · `login` · `halt` (kill switch) · `resume` · `node test-live.mjs` (fake broker)
Instant stop from anywhere: disconnect the agent in the Robinhood app.
Logs: `journalctl --user -u dip-trade -n 100`

## If Oracle reclaims the free VM
Create a new one and repeat setup + login (about 15 minutes). Upgrading the Oracle account to pay-as-you-go (add a card, stay inside free limits, set a $1 budget alert) stops idle reclaiming.
