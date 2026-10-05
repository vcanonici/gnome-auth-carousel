#!/usr/bin/python3
"""Scoped snapshot, persistent timed recovery and activation for native carousel."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import sys
import time

VERSION = '46.0-0ubuntu6~24.04.14+thinkpad1'
UNIT = 'thinkpad-carousel-rollback'
CONFIG = Path('/etc/security/thinkpad-auth')
BASE = Path('/var/backups/thinkpad-auth')
EXEC = '/usr/local/sbin/thinkpad-carousel-control'
PACKAGES = ('gnome-shell', 'gnome-shell-common', 'gnome-shell-extension-prefs')


def run(args):
    deadline = time.monotonic() + 60
    while True:
        result = subprocess.run(args, capture_output=True, text=True,
                                env={**os.environ, 'LC_ALL': 'C'})
        if result.returncode == 0:
            return result.stdout.strip()
        if args[0] == 'dpkg' and 'lock' in result.stderr.lower() and time.monotonic() < deadline:
            time.sleep(1)
            continue
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)


def atomic(path, data, mode=0o644, uid=0, gid=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.thinkpad-carousel-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.chown(tmp, uid, gid)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def stop_timer():
    state = run(['systemctl', 'show', UNIT + '.timer', '-p', 'LoadState', '--value'])
    if state != 'not-found':
        run(['systemctl', 'disable', '--now', UNIT + '.timer'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('snapshot', 'arm', 'activate', 'confirm', 'rollback', 'restore'))
    p.add_argument('backup', type=Path)
    p.add_argument('--original-packages', type=Path)
    p.add_argument('--user', required=False)
    a = p.parse_args()
    if os.geteuid() != 0:
        p.error('Exige root.')
    root = a.backup.resolve(strict=True)
    if not root.is_relative_to(BASE) or root == BASE:
        p.error('Diretorio fora do escopo.')
    for directory in (root, BASE):
        s = directory.stat()
        if s.st_uid != 0 or stat.S_IMODE(s.st_mode) != 0o700:
            p.error('Backup deve ser root:0700.')
    os.umask(0o077)
    with (root / 'carousel.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest_file = root / 'carousel.json'
        if a.action == 'snapshot':
            if manifest_file.exists() or not a.original_packages:
                p.error('Snapshot existente ou pacotes originais ausentes.')
            # Recovery/controller code exists independently of package activation.
            sys.path.insert(0, '/usr/local/lib/thinkpad-auth')
            from policy import files
            if not a.user:
                p.error('Snapshot exige --user.')
            payload = files('/etc/pam.d', a.user)
            manifest = {'files': {}, 'packages': {}, 'directory_mode':
                        stat.S_IMODE(CONFIG.stat().st_mode) if CONFIG.exists() else None}
            for i, name in enumerate(payload):
                path = Path(name)
                if path.is_symlink() or (path.exists() and not path.is_file()):
                    p.error('Arquivo inesperado: ' + name)
                entry = {'exists': path.exists()}
                if path.exists():
                    s = path.stat()
                    atomic(root / str(i), path.read_bytes(), 0o600)
                    entry.update(backup=str(i), mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid)
                manifest['files'][name] = entry
            pkg_dir = root / 'packages'
            pkg_dir.mkdir(mode=0o700)
            for pkg in PACKAGES:
                status = subprocess.run(['dpkg-query', '-W', '-f=${Status}', pkg],
                                        capture_output=True, text=True)
                if pkg == 'gnome-shell-extension-prefs' and (
                        status.returncode or status.stdout != 'install ok installed'):
                    continue
                current = run(['dpkg-query', '-W', '-f=${Version}', pkg])
                candidates = list(a.original_packages.glob(pkg + '_*.deb'))
                candidates = [x for x in candidates if run(['dpkg-deb', '-f', str(x), 'Package']) == pkg
                              and run(['dpkg-deb', '-f', str(x), 'Version']) == current]
                if len(candidates) != 1:
                    p.error('Pacote original exato ausente: ' + pkg)
                data = candidates[0].read_bytes()
                atomic(pkg_dir / candidates[0].name, data, 0o600)
                manifest['packages'][pkg] = {'version': current, 'file': candidates[0].name,
                                             'sha256': hashlib.sha256(data).hexdigest()}
            # Generated payload is fixed at snapshot time, before any live PAM change.
            atomic(root / 'payload.json', json.dumps(payload).encode(), 0o600)
            atomic(manifest_file, json.dumps(manifest, indent=2).encode(), 0o600)
            print('CAROUSEL_SNAPSHOT_OK')
            return
        manifest = json.loads(manifest_file.read_text())
        if a.action in ('arm', 'activate'):
            if (root / 'confirmed').exists() or (root / 'restored').exists():
                p.error('Rodada encerrada.')
            if a.action == 'activate':
                for pkg in ('gnome-shell', 'gnome-shell-common'):
                    if run(['dpkg-query', '-W', '-f=${Version}', pkg]) != VERSION:
                        p.error('GNOME Shell testado nao instalado.')
            # Arm persistent recovery first. A reboot starts another ten minute window.
            atomic(Path('/etc/systemd/system/' + UNIT + '.service'),
                   f'[Unit]\nDescription=Recuperacao da autenticacao ThinkPad\n[Service]\nType=oneshot\nExecStart={EXEC} rollback {root}\n'.encode())
            atomic(Path('/etc/systemd/system/' + UNIT + '.timer'),
                   f'[Unit]\nDescription=Janela de validacao da autenticacao ThinkPad\n[Timer]\nOnActiveSec=10min\nAccuracySec=1s\nUnit={UNIT}.service\n[Install]\nWantedBy=timers.target\n'.encode())
            run(['systemctl', 'daemon-reload'])
            run(['systemctl', 'enable', '--now', UNIT + '.timer'])
            if a.action == 'arm':
                print('CAROUSEL_ROLLBACK_ARMED_BEFORE_PACKAGES')
                return
            for name, content in json.loads((root / 'payload.json').read_text()).items():
                atomic(Path(name), content.encode())
            CONFIG.chmod(0o755)
            print('CAROUSEL_ACTIVE_ROLLBACK_10MIN')
            return
        if a.action == 'confirm':
            if (root / 'restored').exists():
                p.error('Estado ja restaurado.')
            atomic(root / 'confirmed', b'', 0o600)
            stop_timer()
            print('CAROUSEL_CONFIRMED')
            return
        if a.action == 'rollback' and (root / 'confirmed').exists():
            print('CAROUSEL_ROLLBACK_SKIPPED_CONFIRMED')
            return
        # Restore stock authentication first, even if package restoration later fails.
        for name, entry in manifest['files'].items():
            path = Path(name)
            if entry['exists']:
                atomic(path, (root / entry['backup']).read_bytes(), entry['mode'], entry['uid'], entry['gid'])
            else:
                path.unlink(missing_ok=True)
        if manifest['directory_mode'] is not None:
            CONFIG.chmod(manifest['directory_mode'])
        elif CONFIG.exists() and not any(CONFIG.iterdir()):
            CONFIG.rmdir()
        package_paths = []
        for pkg, entry in manifest['packages'].items():
            path = root / 'packages' / entry['file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise RuntimeError('Checksum de recuperacao divergente.')
            package_paths.append(str(path))
        # Companion intentionally constrains upgrades; remove before restoring stock pair.
        installed = subprocess.run(['dpkg-query', '-W', '-f=${Status}', 'thinkpad-auth-policy'],
                                   capture_output=True, text=True)
        if installed.returncode == 0 and installed.stdout == 'install ok installed':
            run(['dpkg', '--remove', 'thinkpad-auth-policy'])
        run(['dpkg', '--install', *package_paths])
        atomic(root / 'restored', b'', 0o600)
        stop_timer()
        print('CAROUSEL_RESTORED_NO_SESSION_RESTART')


if __name__ == '__main__':
    main()
