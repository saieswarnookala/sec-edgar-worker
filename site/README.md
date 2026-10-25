# Sentinel website

The Sentinel dashboard as a private website on Cloudflare Workers, with username + password logins.

- **URL:** `https://sentinel-web.<your-workers-subdomain>.workers.dev`
- **Main admin:** username `admin`, password = the `SENTINEL_ADMIN_PASSWORD` GitHub secret
- **Add people:** sign in as admin → **Users** → username + password (10+ characters) → Save. Saving an existing name resets the password and signs that person out everywhere.

## How it works
- `src/index.js`: every request goes through the Worker first; nothing but `/login` is served without a session.
- `src/auth.js`: PBKDF2-SHA256 password hashes in KV (`AUTH`), 7-day HttpOnly/Secure session cookies, lockout after 5 wrong passwords (15 min).
- `src/data.js`: live feeds for Stock analysis: SEC EDGAR statements (shared code in `../src/worker.js`), Alpaca daily prices, FMP profile (falls back to SEC details without a key).
- `dashboard/page.html`: the same page as the Claude dashboard; `dashboard/runtime.js` stands in for the Claude runtime.
- `build.mjs`: wraps the page and copies the data files built by the other GitHub Actions into `public/data/`.

## Deploy (GitHub Action "Deploy website")
Runs on every push to `site/`, `src/` or `data/`, after each data-building Action, or manually.
Repo secrets it needs: `CLOUDFLARE_API_TOKEN`, `SENTINEL_ADMIN_PASSWORD`, plus the existing `SEC_USER_AGENT`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`; optional `FMP_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`.

## Updating the dashboard page
When the Claude dashboard changes, copy its page into `dashboard/page.html` and push.

## Tests
`node site/test.mjs` (18 checks: sign-in, roles, lockout, password reset, sessions, headers, data formats).
