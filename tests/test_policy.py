import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('policy', Path(__file__).parents[1] / 'scripts/policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class PolicyTest(unittest.TestCase):
    def test_target_account_and_existing_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'gdm-password').write_text('#%PAM-1.0\n@include common-auth\n@include common-account\n')
            (root / 'gdm-fingerprint').write_text('#%PAM-1.0\nauth required pam_fprintd.so\n')
            with patch.object(policy.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1001)):
                files = policy.files(root, 'alice')
            self.assertIn('Users=alice;', files['/etc/security/thinkpad-auth/ui.conf'])
            self.assertIn('user != alice quiet', files['/etc/pam.d/thinkpad-local-fingerprint'])
            self.assertIn('@include common-auth\n', files['/etc/pam.d/gdm-password'])
            self.assertIn('auth include thinkpad-local-block', files['/etc/pam.d/gdm-fingerprint'])
            self.assertNotIn('/etc/pam.d/common-auth', files)
            self.assertNotIn('/etc/pam.d/sudo', files)
            self.assertNotIn('/etc/pam.d/sshd', files)

    def test_invalid_username_never_reads_pam(self):
        for username in ('root\nauth sufficient pam_permit.so', 'a;b', 'name space', '-root', ''):
            with self.subTest(username=username), self.assertRaises(ValueError):
                policy.files('/does-not-exist', username)

    def test_system_account_rejected(self):
        with patch.object(policy.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=0)):
            with self.assertRaises(ValueError):
                policy.files('/does-not-exist', 'root')

    def test_modified_stack_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'gdm-password').write_text('#%PAM-1.0\nauth sufficient pam_permit.so\n')
            with patch.object(policy.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1001)):
                with self.assertRaises(ValueError):
                    policy.files(root, 'alice')


    def _pam_root(self, tmp):
        root = Path(tmp)
        (root / 'gdm-password').write_text('#%PAM-1.0\n@include common-auth\n@include common-account\n')
        (root / 'gdm-fingerprint').write_text('#%PAM-1.0\nauth required pam_fprintd.so\n')
        return root

    def test_trezor_factor_uses_pam_u2f_without_skipping_unregistered_users(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pam_root(tmp)
            with patch.object(policy.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1001)):
                files = policy.files(root, 'alice', 'trezor', 'megalodoom')
            stack = files['/etc/pam.d/thinkpad-local-trezor']
            self.assertIn('pam_u2f.so authfile=/etc/security/thinkpad-auth/u2f_keys', stack)
            self.assertIn('origin=pam://megalodoom appid=pam://megalodoom', stack)
            self.assertNotIn('nouserok', stack)
            self.assertNotIn('pam_fprintd', stack)
            self.assertIn('user != alice quiet', stack)
            self.assertIn('auth substack thinkpad-local-trezor', files['/etc/pam.d/gdm-password'])
            self.assertNotIn('/etc/pam.d/thinkpad-local-fingerprint', files)
            self.assertEqual(files['/etc/security/thinkpad-auth/trezor-step.txt'], 'THINKPAD_AUTH_V1:TREZOR\n')
            self.assertIn('Factor=trezor', files['/etc/security/thinkpad-auth/ui.conf'])
            self.assertIn('auth include thinkpad-local-block', files['/etc/pam.d/gdm-fingerprint'])

    def test_fingerprint_remains_the_default_factor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pam_root(tmp)
            with patch.object(policy.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1001)):
                files = policy.files(root, 'alice')
            self.assertIn('pam_fprintd.so', files['/etc/pam.d/thinkpad-local-fingerprint'])
            self.assertIn('Factor=fingerprint', files['/etc/security/thinkpad-auth/ui.conf'])

    def test_invalid_factor_or_host_rejected_before_reading_pam(self):
        for factor, host in (('sms', 'host'), ('trezor', None), ('trezor', 'a b'),
                             ('trezor', 'host appid=pam://evil'), ('trezor', 'Host')):
            with self.subTest(factor=factor, host=host), self.assertRaises(ValueError):
                policy.files('/does-not-exist', 'alice', factor, host)


install_spec = importlib.util.spec_from_file_location('install', Path(__file__).parents[1] / 'scripts/install.py')
install = importlib.util.module_from_spec(install_spec)
install_spec.loader.exec_module(install)


class U2fAuthfileTest(unittest.TestCase):
    def _authfile(self, tmp, name, content):
        path = Path(tmp) / name
        path.write_text(content)
        return path

    def test_registered_root_owned_file_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._authfile(tmp, 'ok', 'bob:cred1\nalice:khandle,pubkey,es256,+presence\n')
            with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_uid=0, st_mode=0o100644)):
                install.check_u2f_authfile(path, 'alice')

    def test_missing_user_writable_or_absent_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = [
                (self._authfile(tmp, 'other-user', 'bob:cred\nalice:\n'), 0o100644, 0),
                (self._authfile(tmp, 'group-writable', 'alice:cred\n'), 0o100664, 0),
                (self._authfile(tmp, 'user-owned', 'alice:cred\n'), 0o100644, 1000),
                (self._authfile(tmp, 'symlink', 'alice:cred\n'), 0o120777, 0),
            ]
            for path, mode, uid in cases:
                with self.subTest(path=path, mode=oct(mode), uid=uid), \
                        patch.object(Path, 'lstat', return_value=SimpleNamespace(st_uid=uid, st_mode=mode)), \
                        self.assertRaises(ValueError):
                    install.check_u2f_authfile(path, 'alice')
            with self.assertRaises(ValueError):
                install.check_u2f_authfile(Path(tmp) / 'absent', 'alice')


if __name__ == '__main__':
    unittest.main()
