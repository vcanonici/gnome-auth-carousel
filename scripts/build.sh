#!/bin/bash
set -euo pipefail
if [[ $# != 2 || "$1" != --in-build-vm ]]; then
  echo 'Uso: build.sh --in-build-vm /caminho/fonte-gnome-shell-original' >&2
  echo 'Execute na VM de compilacao com dependencias Ubuntu ja instaladas.' >&2
  exit 2
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir=$(realpath -- "$2")
python3 "$script_dir/patch_source.py" "$source_dir"
cd -- "$source_dir"
dpkg-buildpackage -b -uc -us -j2
python3 "$script_dir/build_policy_package.py" "$(dirname -- "$source_dir")"
echo 'Build concluido. Crie manifesto dos tres pacotes com release_manifest.py.'
