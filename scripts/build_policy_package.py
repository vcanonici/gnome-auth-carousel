#!/usr/bin/env python3
"""Build companion package; never activate PAM during package installation."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
VERSION = '46.0-0ubuntu6~24.04.14+thinkpad2'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='thinkpad-policy-') as tmp:
    root = Path(tmp)
    (root / 'DEBIAN').mkdir()
    (root / 'DEBIAN/control').write_text(f'''Package: thinkpad-auth-policy
Version: 1.2
Architecture: all
Maintainer: ThinkPad Maintenance <root@localhost>
Depends: gnome-shell (= {VERSION}), gnome-shell-common (= {VERSION}), libpam-fprintd | libpam-u2f, python3
Section: admin
Priority: optional
Description: ThinkPad sequential authentication integration
 Pins the tested shell pair and provides inactive policy generation tools,
 the Trezor icon and the carousel translations.
 PAM activation and timed recovery are explicit controller actions.
''')
    dest = root / 'usr/share/thinkpad-auth'
    dest.mkdir(parents=True)
    shutil.copyfile(HERE / 'policy.py', dest / 'policy.py')
    shutil.copyfile(HERE.parent / 'assets/trezor-symbolic.svg', dest / 'trezor-symbolic.svg')
    # One catalog per po/*.po; the shell binds the domain to /usr/share/locale.
    for po in sorted((HERE.parent / 'po').glob('*.po')):
        mo_dir = root / 'usr/share/locale' / po.stem / 'LC_MESSAGES'
        mo_dir.mkdir(parents=True)
        subprocess.run(['msgfmt', '--check', '-o', str(mo_dir / 'gnome-auth-carousel.mo'), str(po)], check=True)
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(root),
                    str(a.output.resolve() / 'thinkpad-auth-policy_1.2_all.deb')], check=True)
