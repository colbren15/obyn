#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
xgettext --language=Python --from-code=UTF-8 --keyword=tr --keyword=ngettext:1,2 \
  --package-name=OBYN --package-version=0.1.2 -o po/obyn.pot src/obyn.py
for language in it en; do
  msgmerge --update --backup=none "po/$language.po" po/obyn.pot
done
