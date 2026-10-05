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


if __name__ == '__main__':
    unittest.main()
