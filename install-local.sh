#!/usr/bin/env bash
# Installa OBYN soltanto per l'utente corrente, senza dipendere da ADA.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$BIN_DIR" "$APPS_DIR" "$ICON_DIR/scalable/apps" "$ICON_DIR/scalable/status"
install -m 0644 "$SCRIPT_DIR/data/io.obyn.Bluetooth.svg" "$ICON_DIR/scalable/apps/"
install -m 0644 "$SCRIPT_DIR/data/io.obyn.Bluetooth-symbolic.svg" "$ICON_DIR/scalable/status/"
if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "$ICON_DIR" >/dev/null 2>&1 || true
fi
# Install catalogs before the executable so the watcher never exposes missing translations.
for language in it en; do
  install -Dm644 "$SCRIPT_DIR/locale/$language/LC_MESSAGES/obyn.mo" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/obyn/locale/$language/LC_MESSAGES/obyn.mo"
done
install -m 0755 "$SCRIPT_DIR/src/obyn.py" "$BIN_DIR/obyn"
g++ -std=c++17 -O2 -fPIC -pie "$SCRIPT_DIR/src/obyn_tray.cpp" -o "$BIN_DIR/obyn-tray" \
  -I/usr/include/qt6 -I/usr/include/qt6/QtCore -I/usr/include/qt6/QtGui \
  -I/usr/include/qt6/QtWidgets -I/usr/include/KF6 -I/usr/include/KF6/KStatusNotifierItem \
  -lKF6StatusNotifierItem -lQt6Widgets -lQt6Gui -lQt6Core
install -m 0644 "$SCRIPT_DIR/data/io.obyn.Bluetooth.desktop" \
  "$APPS_DIR/io.obyn.Bluetooth.desktop"
# KDE non eredita sempre ~/.local/bin nel PATH: il launcher deve quindi usare
# il percorso assoluto dell'installazione utente.
sed -i "s|^Exec=obyn$|Exec=$BIN_DIR/obyn|" "$APPS_DIR/io.obyn.Bluetooth.desktop"

echo "OBYN installato per l'utente corrente."
echo "Se necessario, aggiungi $BIN_DIR alla variabile PATH e riapri la sessione."
