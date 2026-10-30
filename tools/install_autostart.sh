#!/usr/bin/env bash
# Start the physics display automatically at boot (systemd service).
#
#   bash tools/install_autostart.sh            # install and start now
#   bash tools/install_autostart.sh --remove   # turn autostart off
#
# After installing:
#   sudo systemctl stop physics-display      # stop it (e.g. to run a scene by hand)
#   sudo systemctl start physics-display     # start it again
#   sudo systemctl restart physics-display   # restart (e.g. after git pull)
#   journalctl -u physics-display -f         # watch its output / errors
set -euo pipefail

NAME=physics-display
UNIT=/etc/systemd/system/$NAME.service

if [[ "${1:-}" == "--remove" ]]; then
    sudo systemctl disable --now "$NAME" 2>/dev/null || true
    sudo rm -f "$UNIT"
    sudo systemctl daemon-reload
    echo "Autostart removed."
    exit 0
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
PY="$REPO/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

echo "Repo:   $REPO"
echo "User:   $USER_NAME"
echo "Python: $PY"

sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=Physics display (touch scenes on the Waveshare panel)
# no network dependency: the screen starts right away, the panel works once Wi-Fi is up

[Service]
User=$USER_NAME
SupplementaryGroups=video render input
WorkingDirectory=$REPO
Environment=PYTHONUNBUFFERED=1
# hide the console's blinking cursor so it doesn't flicker over the scene (runs as root)
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/graphics/fbcon/cursor_blink || true'
# no scene name: start the last scene that was showing
# --gpu draws through the GPU with vsync, and falls back to the framebuffer if that fails
ExecStart=$PY $REPO/run.py --gpu
# restart after a crash, but not after a clean stop (Stop button, or a manual run taking over)
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$NAME"
sudo systemctl restart "$NAME"
sleep 2
systemctl --no-pager --lines=5 status "$NAME" || true
echo
echo "Autostart installed. It will start the last scene at every boot."
