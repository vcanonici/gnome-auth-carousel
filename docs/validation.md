# Validacao e compatibilidade

Ubuntu 24.04, GNOME Shell 46.0-0ubuntu6~24.04.14, GDM 46.2, Wayland.

- VM: nove casos PAM (senha correta/incorreta, digital ausente/recusada,
  leitor desconectado, rotas alternativas, TTY e remoto) e dez desbloqueios.
- Instalacao via PID 1 com timer anterior aos pacotes, reboot e restauracao
  byte a byte testados na VM.
- Hardware: ThinkPad T15p Gen 3, leitor Synaptics Prometheus MIS.
  Usuario confirmou login, desbloqueio e retorno da suspensao com senha/digital.
- Interface em portugues, animacao 250 ms, respeita animacoes reduzidas.
- O mock do leitor nao prova comportamento de outros sensores. Cada novo
  dispositivo precisa concluir o piloto fisico antes de confirmar instalacao.
- Suspensao real da VM falhou no driver virtio_gpu tambem com Shell original;
  pm_test=freezer validou somente o fluxo de software da VM.
- ARM, outras distribuicoes/versoes, outros leitores e outras GPUs nao foram
  validados. A primeira distribuicao binaria suporta somente amd64 no par exato.
- A versao parametrizada passou prepare/start/confirm/restore na VM, com
  dez novos desbloqueios; nova conta carouseltest tambem passou login e fluxo
  de dois fatores. APT ocupado foi rejeitado antes de armar timer.

A interface nunca verifica senhas ou digitais: GDM/PAM/fprintd autentica.
TTY, SSH e sudo ficam fora da alteracao; login remoto proprio isento de digital.
Desbloqueio remoto de uma sessao local ainda exige digital fisica.

## v1.1.0 (fator Trezor, traducoes)

- `scripts/container_build.sh` em 2026-10-06: build no snapshot Ubuntu
  20260920T000000Z e e2e em container limpo, 35/35 verificacoes:
  - `install.py prepare --factor trezor` e `pilot.py` reais (systemctl simulado),
    PAM ativo identico ao payload, restauracao byte a byte e Shell original de volta;
  - pilhas `gdm-password` com `pamtester` para trezor e fingerprint: senha errada
    nao chama o 2o fator, senha + 2o fator autentica, 2o fator recusado nega,
    outro usuario/remoto/login/sudo inalterados, `gdm-fingerprint` bloqueada so
    para o alvo; `pam_u2f` e `pam_fprintd` reais sem dispositivo negam;
  - catalogos `.mo` instalados (pt_BR, ja, fallback en);
  - gnome-shell 46 headless renderiza o carrossel compilado em pt_BR e avanca
    para a etapa Trezor sem erro JS (`docs/trezor.png`).
- Registro do Trezor: `pamu2fcfg` 1.1.0 do Ubuntu falha com auto-atestacao
  (`FIDO_ERR_INVALID_ARGUMENT`); `scripts/register_trezor.sh` (pam-u2f 1.4.0 em
  container) registrou um Trezor Safe e o `pam_u2f` 1.1.0 do sistema autenticou.
- O segundo fator e simulado no e2e; login fisico com Trezor e obrigatorio no piloto.
- Sem o Trezor conectado o `pam_u2f` falha imediatamente e a tentativa volta a senha.
