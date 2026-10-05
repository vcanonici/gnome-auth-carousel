#!/usr/bin/python3
"""Run from PID 1 after saved-work coordination; require recovery TTY and snapshot."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

CONTROL = '/usr/local/sbin/thinkpad-carousel-control'
if os.geteuid() != 0 or len(sys.argv) != 2:
    raise SystemExit('Exige root e snapshot.')
root = Path(sys.argv[1]).resolve(strict=True)
if not root.is_relative_to('/var/backups/thinkpad-auth') or not (root / 'carousel.json').is_file():
    raise SystemExit('Snapshot invalido.')


def run(args):
    return subprocess.check_output(args, text=True).strip()



def assert_package_manager_idle():
    import fcntl
    for name in ('/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock'):
        with open(name, 'a') as lock:
            try:
                fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('APT/dpkg ocupado; aguarde terminar e tente novamente.')
            finally:
                fcntl.lockf(lock, fcntl.LOCK_UN)


assert_package_manager_idle()
# The operator starts this independent menu before any desktop intervention.
if run(['systemctl', 'is-active', 'thinkpad-carousel-console.service']) != 'active':
    raise SystemExit('Console de recuperacao ausente.')
if run(['systemctl', 'show', 'thinkpad-carousel-console.service', '-p', 'TTYPath', '--value']) != '/dev/tty8':
    raise SystemExit('Console nao vinculado a tty8.')
manifest = json.loads((root / 'carousel.json').read_text())
for name, entry in manifest['files'].items():
    path = Path(name)
    if path.is_symlink() or (entry['exists'] and path.read_bytes() != (root / entry['backup']).read_bytes()) or (
            not entry['exists'] and path.exists()):
        raise SystemExit('Pre-estado alterado: ' + name)
for pkg, entry in manifest['packages'].items():
    if run(['dpkg-query', '-W', '-f=${Version}', pkg]) != entry['version']:
        raise SystemExit('Versao mudou desde snapshot: ' + pkg)
packages = []
rows = json.loads((root / 'new-packages.json').read_text())
expected = {'gnome-shell', 'gnome-shell-common', 'thinkpad-auth-policy'}
for entry in rows:
    name = entry['file']
    if Path(name).name != name:
        raise SystemExit('Nome de pacote invalido.')
    path = root / 'new-packages' / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise SystemExit('Checksum novo divergente.')
    pkg = run(['dpkg-deb', '-f', str(path), 'Package'])
    if pkg not in expected:
        raise SystemExit('Pacote fora do escopo.')
    expected.remove(pkg)
    packages.append(str(path))
if expected:
    raise SystemExit('Pacotes incompletos.')
try:
    subprocess.run([CONTROL, 'arm', str(root)], check=True)
    subprocess.run(['dpkg', '--install', *packages], check=True)
    subprocess.run([CONTROL, 'activate', str(root)], check=True)
    # This is the only session-ending action, after explicit saved-work readiness.
    subprocess.run(['systemctl', 'restart', 'gdm3.service'], check=True)
    print('PILOT_STARTED_ROLLBACK_ACTIVE', flush=True)
except subprocess.CalledProcessError:
    subprocess.run([CONTROL, 'restore', str(root)], check=True)
    raise
