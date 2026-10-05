#!/usr/bin/python3
"""Copy exactly three checksum-verified public packages into the private snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('backup', type=Path)
p.add_argument('packages', type=Path)
p.add_argument('manifest', type=Path)
a = p.parse_args()
r = a.backup.resolve(strict=True)
if os.geteuid() != 0 or not r.is_relative_to('/var/backups/thinkpad-auth') or not (r / 'carousel.json').is_file():
    p.error('Exige root e snapshot valido.')
expected = {'gnome-shell': '46.0-0ubuntu6~24.04.14+thinkpad1',
            'gnome-shell-common': '46.0-0ubuntu6~24.04.14+thinkpad1', 'thinkpad-auth-policy': '1.1'}
verified = []
for row in json.loads(a.manifest.read_text()):
    name = row['file']
    if Path(name).name != name:
        p.error('Nome inesperado.')
    pkg = name.split('_', 1)[0]
    if row['set'] != 'packages' or pkg not in expected:
        continue
    src = a.packages / name
    if src.is_symlink():
        p.error('Symlink de pacote inesperado.')
    content = src.read_bytes()
    if hashlib.sha256(content).hexdigest() != row['sha256']:
        p.error('Checksum divergente.')
    def field(key):
        return subprocess.check_output(['dpkg-deb', '-f', str(src), key], text=True).strip()
    if field('Package') != pkg or field('Version') != expected[pkg]:
        p.error('Metadados divergentes.')
    verified.append((row, content))
    del expected[pkg]
if expected:
    p.error('Pacotes incompletos.')
os.umask(0o077)
dest = r / 'new-packages'
dest.mkdir(mode=0o700, exist_ok=True)
for row, content in verified:
    (dest / row['file']).write_bytes(content)
(r / 'new-packages.json').write_text(json.dumps([row for row, _ in verified], indent=2))
print('THREE_PACKAGE_PAYLOAD_STAGED_INACTIVE')
