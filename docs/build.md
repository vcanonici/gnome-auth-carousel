# Compilar em ambiente isolado

Caminho recomendado: `./scripts/container_build.sh` (Docker ou Podman). Ele
executa os passos abaixo em containers descartáveis com APT apontado para
`snapshot.ubuntu.com/ubuntu/20260920T000000Z`: o arquivo atual do Ubuntu só
indexa a versão mais nova do gnome-shell, e o snapshot assinado ainda publica a
`46.0-0ubuntu6~24.04.14` exata. `apt-get source` confere o fonte contra os
índices assinados; os pacotes originais são conferidos com
`docs/original-packages.json`. Por padrão usa `DEB_BUILD_OPTIONS=nocheck`
(a suíte upstream precisa de pilha gráfica); `--upstream-tests` a inclui.

Passos manuais equivalentes, numa VM:

Use uma VM Ubuntu 24.04 com a toolchain Ubuntu e dependências de build de
GNOME Shell. A compilação não deve instalar dependências na máquina cujo
login será modificado.

O fonte original exato é `gnome-shell 46.0-0ubuntu6~24.04.14`, assinado pela
Ubuntu. Preserve a verificação da assinatura `.dsc` e os checksums antes de
extrair com `dpkg-source -x`. Sobre o fonte original ainda sem o patch:

```bash
./scripts/build.sh --in-build-vm /caminho/gnome-shell-original
```

O script valida os pontos de alteração antes de escrever, atualiza os recursos
GJS e compila com `dpkg-buildpackage -b -uc -us -j2`. Reaplicar sobre fonte já
modificado é recusado. O complemento 1.2 é construído separadamente e não tem
postinst que ative PAM.

A release oferece `gnome-shell-46.0-thinkpad2-source.tar.xz`: fonte completo já
modificado. Para esse artefato, extraia, instale dependências apenas na VM,
entre no diretório e execute diretamente `dpkg-buildpackage -b -uc -us -j2`.
O arquivo inclui `debian/copyright` e as licenças upstream. Esse build gera o
mesmo código-fonte, sem promessa de identidade binária entre toolchains.

Para montar a distribuição, reúna somente `gnome-shell`, `gnome-shell-common`
e `thinkpad-auth-policy` nas versões exatas em um diretório, então:

```bash
python3 scripts/release_manifest.py /caminho/pacotes /caminho/pacotes/packages-manifest.json
```

Antes de publicar outra versão, repita em GDM/Wayland real: senha incorreta
sem acionar leitor, senha sozinha negada, senha+segundo fator (digital e Trezor), timeout/três falhas,
cancelamento/liberação do leitor, vias alternativas negadas, TTY/SSH preservados,
dez desbloqueios, reboot, suspensão, restauração e timer. Teste hardware real
além de mock. Não apresente pm_test=freezer como suspensão física validada.

O instalador usa APIs Ubuntu e não adapta silenciosamente stacks PAM ou
versões novas. Nomes de arquivos internos thinkpad-* permanecem por
compatibilidade com o protocolo de marcadores da primeira implementação.
