#!/usr/bin/env bash
# Disattiva l'aggiornamento locale automatico di OBYN.
set -euo pipefail

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
systemctl --user disable --now obyn-local-update.path 2>/dev/null || true
rm -f "$UNIT_DIR/obyn-local-update.path" "$UNIT_DIR/obyn-local-update.service"
systemctl --user daemon-reload
echo 'Aggiornamento automatico OBYN disattivato.'
