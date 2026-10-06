#!/usr/bin/env python3
"""End-to-end install, PAM and restore checks. Runs ONLY inside the disposable
e2e container (scripts/container/e2e_in_container.sh): it creates users, swaps
PAM modules for stubs and installs packages as root."""
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = Path('/src')
OUT = Path('/out')
CONFIG = Path('/etc/security/thinkpad-auth')
LIB = Path('/usr/local/lib/thinkpad-auth')
STUB = Path('/usr/local/bin/e2e-second-factor')
STUB_LOG = Path('/run/e2e-second-factor.log')
STUB_MODE = Path('/run/e2e-second-factor.mode')
BASE_VERSION = '46.0-0ubuntu6~24.04.14'
CUSTOM_VERSION = BASE_VERSION + '+thinkpad2'
HOST = 'e2e-host'
USERS = {'alice': 'alice-e2e-pass', 'bob': 'bob-e2e-pass'}
failures = []


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=600, **kwargs)


def check(condition, label, detail=''):
    print(('PASS ' if condition else 'FAIL ') + label)
    if not condition:
        failures.append(label)
        if detail:
            print('     ' + detail.strip().replace('\n', '\n     '))


def version(package):
    result = run(['dpkg-query', '-W', '-f=${Version}', package])
    return result.stdout if result.returncode == 0 else None


def capture_state():
    """Bytes of every file the installer may touch, for byte-exact restore checks."""
    paths = sorted(Path('/etc/pam.d').iterdir())
    if CONFIG.exists():
        paths += sorted(CONFIG.iterdir())
    return {str(p): p.read_bytes() for p in paths if p.is_file()}


def pam(service, user, rhost=None, password=None):
    args = ['pamtester']
    if rhost:
        args += ['-I', f'rhost={rhost}']
    result = run(args + [service, user, 'authenticate'],
                 input=(password if password is not None else USERS[user]) + '\n')
    return result.returncode == 0, result.stdout + result.stderr


def stub_calls():
    return STUB_LOG.read_text().split() if STUB_LOG.exists() else []


def swap_second_factor(stack_file, module):
    """Replace the real second-factor module with the file-controlled stub."""
    path = Path(stack_file)
    text = path.read_text()
    lines = [line for line in text.splitlines() if module in line]
    assert len(lines) == 1, f'{module} ausente em {stack_file}'
    path.write_text(text.replace(lines[0], f'auth [success=ok default=bad] pam_exec.so quiet {STUB}'))
    return text


def check_stack(factor):
    """Same assertions for both factors once the second stack calls the stub."""
    marker = f'THINKPAD_AUTH_V1:{factor.upper()}'
    STUB_LOG.unlink(missing_ok=True)
    ok, out = pam('gdm-password', 'alice', password='wrong')
    check(not ok and not stub_calls(), f'[{factor}] senha errada nega sem chamar o 2o fator', out)
    STUB_MODE.write_text('allow')
    ok, out = pam('gdm-password', 'alice')
    check(ok and stub_calls() == ['alice'], f'[{factor}] senha + 2o fator aceitos autenticam', out)
    check('THINKPAD_AUTH_V1:PASSWORD' in out and marker in out, f'[{factor}] marcadores enviados ao GDM', out)
    STUB_MODE.write_text('deny')
    ok, out = pam('gdm-password', 'alice')
    check(not ok, f'[{factor}] 2o fator recusado nega', out)
    STUB_LOG.unlink(missing_ok=True)
    ok, out = pam('gdm-password', 'bob')
    check(ok and not stub_calls(), f'[{factor}] outro usuario mantem so a senha', out)
    ok, out = pam('gdm-password', 'alice', rhost='192.0.2.10')
    check(ok and not stub_calls(), f'[{factor}] login remoto proprio isento do 2o fator', out)
    for service in ('login', 'sudo'):
        ok, out = pam(service, 'alice')
        check(ok and not stub_calls(), f'[{factor}] {service} inalterado', out)
    gdm_fingerprint = Path('/etc/pam.d/gdm-fingerprint')
    original = gdm_fingerprint.read_text()
    # Turn the reader into "always accept" to prove the block, not the reader, denies.
    gdm_fingerprint.write_text(original.replace('pam_fprintd.so', 'pam_permit.so'))
    ok_alice, out = pam('gdm-fingerprint', 'alice')
    ok_bob, _ = pam('gdm-fingerprint', 'bob')
    check(not ok_alice and ok_bob, f'[{factor}] via gdm-fingerprint bloqueada so para o alvo', out)
    gdm_fingerprint.write_text(original)


