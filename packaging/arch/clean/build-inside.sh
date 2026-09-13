#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Solo dentro un container Arch usa-e-getta: non eseguire sull'host.
set -euo pipefail
[[ -f /run/.containerenv && -f /input/PKGBUILD ]]
mkdir -p /results /build
version=$(sed -n 's/^[[:space:]]*pkgver = //p' /input/.SRCINFO)
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
export OBYN_EXPECTED_VERSION="$version"
cp /input/PKGBUILD "/input/obyn-$version.tar.gz" /build/
cp /input/.SRCINFO /results/input.SRCINFO
# Legge i nomi da metadati, senza eseguire la ricetta come root.
mapfile -t dependencies < <(sed -n 's/^[[:space:]]*\(depends\|makedepends\|checkdepends\) = //p' /input/.SRCINFO | sort -u)
pacman-key --init
pacman-key --populate archlinux
pacman -Syu --needed --noconfirm "${dependencies[@]}"
pacman -Q > /results/packages-before-build.txt
useradd --create-home builder
chown -R builder:builder /build
runuser -u builder -- bash -c 'cd /build && SOURCE_DATE_EPOCH=1789171200 makepkg --cleanbuild --force --noconfirm --log'
cp /build/*.pkg.tar.zst /results/
cp /build/*.log /results/
package=(/results/obyn-*.pkg.tar.zst)
# Upgrade from the preserved package, if mounted read-only by the caller.
if [[ -f /previous/old.pkg.tar.zst ]]; then
  pacman -U --noconfirm /previous/old.pkg.tar.zst
  /usr/bin/obyn --version > /results/previous-version.txt
  runuser -u builder -- python - <<'CONFIG'
import json
from pathlib import Path
p = Path.home() / '.config/obyn/config.json'
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({'auto_connect': 'AA:BB:CC:DD:EE:FF', 'theme_hue': 285,
                         'hidden_devices': ['00:11:22:33:44:55']}))
CONFIG
  cp /home/builder/.config/obyn/config.json /results/config-before.json
fi
pacman -U --noconfirm "${package[0]}"
pacman -Qk obyn
/usr/bin/obyn --version
python - <<'PY'
import importlib.machinery, importlib.util
loader = importlib.machinery.SourceFileLoader('obyn_check', '/usr/bin/obyn')
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
import os
assert module.__version__ == os.environ['OBYN_EXPECTED_VERSION']
module._lingue.configure('en')
assert module._lingue.catalog_loaded
assert module.tr('Connesso') == 'Connected'
module._lingue.configure('it')
assert module.tr('Connesso') == 'Connesso'
print('Cataloghi installati italiano/inglese: OK')
print('Import GTK/Gio e backend installato: OK (nessuna app avviata)')
PY
if [[ -f /results/config-before.json ]]; then
  cmp /results/config-before.json /home/builder/.config/obyn/config.json
  runuser -u builder -- python - <<'CONFIG'
import importlib.machinery, importlib.util
from pathlib import Path
from types import SimpleNamespace
loader = importlib.machinery.SourceFileLoader('obyn_config_check', '/usr/bin/obyn')
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
config = m.ObynApplication.carica_config(SimpleNamespace(config_path=Path.home()/'.config/obyn/config.json'))
assert config['auto_connect'] == 'AA:BB:CC:DD:EE:FF'
assert m.tonalita_valida(config['theme_hue']) == 285
assert config['hidden_devices'] == ['00:11:22:33:44:55']
print('Configurazione e tema letti dalla nuova versione: OK')
CONFIG
  printf '%s\n' 'PASS: aggiornamento vecchio pacchetto, configurazione identica e tema letto' > /results/UPGRADE.txt
fi
ldd /usr/bin/obyn-tray > /results/tray-libraries.txt
if grep -q 'not found' /results/tray-libraries.txt; then exit 1; fi
desktop-file-validate /usr/share/applications/io.obyn.Bluetooth.desktop
pacman -U --noconfirm "${package[0]}"
pacman -R --noconfirm obyn
test ! -e /usr/bin/obyn
test ! -e /usr/bin/obyn-tray
if [[ -f /results/config-before.json ]]; then
  cmp /results/config-before.json /home/builder/.config/obyn/config.json
fi
printf '%s\n' 'PASS: build clean, tests, installazione, import, reinstallazione, rimozione' > /results/RESULT.txt
