#!/bin/bash
# Builds the screener on this Mac and uploads it to the Worker's KV. Run any time (e.g. once a day after the close).
set -e
cd "$(dirname "$0")"
export SEC_USER_AGENT="${SEC_USER_AGENT:-Sai sai.eswar27@gmail.com}"
node scripts/build-screen.mjs data/screen.json
npx wrangler kv key put screen --path=data/screen.json --binding=CACHE --remote
echo "✓ Screener uploaded"
