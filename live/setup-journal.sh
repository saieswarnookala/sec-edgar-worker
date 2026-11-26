#!/usr/bin/env bash
# Adds ONLY the shadow-journal hand-off timer (4:50 pm ET weekdays). Does not touch the trade/verify/intraday/health units or config.
set -euo pipefail
DIR="$HOME/sec-edgar-worker"; U="$HOME/.config/systemd/user"; mkdir -p "$U"
cat > "$U/dip-journal.service" <<SVC
[Unit]
Description=dip bot shadow-journal hand-off (read-only)
[Service]
Type=oneshot
WorkingDirectory=$DIR/live
ExecStart=/usr/bin/node export-journal.mjs
TimeoutStartSec=120
SVC
cat > "$U/dip-journal.timer" <<TMR
[Unit]
Description=dip bot shadow-journal hand-off timer
[Timer]
OnCalendar=Mon..Fri 16:50 America/New_York
Persistent=false
[Install]
WantedBy=timers.target
TMR
systemctl --user daemon-reload
systemctl --user enable --now dip-journal.timer >/dev/null
systemctl --user list-timers dip-journal.timer --no-pager | head -3
grep -q '^JOURNAL_TOKEN=.\+' "$HOME/.sentinel-live/config.env" && echo "JOURNAL_TOKEN found in config.env" || echo "Add JOURNAL_TOKEN=<token> to ~/.sentinel-live/config.env (same value as the GitHub secret)"
