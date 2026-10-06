#!/usr/bin/env python3
"""Generate narrowly scoped PAM policy. Does not write the host configuration."""
from pathlib import Path
import pwd
import re

ALTERNATIVES = ('gdm-fingerprint', 'gdm-autologin',
                'gdm-smartcard-sssd-exclusive', 'gdm-smartcard-sssd-or-password',
                'gdm-smartcard-pkcs11-exclusive')
CONFIG = '/etc/security/thinkpad-auth'
# Registered with: pamu2fcfg -o pam://HOST -i pam://HOST -u USER (root:root 0644).
U2F_AUTHFILE = CONFIG + '/u2f_keys'
FACTORS = ('fingerprint', 'trezor')
HOST_PATTERN = r'[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*'


def second_factor_module(factor, host):
    """Return the authoritative PAM line for the selected second factor."""
    if factor == 'fingerprint':
        return 'auth [success=ok default=bad] pam_fprintd.so max-tries=3 timeout=30'
    # No nouserok: a user without a registered Trezor must be denied, not skipped.
    # The Trezor asks for its own PIN on the device, so no pinverification.
    return (f'auth [success=ok default=bad] pam_u2f.so authfile={U2F_AUTHFILE} '
            f'origin=pam://{host} appid=pam://{host}')


def files(pam_dir, username, factor='fingerprint', host=None):
    """Map each managed path to its content for one local user and second factor.

    factor: 'fingerprint' (pam_fprintd) or 'trezor' (pam_u2f, requires host,
    the FIDO origin used when registering the device).
    """
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', username):
        raise ValueError('Nome de usuario local invalido.')
    if factor not in FACTORS:
        raise ValueError('Fator desconhecido: use fingerprint ou trezor.')
    if factor == 'trezor' and not (host and re.fullmatch(HOST_PATTERN, host)):
        raise ValueError('Fator trezor exige host valido (origem FIDO pam://HOST).')
    account = pwd.getpwnam(username)
    if account.pw_uid < 1000:
        raise ValueError('Exige conta local comum, nao conta de sistema.')
    pam_dir = Path(pam_dir)
    second_stack = 'thinkpad-local-' + factor
    original = (pam_dir / 'gdm-password').read_text()
    if original.count('@include common-auth') != 1 or 'thinkpad-local-' in original:
        raise ValueError('PAM original inesperado; nao aplicar sobre politica existente.')
    result = {'/etc/pam.d/gdm-password': original.replace('@include common-auth',
        'auth substack thinkpad-local-password-step\n@include common-auth\n'
        f'auth substack {second_stack}', 1)}
    for name in ALTERNATIVES:
        path = pam_dir / name
        if not path.exists():
            continue
        content = path.read_text()
        if not content.startswith('#%PAM-1.0\n') or 'thinkpad-local-' in content:
            raise ValueError(f'PAM original inesperado: {name}')
        # include propagates pam_deny's requisite failure to the caller.
        # substack would only stop the helper and could still call the reader.
        result[f'/etc/pam.d/{name}'] = content.replace('#%PAM-1.0\n',
            '#%PAM-1.0\nauth include thinkpad-local-block\n', 1)
    result.update({
        '/etc/pam.d/thinkpad-local-password-step': '''#%PAM-1.0
auth [success=2 default=ignore] pam_succeed_if.so user != vinicius quiet
auth [success=1 default=ignore] pam_succeed_if.so rhost =~ ?* quiet
auth optional pam_echo.so file=/etc/security/thinkpad-auth/password-step.txt
auth required pam_permit.so
''',
        f'/etc/pam.d/{second_stack}': f'''#%PAM-1.0
auth [success=3 default=ignore] pam_succeed_if.so user != vinicius quiet
auth [success=2 default=ignore] pam_succeed_if.so rhost =~ ?* quiet
auth optional pam_echo.so file=/etc/security/thinkpad-auth/{factor}-step.txt
{second_factor_module(factor, host)}
auth required pam_permit.so
''',
        '/etc/pam.d/thinkpad-local-block': '''#%PAM-1.0
auth [success=2 default=ignore] pam_succeed_if.so user != vinicius quiet
auth [success=1 default=ignore] pam_succeed_if.so rhost =~ ?* quiet
auth requisite pam_deny.so
auth required pam_permit.so
''',
        '/etc/security/thinkpad-auth/password-step.txt': 'THINKPAD_AUTH_V1:PASSWORD\n',
        f'/etc/security/thinkpad-auth/{factor}-step.txt': f'THINKPAD_AUTH_V1:{factor.upper()}\n',
        '/etc/security/thinkpad-auth/ui.conf': f'[UI]\nEnabled=true\nUsers=vinicius;\nFactor={factor}\n',
    })
    return {name: value.replace('user != vinicius quiet', f'user != {username} quiet')
            .replace('Users=vinicius;', f'Users={username};') for name, value in result.items()}
