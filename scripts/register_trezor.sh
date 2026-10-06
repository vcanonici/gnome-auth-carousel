#!/bin/bash
# Register a Trezor (FIDO2/U2F) for pam_u2f and prove one real authentication.
#
# Ubuntu 24.04 ships pamu2fcfg 1.1.0, which rejects authenticators using self
# attestation (Trezor) with "fido_cred_verify (-7) FIDO_ERR_INVALID_ARGUMENT".
# pam-u2f >= 1.2 falls back to fido_cred_verify_self. Only the registration tool
# is replaced, inside a disposable container; the system pam_u2f.so 1.1.0 then
# verifies the assertion, which this script tests before the login uses it.
set -euo pipefail

# Same path as U2F_AUTHFILE in scripts/policy.py.
AUTHFILE=/etc/security/thinkpad-auth/u2f_keys
CHECK_SERVICE=/etc/pam.d/thinkpad-u2f-check
PAM_U2F_TAG=pam_u2f-1.4.0
PAM_U2F_COMMIT=1d85db26b590c191a508d06eddc86fbff6b5009e
IMAGE=gnome-auth-carousel/pamu2fcfg:1.4.0

usage() {
    cat <<'USAGE'
Uso: sudo scripts/register_trezor.sh --user USUARIO [--host HOST] [--append] [--no-verify]

  --user USUARIO  conta local que vai usar o Trezor
  --host HOST     origem FIDO pam://HOST (padrao: hostname em minusculas);
                  use o mesmo valor em install.py prepare --host
  --append        acrescenta outro Trezor (reserva) ao usuario ja registrado
  --no-verify     nao testa a autenticacao real depois do registro

Conecte e desbloqueie o Trezor (PIN no aparelho) antes de rodar. O Trezor pede
confirmacao duas vezes: registro e teste de autenticacao.
USAGE
}

die() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

user='' host=$(hostname | tr '[:upper:]' '[:lower:]') append=0 verify=1
while [[ $# -gt 0 ]]; do
    case $1 in
        --user) user=$2; shift 2 ;;
        --host) host=$2; shift 2 ;;
        --append) append=1; shift ;;
        --no-verify) verify=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[[ $EUID == 0 ]] || die 'rode com sudo (grava em /etc/security).'
[[ $user =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] && id "$user" >/dev/null 2>&1 || die "usuario local invalido: '$user'"
[[ $host =~ ^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$ ]] || die "host invalido: '$host'"
engine=$(command -v docker || command -v podman || true)
[[ -n $engine ]] || die 'instale Docker ou Podman.'

# Trezor Model T / Safe (1209:53c1) and Model One (534c:0001) FIDO interfaces.
devices=()
for uevent in /sys/class/hidraw/hidraw*/device/uevent; do
    if grep -qiE '^HID_ID=0003:0000(1209:000053C1|534C:00000001)$' "$uevent"; then
        devices+=("--device=/dev/$(basename "$(dirname "$(dirname "$uevent")")")")
    fi
done
[[ ${#devices[@]} -gt 0 ]] || die 'Trezor nao encontrado: conecte e desbloqueie o aparelho.'

if ! "$engine" image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "==> Compilando pamu2fcfg $PAM_U2F_TAG em container (uma vez)"
    "$engine" build -t "$IMAGE" - <<DOCKERFILE
FROM ubuntu:24.04
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      autoconf automake ca-certificates git libfido2-dev libpam0g-dev libssl-dev libtool make pkg-config \
 && git clone --quiet --branch $PAM_U2F_TAG https://github.com/Yubico/pam-u2f /pam-u2f \
 && test "\$(git -C /pam-u2f rev-parse HEAD)" = $PAM_U2F_COMMIT \
 && cd /pam-u2f && autoreconf --install >/dev/null && ./configure --disable-man >/dev/null && make -s \
 && install -m 0755 pamu2fcfg/pamu2fcfg /usr/local/bin/pamu2fcfg \
 && pamu2fcfg --version
DOCKERFILE
fi

echo "==> Confirme o registro no Trezor (origem pam://$host)"
args=(-o "pam://$host" -i "pam://$host")
if [[ $append == 1 ]]; then args+=(-n); else args+=(-u "$user"); fi
# /run/udev lets libfido2 enumerate the passed hidraw node inside the container.
credential=$("$engine" run --rm "${devices[@]}" -v /run/udev:/run/udev:ro "$IMAGE" pamu2fcfg "${args[@]}")
credential=$(printf '%s' "$credential" | tr -d '\r\n')
if [[ $append == 1 ]]; then
    [[ $credential =~ ^:[^:,]+,[^,]+,[a-z0-9]+,[+a-z]*$ ]] || die "saida inesperada do pamu2fcfg: $credential"
else
    [[ $credential =~ ^$user:[^:,]+,[^,]+,[a-z0-9]+,[+a-z]*$ ]] || die "saida inesperada do pamu2fcfg: $credential"
fi

echo "==> Gravando $AUTHFILE"
install -d -m 0755 "$(dirname "$AUTHFILE")"
tmp=$(mktemp "$AUTHFILE.XXXXXX")
trap 'rm -f "$tmp"' EXIT
existing=''
[[ -f $AUTHFILE ]] && existing=$(grep -v "^$user:" "$AUTHFILE" || true)
current=$( [[ -f $AUTHFILE ]] && grep "^$user:" "$AUTHFILE" || true)
if [[ $append == 1 ]]; then
    [[ -n $current ]] || die "nenhum Trezor registrado para $user; registre o primeiro sem --append."
    line=$current$credential
else
    line=$credential
fi
{ [[ -n $existing ]] && printf '%s\n' "$existing"; printf '%s\n' "$line"; } > "$tmp"
chown root:root "$tmp"
chmod 0644 "$tmp"
mv "$tmp" "$AUTHFILE"

if [[ $verify == 1 ]]; then
    if ! command -v pamtester >/dev/null; then
        echo '==> Instalando pamtester (teste de autenticacao)'
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pamtester >/dev/null
    fi
    # Temporary service with only pam_u2f: never part of the login stacks.
    trap 'rm -f "$tmp" "$CHECK_SERVICE"' EXIT
    printf 'auth required pam_u2f.so authfile=%s origin=pam://%s appid=pam://%s\naccount required pam_permit.so\n' \
        "$AUTHFILE" "$host" "$host" > "$CHECK_SERVICE"
    echo "==> Confirme no Trezor de novo: teste real com o pam_u2f do sistema"
    pamtester "$(basename "$CHECK_SERVICE")" "$user" authenticate </dev/null \
        || die 'o pam_u2f do sistema nao autenticou este Trezor; nao instale o carrossel com --factor trezor.'
fi
echo "TREZOR_REGISTRADO $user pam://$host"
