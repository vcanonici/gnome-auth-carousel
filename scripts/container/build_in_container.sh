#!/bin/bash
# Runs inside a disposable ubuntu:24.04 container started by container_build.sh.
# Inputs: repository at /src (read-only). Outputs in /out:
#   packages/            3 .debs + packages-manifest.json
#   original-packages/   stock gnome-shell pair for recovery (checksum-verified)
#   gnome-auth-carousel-$RELEASE-amd64.tar.gz, gnome-shell-46.0-thinkpad2-source.tar.xz, SHA256SUMS
set -euo pipefail
source /src/scripts/container/common.sh
# Hand /out back to the host user even when a step fails.
trap own_output EXIT

log "APT no snapshot $SNAPSHOT"
setup_snapshot_apt
apt-get install -y -qq --no-install-recommends dpkg-dev fakeroot gettext nodejs python3 xz-utils >/dev/null

log "Copiando repositorio (sem artefatos)"
mkdir -p /work/repo
tar -C /src --exclude=./artifacts --exclude=./.git -cf - . | tar -C /work/repo -xf -
cd /work/repo

log "Testes unitarios e traducoes"
node --test tests/*.test.js
python3 -m unittest discover -s tests -p 'test_*.py'
cmp state.js scripts/state.js || die 'state.js e scripts/state.js divergem.'
for po in po/*.po; do msgfmt --check -o /dev/null "$po"; done
xgettext --language=JavaScript --keyword=N_ --from-code=UTF-8 -o /tmp/check.pot -f po/POTFILES
diff <(grep '^msgid' /tmp/check.pot) <(grep '^msgid' po/gnome-auth-carousel.pot) \
    || die 'po/gnome-auth-carousel.pot desatualizado: regenere com xgettext (docs/translations.md).'

log "Fonte original gnome-shell $BASE_VERSION (indices assinados do snapshot)"
cd /work
apt-get source -qq "gnome-shell=$BASE_VERSION"
source_dir=/work/gnome-shell-46.0
[[ -d $source_dir ]] || die "fonte nao extraido em $source_dir"
cp -a "$source_dir" /work/pristine
apt-get build-dep -y -qq "$source_dir" >/dev/null

log "Pacotes originais para recuperacao"
mkdir -p /out/original-packages
(cd /out/original-packages && apt-get download -qq "gnome-shell=$BASE_VERSION" "gnome-shell-common=$BASE_VERSION")
python3 - <<'PY'
import hashlib, json, pathlib
rows = json.loads(pathlib.Path('/work/repo/docs/original-packages.json').read_text())
for row in rows:
    path = pathlib.Path('/out/original-packages') / row['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise SystemExit('Checksum original divergente: ' + row['file'])
print('ORIGINAIS_CONFERIDOS')
PY

log "Compilando (pode levar 10-30 min)"
# Upstream test suite needs a display stack; our own tests ran above.
if [[ ${UPSTREAM_TESTS:-0} != 1 ]]; then export DEB_BUILD_OPTIONS=nocheck; fi
/work/repo/scripts/build.sh --in-build-vm "$source_dir"

log "Montando release"
rm -rf /out/packages && mkdir -p /out/packages
cp "/work/gnome-shell_${CUSTOM_VERSION}_amd64.deb" "/work/gnome-shell-common_${CUSTOM_VERSION}_all.deb" \
   "/work/thinkpad-auth-policy_${POLICY_VERSION}_all.deb" /out/packages/
python3 /work/repo/scripts/release_manifest.py /out/packages /out/packages/packages-manifest.json
tar -C /out/packages -czf "/out/gnome-auth-carousel-$RELEASE-amd64.tar.gz" .
python3 /work/repo/scripts/patch_source.py /work/pristine
mv /work/pristine /work/gnome-shell-46.0-thinkpad2
tar -C /work -cJf /out/gnome-shell-46.0-thinkpad2-source.tar.xz gnome-shell-46.0-thinkpad2
(cd /out && sha256sum "gnome-auth-carousel-$RELEASE-amd64.tar.gz" gnome-shell-46.0-thinkpad2-source.tar.xz > SHA256SUMS)
log "BUILD_OK"
