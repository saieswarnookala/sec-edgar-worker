# sec-edgar-mcp (Cloudflare Worker)

SEC EDGAR financials as an MCP server. Free plan, no AWS.

## Deploy (first time)
```bash
npm i -g wrangler        # or use npx
npx wrangler login
npx wrangler secret put SEC_USER_AGENT     # "Sai you@email.com" (SEC requires a contact)
npx wrangler secret put ACCESS_TOKEN       # openssl rand -hex 24
npx wrangler deploy
```
Updates later: just `npx wrangler deploy`.

## Test
```bash
curl https://sec-edgar-mcp.<you>.workers.dev/health
curl "https://sec-edgar-mcp.<you>.workers.dev/api/<TOKEN>/financials?symbol=LULU"
```

## Add to Claude
Settings → Connectors → Add custom connector → URL:
`https://sec-edgar-mcp.<you>.workers.dev/mcp/<TOKEN>`

## Tools
- `get_financials(symbol)` → rows (annual ~11 FY, quarterly ~24 Q): revenue, gross_profit,
  operating_income, ebit, interest_expense, net_income, operating_cf, capex (+), total_assets,
  current_assets, current_liabilities, equity, cash, borrowings (excl. leases), leases,
  debt_total, long_term_debt, current_long_term_debt, shares
- `lookup_company(symbol)` → cik, name, exchange, sic, sic_description, fiscal_year_end

## Notes
- Quarters are true 3-month values: YTD 6M/9M differences resolved, Q4 = FY − 9M.
- Free-plan limits: 10 ms CPU, 50 subrequests → uses small per-concept SEC files, not companyfacts.
- Results cached 12h in KV (`CACHE`). Bump CACHE_VERSION in worker.js to invalidate.
- borrowings/leases = 0 when a balance sheet exists but nothing is reported at that date.

## Screener (get_screen)
A GitHub Action (`.github/workflows/screen.yml`) runs `scripts/build-screen.mjs` each weekday after the close
and commits `data/screen.json`. The Worker's `get_screen` tool serves that file from `SCREEN_URL`.

Setup:
1. Push this folder to a **public** GitHub repo named `sec-edgar-worker`.
2. Repo → Settings → Secrets and variables → Actions → New secret `SEC_USER_AGENT` = `Sai you@email.com`.
3. Actions tab → "Build screener" → Run workflow (first build).
4. Put your GitHub username in `SCREEN_URL` in wrangler.toml, then `npx wrangler deploy`.

Rules: profitable both years, sales growth ≥ 5%, profit growth > 0, net margin ≥ 3%, P/E ≤ 200, price ≥ $1.
Buckets: Mega ≥ $200B, Large $10–200B, Mid $2–10B, Small $300M–2B, Micro $50–300M. Top 15 by P/E each.
