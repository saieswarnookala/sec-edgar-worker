#!/usr/bin/env bash
# One-shot setup for the live dip bot on a fresh Oracle Cloud Ubuntu VM (Always Free). Safe to re-run.
# Usage (on the VM):  curl -fsSL https://raw.githubusercontent.com/saieswarnookala/sec-edgar-worker/main/live/setup-vm.sh | bash
set -euo pipefail
REPO=https://github.com/saieswarnookala/sec-edgar-worker.git
DIR="$HOME/sec-edgar-worker"; CFG="$HOME/.sentinel-live"

echo "== packages"
sudo apt-get update -qq
sudo apt-get install -y -qq git curl ca-certificates chrony >/dev/null
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - >/dev/null
  sudo apt-get install -y -qq nodejs >/dev/null
fi
sudo timedatectl set-ntp true || true

echo "== code"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; else git clone -q "$REPO" "$DIR"; fi
cd "$DIR/live" && npm ci --silent
if [ "${INSTALL_CLAUDE:-1}" = "1" ] && ! command -v claude >/dev/null; then
  echo "== Claude Code (fallback way to reach Robinhood)"; sudo npm install -g --silent @anthropic-ai/claude-code
fi

echo "== config"
mkdir -p "$CFG" && chmod 700 "$CFG"
if [ ! -f "$CFG/config.env" ]; then
  cat > "$CFG/config.env" <<'CONF'
# Live dip bot settings. Keep this file private (chmod 600).
LIVE_MODE=dry                 # dry = plan + alerts only. Change to live only when Claude/Sai agree.
RH_ACCOUNT=                   # agentic account number (from: node live-dip.mjs doctor)
APCA_API_KEY_ID=              # Alpaca keys, market data only (free account is fine)
APCA_API_SECRET_KEY=
NTFY_TOPIC=                   # your ntfy topic for phone alerts
HC_PING_URL=                  # optional: healthchecks.io ping URL (alerts you if the VM itself dies)
MAX_DRAWDOWN=0.35             # stop everything if the account falls 35% from its peak
# MAX_ORDER_USD=200           # default: 20% of the account per order
# EQUITY_CAP=1000             # only trade this much even if the account holds more
EXECUTOR=direct               # direct = our code talks to Robinhood; claude = go through official Claude Code (fallback)
CONF
fi
chmod 600 "$CFG/config.env"

echo "== timers (New York time; a missed run is NOT re-run late)"
U="$HOME/.config/systemd/user"; mkdir -p "$U"
unit() { # name command
  cat > "$U/dip-$1.service" <<SVC
[Unit]
Description=dip bot $1
[Service]
Type=oneshot
WorkingDirectory=$DIR/live
EnvironmentFile=$CFG/config.env
ExecStart=/usr/bin/node live-dip.mjs $2
TimeoutStartSec=600
SVC
}
timer() { # name calendar...
  local name=$1; shift
  { echo "[Unit]"; echo "Description=dip bot $name timer"; echo "[Timer]"; for c in "$@"; do echo "OnCalendar=$c"; done
    echo "Persistent=false"; echo "AccuracySec=1s"; echo "[Install]"; echo "WantedBy=timers.target"; } > "$U/dip-$name.timer"
}
unit health health;  timer health "Mon..Fri 08:45 America/New_York"
unit trade trade;    timer trade  "Mon..Fri 15:47 America/New_York" "Mon..Fri 15:52 America/New_York"
unit verify verify;  timer verify "Mon..Fri 16:35 America/New_York"
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now dip-health.timer dip-trade.timer dip-verify.timer >/dev/null

echo "== self-test (fake broker, no real account)"
node test-live.mjs | tail -1
echo
echo "Done. Next steps:"
echo "  1) nano $CFG/config.env   (fill in keys and ntfy topic)"
echo "  2) From your laptop: ssh -L 8765:localhost:8765 ubuntu@<vm-ip>   then on the VM: cd $DIR/live && node live-dip.mjs login"
echo "  3) node live-dip.mjs doctor   and send Claude the schema + mapping lines"
systemctl --user list-timers 'dip-*' --no-pager || true
