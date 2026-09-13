#!/usr/bin/env bash
# Attiva l'aggiornamento locale automatico di OBYN per l'utente corrente.
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_NAME="obyn-local-update.service"
PATH_NAME="obyn-local-update.path"

mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/$SERVICE_NAME" <<EOF
[Unit]
Description=Aggiorna l'installazione locale di OBYN dopo una modifica dei sorgenti

[Service]
Type=oneshot
ExecStart=/usr/bin/env bash $SOURCE_DIR/install-local.sh
EOF

cat > "$UNIT_DIR/$PATH_NAME" <<EOF
[Unit]
Description=Osserva i sorgenti locali di OBYN

[Path]
PathChanged=$SOURCE_DIR/locale/en/LC_MESSAGES/obyn.mo
PathChanged=$SOURCE_DIR/locale/it/LC_MESSAGES/obyn.mo
PathChanged=$SOURCE_DIR/src/obyn.py
PathChanged=$SOURCE_DIR/src/obyn_tray.cpp
PathChanged=$SOURCE_DIR/data/io.obyn.Bluetooth.desktop
PathChanged=$SOURCE_DIR/install-local.sh
Unit=$SERVICE_NAME

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$PATH_NAME"
systemctl --user start "$SERVICE_NAME"

echo 'Aggiornamento automatico OBYN attivato.'
echo 'Ogni modifica ai sorgenti locali reinstalla OBYN in ~/.local/bin.'