def create_users():
    for uid, (user, password) in enumerate(USERS.items(), start=1001):
        run(['useradd', '-m', '-u', str(uid), '-s', '/bin/bash', user]).check_returncode()
        run(['chpasswd'], input=f'{user}:{password}\n').check_returncode()
    STUB.write_text(f'#!/bin/sh\necho "$PAM_USER" >> {STUB_LOG}\n[ "$(cat {STUB_MODE})" = allow ]\n')
    STUB.chmod(0o755)


def register_fake_trezor():
    # Format of pamu2fcfg output; the fake key can never verify, which the real-module check relies on.
    CONFIG.mkdir(mode=0o755, exist_ok=True)
    authfile = CONFIG / 'u2f_keys'
    authfile.write_text('alice:e2eKeyHandle,e2ePublicKey,es256,+presence\n')
    authfile.chmod(0o644)


def install_trezor():
    result = run([sys.executable, str(REPO / 'scripts/install.py'), 'prepare', '--user', 'alice',
                  '--factor', 'trezor', '--host', HOST, '--packages', str(OUT / 'packages'),
                  '--manifest', str(OUT / 'packages/packages-manifest.json'),
                  '--original-packages', str(OUT / 'original-packages')])
    match = re.search(r'PREPARADO_SEM_ATIVAR (\S+)', result.stdout)
    check(result.returncode == 0 and match, 'install.py prepare --factor trezor', result.stdout + result.stderr)
    if not match:
        return None
    backup = match.group(1)
    result = run([sys.executable, str(LIB / 'pilot.py'), backup])
    check('PILOT_STARTED_ROLLBACK_ACTIVE' in result.stdout, 'piloto instala pacotes e ativa PAM',
          result.stdout + result.stderr)
    return backup


def check_installed_payload(backup):
    check(version('gnome-shell') == CUSTOM_VERSION and version('thinkpad-auth-policy') == '1.2',
          'versoes instaladas +thinkpad2 / politica 1.2')
    payload = json.loads((Path(backup) / 'payload.json').read_text())
    check(all(Path(name).read_text() == content for name, content in payload.items()),
          'PAM ativo identico ao payload do snapshot')
    check(Path('/usr/share/thinkpad-auth/trezor-symbolic.svg').is_file(), 'icone Trezor instalado')
    for locale, expected in (('pt_BR.UTF-8', 'Digite sua senha'), ('ja_JP.UTF-8', 'パスワードを入力してください'),
                             ('en_US.UTF-8', 'Enter your password')):
        result = run(['gettext', '-d', 'gnome-auth-carousel', 'Enter your password'],
                     env={'LC_ALL': locale, 'PATH': '/usr/bin:/bin'})
        diagnostics = run(['bash', '-c', 'locale -a; ls -l /usr/share/locale/*/LC_MESSAGES/gnome-auth-carousel.mo']).stdout
        check(result.stdout == expected, f'catalogo {locale} -> {expected}',
              f'{result.stdout}{result.stderr}\n{diagnostics}')
    library = next(p for p in run(['dpkg', '-L', 'gnome-shell']).stdout.split() if re.search(r'libshell-\d+\.so$', p))
    module = run(['gresource', 'extract', library, '/org/gnome/shell/gdm/thinkpadAuth.js']).stdout
    state = run(['gresource', 'extract', library, '/org/gnome/shell/gdm/thinkpadAuthState.js']).stdout
    check("'gnome-auth-carousel'" in module and 'THINKPAD_AUTH_V1:TREZOR' in state,
          'Shell compilado contem carrossel com i18n e fator Trezor')


SMOKE_SCRIPT = r"""
set -u
gsettings set org.gnome.shell enabled-extensions "['carousel-smoke@e2e']"
gsettings set org.gnome.shell disable-user-extensions false
gnome-shell --headless --wayland --no-x11 --virtual-monitor 1280x800 > "$LOG" 2>&1 &
for _ in $(seq 90); do
    grep -q 'CAROUSEL_SMOKE_' "$LOG" && break
    sleep 1
done
kill %1 2>/dev/null; wait
"""


