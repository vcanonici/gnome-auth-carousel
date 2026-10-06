#!/usr/bin/python3
"""Prepare a verified, inactive snapshot; start an explicit recoverable GDM pilot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE_VERSION = '46.0-0ubuntu6~24.04.14'
CUSTOM_VERSION = BASE_VERSION + '+thinkpad2'
BASE = Path('/var/backups/thinkpad-auth')
CONTROL = '/usr/local/sbin/thinkpad-carousel-control'
LIB = Path('/usr/local/lib/thinkpad-auth')


def run(args):
    return subprocess.check_output(args, text=True).strip()


def installed(pkg):
    return run(['dpkg-query', '-W', '-f=${Version}', pkg])


def check_u2f_authfile(path, username):
    """Require a root-owned, non-writable pam_u2f mapping with a credential for username."""
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    if info is None or not stat.S_ISREG(info.st_mode):
        raise ValueError(f'Registre o Trezor antes: {path} ausente ou nao regular (veja README, pamu2fcfg).')
    if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f'{path} deve ser root e nao gravavel por grupo/outros.')
    for line in path.read_text().splitlines():
        user, _, credentials = line.partition(':')
        if user == username and credentials.strip():
            return
    raise ValueError(f'Nenhuma credencial Trezor de {username} em {path}.')


def check_fingerprint(username):
    import dbus
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object('net.reactivated.Fprint', '/net/reactivated/Fprint/Manager'),
                             'net.reactivated.Fprint.Manager')
    device = dbus.Interface(bus.get_object('net.reactivated.Fprint', manager.GetDefaultDevice()),
                            'net.reactivated.Fprint.Device')
    enrolled = [str(x) for x in device.ListEnrolledFingers(username)]
    if not any('index-finger' in x for x in enrolled):
        raise ValueError('A primeira interface pede indicador: cadastre indicador esquerdo ou direito antes de instalar.')


def preflight(username, factor, host):
    from policy import files, U2F_AUTHFILE
    account = pwd.getpwnam(username)
    if not any(row.startswith(username + ':') for row in Path('/etc/passwd').read_text().splitlines()):
        raise ValueError('Exige conta local presente em /etc/passwd.')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
        raise ValueError('Suporte inicial: Ubuntu 24.04.')
    if run(['dpkg', '--print-architecture']) != 'amd64':
        raise ValueError('Pacotes iniciais suportam somente amd64.')
    for pkg in ('gnome-shell', 'gnome-shell-common'):
        if installed(pkg) != BASE_VERSION:
            raise ValueError('Versao original exata exigida: ' + BASE_VERSION)
    factor_pkg = 'libpam-fprintd' if factor == 'fingerprint' else 'libpam-u2f'
    for pkg in ('gdm3', factor_pkg, 'python3-dbus'):
        if run(['dpkg-query', '-W', '-f=${Status}', pkg]) != 'install ok installed':
            raise ValueError('Dependencia ausente: ' + pkg)
    if run(['systemctl', 'is-active', 'gdm3.service']) != 'active':
        raise ValueError('Exige GDM ativo.')
    # Audit the password authority rather than assuming arbitrary PAM stacks.
    common = Path('/etc/pam.d/common-auth').read_text()
    active = [' '.join(x.split()) for x in common.splitlines() if x.strip() and not x.lstrip().startswith('#')]
    tail = ['auth requisite pam_deny.so', 'auth required pam_permit.so', 'auth optional pam_cap.so']
    accepted = []
    for unix_options in ('', ' nullok'):
        accepted.append(['auth [success=1 default=ignore] pam_unix.so' + unix_options] + tail)
        accepted.append(['auth [success=2 default=ignore] pam_unix.so' + unix_options,
                         'auth [success=1 default=ignore] pam_sss.so use_first_pass'] + tail)
    if active not in accepted:
        raise ValueError('common-auth personalizado exige auditoria; nao alterar automaticamente.')
    with Path('/etc/shadow').open() as shadow:
        hashed = next((row.split(':', 2)[1] for row in shadow if row.startswith(username + ':')), '')
    if not hashed or hashed.startswith(('!', '*')):
        raise ValueError('A conta alvo precisa ter senha local ativa.')
    files('/etc/pam.d', username, factor, host)  # validates account and all targeted PAM anchors
    if factor == 'fingerprint':
        check_fingerprint(username)
    else:
        check_u2f_authfile(U2F_AUTHFILE, username)
    # Keep recovery separate from a modified desktop, and avoid overwriting other deployments.
    destinations = [Path(CONTROL)] + [LIB / x for x in ('policy.py', 'stage_payload.py', 'pilot.py', 'recovery_console.py')]
    if any(x.exists() or x.is_symlink() for x in destinations):
        raise ValueError('Controladores anteriores presentes; remova-os somente apos recuperacao/auditoria.')
    return account


def verify_packages(directory, manifest):
    rows = json.loads(manifest.read_text())
    expected = {'gnome-shell': CUSTOM_VERSION, 'gnome-shell-common': CUSTOM_VERSION, 'thinkpad-auth-policy': '1.2'}
    for row in rows:
        name = row['file']
        if Path(name).name != name or row.get('set') != 'packages':
            raise ValueError('Manifesto de release invalido.')
        path = directory / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Checksum ou symlink invalido: ' + name)
        pkg = run(['dpkg-deb', '-f', str(path), 'Package'])
        if pkg not in expected or run(['dpkg-deb', '-f', str(path), 'Version']) != expected.pop(pkg):
            raise ValueError('Pacote/versao inesperado.')
        if run(['dpkg-deb', '-f', str(path), 'Architecture']) not in ('all', 'amd64'):
            raise ValueError('Arquitetura divergente.')
    if expected:
        raise ValueError('Release incompleta.')


def root_snapshot(path):
    root = path.resolve(strict=True)
    if not root.is_relative_to(BASE) or not (root / 'carousel.json').is_file():
        raise ValueError('Snapshot invalido.')
    return root


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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    prepare = sub.add_parser('prepare', help='Verifica e cria backup, sem ativar nem encerrar sessao')
    prepare.add_argument('--user', required=True)
    prepare.add_argument('--factor', choices=('fingerprint', 'trezor'), default='fingerprint',
                         help='Segundo fator apos a senha (padrao: fingerprint)')
    prepare.add_argument('--host', default=socket.gethostname().lower(),
                         help='Origem FIDO pam://HOST usada no registro do Trezor (padrao: hostname)')
    prepare.add_argument('--packages', type=Path, required=True)
    prepare.add_argument('--manifest', type=Path, required=True)
    prepare.add_argument('--original-packages', type=Path, required=True)
    for action in ('start', 'confirm', 'restore', 'status'):
        item = sub.add_parser(action)
        item.add_argument('--backup', type=Path, required=True)
        if action == 'start':
            item.add_argument('--saved-work', action='store_true', required=True)
        if action == 'confirm':
            for name in ('login', 'unlock', 'resume'):
                item.add_argument('--' + name + '-ok', action='store_true', required=True)
    a = p.parse_args()
    if os.geteuid() != 0:
        p.error('Execute com sudo; nao envie senha ao programa pela linha de comando.')
    if a.action == 'prepare':
        assert_package_manager_idle()
        account = preflight(a.user, a.factor, a.host)
        verify_packages(a.packages, a.manifest)
        # Validate all rollback packages before installing any privileged helper.
        packages = ['gnome-shell', 'gnome-shell-common']
        prefs = subprocess.run(['dpkg-query', '-W', '-f=${Status}', 'gnome-shell-extension-prefs'], capture_output=True, text=True)
        if prefs.stdout == 'install ok installed':
            if installed('gnome-shell-extension-prefs') != BASE_VERSION:
                raise ValueError('Versao de extension-prefs exige auditoria.')
            # Avoid dependency mismatch: initial installer supports hosts without this optional package.
            raise ValueError('extension-prefs instalado: primeiro adapte/teste a release incluindo o par exato; nao remover automaticamente.')
        original_hashes = {row['file']: row['sha256'] for row in json.loads((HERE.parent / 'docs/original-packages.json').read_text())}
        for package in packages:
            matches = [x for x in a.original_packages.glob(package + '_*.deb')
                       if not x.is_symlink() and run(['dpkg-deb', '-f', str(x), 'Package']) == package
                       and run(['dpkg-deb', '-f', str(x), 'Version']) == BASE_VERSION
                       and run(['dpkg-deb', '-f', str(x), 'Architecture']) in ('amd64', 'all')]
            if len(matches) != 1:
                raise ValueError('Pacote original exato ausente: ' + package)
            path = matches[0]
            if hashlib.sha256(path.read_bytes()).hexdigest() != original_hashes.get(path.name):
                raise ValueError('Checksum do pacote original divergente: ' + package)
        BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
        if BASE.is_symlink() or BASE.stat().st_uid != 0 or BASE.stat().st_mode & 0o777 != 0o700:
            raise ValueError('Diretorio de backups deve ser root:0700.')
        root = BASE / (datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ') + '-carousel')
        root.mkdir(mode=0o700)
        subprocess.run(['install', '-d', '-m', '0755', str(LIB)], check=True)
        for filename, destination in [('desktop_control.py', CONTROL)] + [(x, str(LIB / x)) for x in
                                       ('policy.py', 'stage_payload.py', 'pilot.py', 'recovery_console.py')]:
            subprocess.run(['install', '-o', 'root', '-g', 'root', '-m', '0755' if filename == 'desktop_control.py' else '0644',
                            str(HERE / filename), destination], check=True)
        subprocess.run([CONTROL, 'snapshot', str(root), '--user', a.user, '--factor', a.factor, '--host', a.host,
                        '--original-packages', str(a.original_packages.resolve())], check=True)
        subprocess.run([sys.executable, str(LIB / 'stage_payload.py'), str(root),
                        str(a.packages.resolve()), str(a.manifest.resolve())], check=True)
        (root / 'target.json').write_text(json.dumps({'username': a.user, 'uid': account.pw_uid,
                                                      'factor': a.factor, 'host': a.host}))
        (root / 'target.json').chmod(0o600)
        print('PREPARADO_SEM_ATIVAR ' + str(root))
        return
    root = root_snapshot(a.backup)
    if a.action == 'status':
        print('Confirmado:', (root / 'confirmed').exists(), 'Restaurado:', (root / 'restored').exists())
        subprocess.run(['systemctl', 'list-timers', 'thinkpad-carousel-rollback.timer', '--no-pager'], check=True)
    elif a.action == 'start':
        assert_package_manager_idle()
        if (root / 'confirmed').exists() or (root / 'restored').exists():
            raise ValueError('Rodada encerrada.')
        print('SESSAO SERA ENCERRADA. Recuperacao: Ctrl+Alt+F8, opcao 1. Reversao em 10 min.', flush=True)
        subprocess.run(['systemd-run', '--unit=thinkpad-carousel-console', '--property=StandardInput=tty',
                        '--property=StandardOutput=tty', '--property=StandardError=tty', '--property=TTYPath=/dev/tty8',
                        '--property=TTYReset=yes', '--property=TTYVHangup=yes', sys.executable,
                        str(LIB / 'recovery_console.py'), str(root)], check=True)
        subprocess.run(['systemd-run', '--unit=thinkpad-carousel-pilot', sys.executable,
                        str(LIB / 'pilot.py'), str(root)], check=True)
    elif a.action == 'confirm':
        for pkg in ('gnome-shell', 'gnome-shell-common'):
            if installed(pkg) != CUSTOM_VERSION:
                raise ValueError('Pacotes ativos divergentes.')
        for name, content in json.loads((root / 'payload.json').read_text()).items():
            if Path(name).read_text() != content:
                raise ValueError('Politica ativa divergente: ' + name)
        target = json.loads((root / 'target.json').read_text())
        sessions = run(['loginctl', 'list-sessions', '--no-legend', '--no-pager']).splitlines()
        local_active = False
        for session in sessions:
            sid = session.split()[0]
            if run(['loginctl', 'show-session', sid, '-p', 'User', '--value']) == str(target['uid']):
                state = run(['loginctl', 'show-session', sid, '-p', 'State', '--value'])
                remote = run(['loginctl', 'show-session', sid, '-p', 'Remote', '--value'])
                if state == 'active' and remote == 'no':
                    local_active = True
        if not local_active:
            raise ValueError('Nenhuma sessao local ativa do usuario alvo.')
        subprocess.run([CONTROL, 'confirm', str(root)], check=True)
        subprocess.run(['systemctl', 'stop', 'thinkpad-carousel-console.service'], check=True)
    else:
        subprocess.run([CONTROL, 'restore', str(root)], check=True)
        if run(['systemctl', 'show', 'thinkpad-carousel-console.service', '-p', 'LoadState', '--value']) != 'not-found':
            subprocess.run(['systemctl', 'stop', 'thinkpad-carousel-console.service'], check=True)
        print('Originais restaurados; encerre/reabra sessao quando tiver salvo o trabalho.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
