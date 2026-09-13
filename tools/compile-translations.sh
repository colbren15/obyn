#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for language in it en; do
  mkdir -p "$root/locale/$language/LC_MESSAGES"
  msgfmt --check --check-format "$root/po/$language.po" -o "$root/locale/$language/LC_MESSAGES/obyn.mo"
done
