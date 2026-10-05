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