def smoke_shell():
    """Start the installed Shell headless as alice (pt_BR) and render the real carousel."""
    home = Path('/home/alice')
    extension = home / '.local/share/gnome-shell/extensions/carousel-smoke@e2e'
    extension.mkdir(parents=True, exist_ok=True)
    for name in ('metadata.json', 'extension.js'):
        (extension / name).write_text((REPO / 'tests/e2e/carousel-smoke@e2e' / name).read_text())
    runtime = Path('/run/user/1001')
    runtime.mkdir(parents=True, exist_ok=True)
    shots = OUT / 'screenshots'
    shots.mkdir(exist_ok=True)
    for path in (home, runtime, shots):
        run(['chown', '-R', 'alice:alice', str(path)]).check_returncode()
    runtime.chmod(0o700)
    log = Path('/tmp/shell-smoke.log')
    run(['runuser', '-u', 'alice', '--', 'env', f'HOME={home}', f'XDG_RUNTIME_DIR={runtime}',
         'LANG=pt_BR.UTF-8', 'LC_ALL=pt_BR.UTF-8', f'LOG={log}', f'CAROUSEL_SMOKE_OUT={shots}',
         'dbus-run-session', '--', 'bash', '-c', SMOKE_SCRIPT])
    text = log.read_text() if log.exists() else ''
    (OUT / 'shell-smoke.log').write_text(text)
    errors = [line for line in text.splitlines() if 'JS ERROR' in line or 'CAROUSEL_SMOKE_FAIL' in line
              or ('thinkpad' in line.lower() and 'error' in line.lower())]
    ok_line = next((line for line in text.splitlines() if 'CAROUSEL_SMOKE_OK' in line), '')
    check(ok_line and not errors, 'gnome-shell headless renderiza o carrossel sem erro JS',
          '\n'.join(errors) or text[-2000:])
    check('Digite sua senha' in ok_line and 'Conecte seu Trezor' in ok_line and 'stage=second' in ok_line,
          'carrossel real traduzido (pt_BR) e avanca para o Trezor', ok_line)
    check((shots / 'carousel-password.png').is_file() and (shots / 'carousel-second.png').is_file(),
          'screenshots do carrossel em /out/screenshots')


def test_trezor_installed():
    stack = '/etc/pam.d/thinkpad-local-trezor'
    ok, out = pam('gdm-password', 'alice')
    check(not ok, '[trezor] pam_u2f real sem dispositivo nega a senha correta', out)
    original = swap_second_factor(stack, 'pam_u2f.so')
    check_stack('trezor')
    Path(stack).write_text(original)


def restore(backup, before):
    result = run([sys.executable, str(REPO / 'scripts/install.py'), 'restore', '--backup', backup])
    check(result.returncode == 0, 'install.py restore', result.stdout + result.stderr)
    after = capture_state()
    changed = sorted(set(before) ^ set(after) | {k for k in before if before[k] != after.get(k)})
    check(not changed, 'restauracao byte a byte de PAM e configuracao', '\n'.join(changed))
    check(version('gnome-shell') == BASE_VERSION and version('thinkpad-auth-policy') in (None, ''),
          'Shell original restaurado e politica removida')


def test_fingerprint_policy(before):
    """Fingerprint needs fprintd on the system bus, so it is checked at the PAM level only."""
    sys.path.insert(0, str(REPO / 'scripts'))
    from policy import files
    for name, content in files('/etc/pam.d', 'alice', 'fingerprint').items():
        Path(name).parent.mkdir(parents=True, exist_ok=True)
        Path(name).write_text(content)
    ok, out = pam('gdm-password', 'alice')
    check(not ok, '[fingerprint] pam_fprintd real sem leitor nega a senha correta', out)
    swap_second_factor('/etc/pam.d/thinkpad-local-fingerprint', 'pam_fprintd.so')
    check_stack('fingerprint')
    for name in set(capture_state()) - set(before):
        Path(name).unlink()
    for name, content in before.items():
        Path(name).write_bytes(content)


def main():
    if not (Path('/.dockerenv').exists() or Path('/run/.containerenv').exists()):
        raise SystemExit('Recusado: pam_e2e.py altera PAM e so roda no container descartavel.')
    run(['locale-gen', 'pt_BR.UTF-8', 'ja_JP.UTF-8', 'en_US.UTF-8']).check_returncode()
    create_users()
    register_fake_trezor()
    before = capture_state()
    backup = install_trezor()
    if backup:
        check_installed_payload(backup)
        smoke_shell()
        test_trezor_installed()
        restore(backup, before)
    test_fingerprint_policy(before)
    print(f'\n{len(failures)} falha(s)')
    if failures:
        raise SystemExit('E2E falhou: ' + '; '.join(failures))


if __name__ == '__main__':
    main()
