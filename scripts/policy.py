#!/usr/bin/env python3
"""Generate narrowly scoped PAM policy. Does not write the host configuration."""
from pathlib import Path
import pwd
import re

ALTERNATIVES = ('gdm-fingerprint', 'gdm-autologin',
                'gdm-smartcard-sssd-exclusive', 'gdm-smartcard-sssd-or-password',
                'gdm-smartcard-pkcs11-exclusive')


def files(pam_dir, username):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', username):
        raise ValueError('Nome de usuario local invalido.')
    account = pwd.getpwnam(username)
    if account.pw_uid < 1000:
        raise ValueError('Exige conta local comum, nao conta de sistema.')
    pam_dir = Path(pam_dir)
    original = (pam_dir / 'gdm-password').read_text()
    if original.count('@include common-auth') != 1 or 'thinkpad-local-' in original:
        raise ValueError('PAM original inesperado; nao aplicar sobre politica existente.')
    result = {'/etc/pam.d/gdm-password': original.replace('@include common-auth',
        'auth substack thinkpad-local-password-step\n@include common-auth\n'
        'auth substack thinkpad-local-fingerprint', 1)}
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
        '/etc/pam.d/thinkpad-local-fingerprint': '''#%PAM-1.0
auth [success=3 default=ignore] pam_succeed_if.so user != vinicius quiet
auth [success=2 default=ignore] pam_succeed_if.so rhost =~ ?* quiet
auth optional pam_echo.so file=/etc/security/thinkpad-auth/fingerprint-step.txt
auth [success=ok default=bad] pam_fprintd.so max-tries=3 timeout=30
auth required pam_permit.so
''',
        '/etc/pam.d/thinkpad-local-block': '''#%PAM-1.0
auth [success=2 default=ignore] pam_succeed_if.so user != vinicius quiet
auth [success=1 default=ignore] pam_succeed_if.so rhost =~ ?* quiet
auth requisite pam_deny.so
auth required pam_permit.so
''',
        '/etc/security/thinkpad-auth/password-step.txt': 'THINKPAD_AUTH_V1:PASSWORD\n',
        '/etc/security/thinkpad-auth/fingerprint-step.txt': 'THINKPAD_AUTH_V1:FINGERPRINT\n',
        '/etc/security/thinkpad-auth/ui.conf': '[UI]\nEnabled=true\nUsers=vinicius;\n',
    })
    return {name: value.replace('user != vinicius quiet', f'user != {username} quiet')
            .replace('Users=vinicius;', f'Users={username};') for name, value in result.items()}
