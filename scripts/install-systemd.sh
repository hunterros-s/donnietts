#!/usr/bin/env bash
# Installs DonnieTTS as systemd user services.
#
# Creates two units:
#   donnietts-speech.service  - the Qwen speech service
#   donnietts.service         - controller API + announcement worker (donnietts run)
#
# Usage: scripts/install-systemd.sh [--start]
#
# Prerequisites: run `uv sync --frozen` in the repo root and in
# services/qwen-speech so the .venv binaries exist. The speech service
# downloads the Qwen model on its first start.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROLLER_BIN="$REPO_ROOT/.venv/bin/donnietts"
SPEECH_BIN="$REPO_ROOT/services/qwen-speech/.venv/bin/qwen-speech"

for binary in "$CONTROLLER_BIN" "$SPEECH_BIN"; do
  if [ ! -x "$binary" ]; then
    echo "Missing $binary" >&2
    echo "Run 'uv sync --frozen' in the repo root and in services/qwen-speech first." >&2
    exit 1
  fi
done

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/donnietts-speech.service" <<EOF
[Unit]
Description=DonnieTTS speech service (Qwen)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT/services/qwen-speech
ExecStart=$SPEECH_BIN serve
EnvironmentFile=-$HOME/.config/donnietts/env
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/donnietts.service" <<EOF
[Unit]
Description=DonnieTTS controller (API + worker)
After=network-online.target donnietts-speech.service

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT
ExecStart=$CONTROLLER_BIN run
EnvironmentFile=-$HOME/.config/donnietts/env
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload

if [ "${1:-}" = "--start" ]; then
  systemctl --user enable --now donnietts-speech donnietts
  loginctl enable-linger "$(id -un)" 2>/dev/null || true
  echo "Installed and started. Check with: systemctl --user status donnietts"
  echo "Logs: journalctl --user -u donnietts -f"
else
  echo "Installed units (not started). To start and enable at boot:"
  echo "  systemctl --user enable --now donnietts-speech donnietts"
  echo "  loginctl enable-linger $(id -un)   # run at boot without login"
fi

echo
echo "Optional overrides go in ~/.config/donnietts/env (e.g. TTS_BASE_URL=..., DONNIETTS_DB_PATH=...)."
