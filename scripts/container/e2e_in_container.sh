#!/bin/bash
# Runs inside a clean ubuntu:24.04 container (no build dependencies).
# Inputs: repository at /src (read-only), build output at /out (from build_in_container.sh).
# Exercises the real install path (prepare -> pilot -> restore) and the PAM stacks.
set -euo pipefail
source /src/scripts/container/common.sh
# Hand /out back to the host user even when a step fails.
trap own_output EXIT

[[ -f /out/packages/packages-manifest.json ]] || die 'Pacotes ausentes em /out/packages: rode o build antes.'

log "APT no snapshot $SNAPSHOT"
setup_snapshot_apt

log "Desktop minimo com o Shell ORIGINAL $BASE_VERSION"
# The Docker ubuntu image drops /usr/share/locale/*/LC_MESSAGES/*.mo at install
# time; a desktop installs them, so the translation checks need them too.
rm -f /etc/dpkg/dpkg.cfg.d/excludes
# libpam-cap keeps common-auth identical to an Ubuntu desktop (audited by install.py).
apt-get install -y -qq --no-install-recommends \
    "gnome-shell=$BASE_VERSION" "gnome-shell-common=$BASE_VERSION" gdm3 \
    libpam-fprintd libpam-u2f libpam-cap libpam-gnome-keyring python3 python3-dbus \
    pamtester gettext-base libglib2.0-bin locales \
    dbus dbus-user-session dconf-service dconf-gsettings-backend libgl1-mesa-dri fonts-cantarell >/dev/null

log "systemctl simulado (container sem systemd)"
# Answers only what install.py/pilot.py/desktop_control.py ask; every other call succeeds silently.
cat > /usr/local/bin/systemctl <<'STUB'
#!/bin/sh
case "$*" in
    is-active*) echo active ;;
    *TTYPath*) echo /dev/tty8 ;;
    *LoadState*) echo not-found ;;
esac
exit 0
STUB
chmod 755 /usr/local/bin/systemctl
hash -r

# A system bus lets the Shell's system proxies connect during the headless smoke test.
# Without /run/systemd/seats the Shell uses its dummy login manager instead of
# activating logind, which cannot run in the container.
mkdir -p /run/dbus && dbus-daemon --system --fork
rm -rf /run/systemd/seats

python3 /src/tests/e2e/pam_e2e.py
log "E2E_OK"
