#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Crea tar sorgenti deterministico e aggiorna il checksum del PKGBUILD locale."""
import ast
import gzip
import hashlib
import io
from pathlib import Path
import re
import tarfile


def main():
    package_dir = Path(__file__).resolve().parent
    repo = package_dir.parents[1]
    recipe = package_dir / 'PKGBUILD'
    text = recipe.read_text()
    version = re.search(r'^pkgver=([0-9.]+)$', text, re.M).group(1)
    source = (repo / 'src/obyn.py').read_text()
    tree = ast.parse(source)
    actual = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))
    if actual != version:
        raise SystemExit(f'Versione Python {actual} diversa dal PKGBUILD {version}')
    paths = [Path(n) for n in ('src/obyn.py', 'src/obyn_tray.cpp', 'LICENSE', 'README.md', 'CHANGELOG.md', 'AUTHORS.md', 'README.en.md')]
    paths += [p.relative_to(repo) for p in (repo / 'data').glob('*') if p.is_file()]
    paths += [p.relative_to(repo) for p in (repo / 'tests').glob('*.py')]
    paths += [p.relative_to(repo) for folder in ('po', 'locale', 'tools')
              for p in (repo / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for rel in sorted(paths):
            data = (repo / rel).read_bytes()
            entry = tarfile.TarInfo(f'obyn-{version}/{rel.as_posix()}')
            entry.size = len(data)
            entry.mode = 0o644
            entry.mtime = 0
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = 'root'
            tar.addfile(entry, io.BytesIO(data))
    archive = package_dir / f'obyn-{version}.tar.gz'
    archive.write_bytes(gzip.compress(stream.getvalue(), mtime=0))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    text = re.sub(r"^sha256sums=\('[^']+'\)$", f"sha256sums=('{digest}')", text, flags=re.M)
    recipe.write_text(text)
    print(f'{archive.name}  {digest}')


if __name__ == '__main__':
    main()
