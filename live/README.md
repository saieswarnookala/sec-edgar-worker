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

## Commands (on the VM, in ~/sec-edgar-worker/live)
`node live-dip.mjs status` · `health` · `doctor` · `login` · `halt` (kill switch) · `resume` · `node test-live.mjs` (fake broker)
Instant stop from anywhere: disconnect the agent in the Robinhood app.
Logs: `journalctl --user -u dip-trade -n 100`

## If Oracle reclaims the free VM
Create a new one and repeat setup + login (about 15 minutes). Upgrading the Oracle account to pay-as-you-go (add a card, stay inside free limits, set a $1 budget alert) stops idle reclaiming.
