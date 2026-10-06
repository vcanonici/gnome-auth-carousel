#!/bin/bash
# One command for the next users: build the patched GNOME Shell, run unit and
# end-to-end tests, and produce release artifacts — all inside disposable
# ubuntu:24.04 containers. Installs nothing on the host; needs Docker or Podman.
set -euo pipefail

usage() {
    cat <<'USAGE'
Uso: scripts/container_build.sh [--out DIR] [--e2e-only] [--build-only] [--upstream-tests] [--no-cache]

  --out DIR          destino dos artefatos (padrao: artifacts/container)
  --e2e-only         reutiliza pacotes ja compilados em DIR e roda so o e2e
  --build-only       compila e testa unidades, sem e2e
  --upstream-tests   roda tambem a suite upstream do gnome-shell (lenta)
  --no-cache         nao reutiliza o volume de cache de .debs do APT

Saidas em DIR: packages/ (3 .deb + manifesto), original-packages/,
gnome-auth-carousel-v1.1.0-amd64.tar.gz, gnome-shell-46.0-thinkpad2-source.tar.xz,
SHA256SUMS e logs build.log / e2e.log.
USAGE
}

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out=$repo/artifacts/container
run_build=1 run_e2e=1 upstream_tests=0 use_cache=1
while [[ $# -gt 0 ]]; do
    case $1 in
        --out) out=$(realpath -m -- "$2"); shift 2 ;;
        --e2e-only) run_build=0; shift ;;
        --build-only) run_e2e=0; shift ;;
        --upstream-tests) upstream_tests=1; shift ;;
        --no-cache) use_cache=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

engine=$(command -v docker || command -v podman || true)
[[ -n $engine ]] || { echo 'ERRO: instale Docker ou Podman.' >&2; exit 1; }
mkdir -p -- "$out"

container() {
    local step=$1
    local args=(run --rm -v "$repo:/src:ro" -v "$out:/out"
                -e "HOST_UID=$(id -u)" -e "HOST_GID=$(id -g)" -e "UPSTREAM_TESTS=$upstream_tests")
    # The signed snapshot is immutable, so cached .debs can be reused across runs.
    if [[ $use_cache == 1 ]]; then args+=(-v gnome-auth-carousel-apt:/var/cache/apt/archives); fi
    "$engine" "${args[@]}" ubuntu:24.04 bash "/src/scripts/container/$step.sh" 2>&1 | tee "$out/${step%%_*}.log"
}

if [[ $run_build == 1 ]]; then
    echo "==> Build em container ($engine); log em $out/build.log"
    container build_in_container
fi
if [[ $run_e2e == 1 ]]; then
    echo "==> E2E em container limpo; log em $out/e2e.log"
    container e2e_in_container
fi
echo "==> Concluido. Artefatos em $out"
