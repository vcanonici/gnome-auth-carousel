#!/usr/bin/python3
"""Write public checksums for exactly the installable binary trio."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('directory', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
rows = []
expected = {'gnome-shell': '46.0-0ubuntu6~24.04.14+thinkpad2',
            'gnome-shell-common': '46.0-0ubuntu6~24.04.14+thinkpad2', 'thinkpad-auth-policy': '1.2'}
for package, version in expected.items():
    found = []
    for path in a.directory.glob(package + '_*.deb'):
        def field(name):
            return subprocess.check_output(['dpkg-deb', '-f', str(path), name], text=True).strip()
        if field('Package') == package and field('Version') == version:
            found.append(path)
    if len(found) != 1:
        raise SystemExit('Exige um pacote exato: ' + package)
    path = found[0]
    rows.append({'set': 'packages', 'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
a.output.write_text(json.dumps(rows, indent=2) + '\n')
