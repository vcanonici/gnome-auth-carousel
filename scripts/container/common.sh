# Shared by the in-container steps. Sourced, not executed.
# The Ubuntu archive only indexes the newest gnome-shell; this signed snapshot
# still publishes the exact base version (superseded on 2026-09-24).
SNAPSHOT=20260920T000000Z
BASE_VERSION=46.0-0ubuntu6~24.04.14
CUSTOM_VERSION=$BASE_VERSION+thinkpad2
POLICY_VERSION=1.2
RELEASE=v1.1.0

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

# Point APT at the immutable snapshot (signature checked with the Ubuntu
# archive keyring). Keeps downloaded .debs when /var/cache/apt/archives is a
# shared volume, which is safe because the snapshot never changes.
setup_snapshot_apt() {
    export DEBIAN_FRONTEND=noninteractive
    rm -f /etc/apt/apt.conf.d/docker-clean
    apt-get update -qq
    apt-get install -y -qq ca-certificates >/dev/null
    cat > /etc/apt/sources.list.d/ubuntu.sources <<SOURCES
Types: deb deb-src
URIs: https://snapshot.ubuntu.com/ubuntu/$SNAPSHOT
Suites: noble noble-updates noble-security
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
SOURCES
    apt-get update -qq
}

# Give the host user ownership of everything written to /out.
own_output() {
    chown -R "${HOST_UID:-0}:${HOST_GID:-0}" /out
}
