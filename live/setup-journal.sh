#!/usr/bin/env bash
# Adds ONLY the private shadow-journal timer (4:50 pm ET weekdays). Does not touch the trade/verify/intraday/health units or config.
set -euo pipefail
DIR="$HOME/sec-edgar-worker"; U="$HOME/.config/systemd/user"; mkdir -p "$U"
cat > "$U/dip-journal.service" <<SVC
[Unit]
Description=dip bot shadow journal (read-only, private)
[Service]
Type=oneshot
WorkingDirectory=$DIR/live
ExecStart=/usr/bin/node journal.mjs
TimeoutStartSec=120
SVC
cat > "$U/dip-journal.timer" <<TMR
[Unit]
Description=dip bot shadow journal timer
[Timer]
OnCalendar=Mon..Fri 16:50 America/New_York
Persistent=false
[Install]
WantedBy=timers.target
TMR
systemctl --user daemon-reload
systemctl --user enable --now dip-journal.timer >/dev/null
systemctl --user list-timers dip-journal.timer --no-pager | head -3
echo "Journal file: ~/.sentinel-live/journal.md  (optional in config.env: SEC_USER_AGENT=\"Your Name you@email\", ANTHROPIC_API_KEY=...)"
