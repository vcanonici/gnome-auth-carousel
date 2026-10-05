#!/usr/bin/python3
"""Fixed recovery menu on independent root TTY; no general shell or credentials."""
import os
from pathlib import Path
import subprocess
import sys

if os.geteuid() != 0 or not os.isatty(0) or len(sys.argv) != 2:
    raise SystemExit('Exige root, TTY e um diretorio de snapshot.')
root = Path(sys.argv[1]).resolve(strict=True)
if not root.is_relative_to('/var/backups/thinkpad-auth') or not (root / 'carousel.json').is_file():
    raise SystemExit('Snapshot invalido.')
while True:
    print('\nRecuperacao da autenticacao ThinkPad — console independente')
    print('1: restaurar autenticacao e pacotes originais')
    print('2: mostrar estado da janela de recuperacao')
    print('3: fechar este console')
    try:
        choice = input('Escolha: ').strip()
    except EOFError:
        break
    if choice == '1':
        result = subprocess.run(['/usr/local/sbin/thinkpad-carousel-control', 'restore', str(root)])
        print('Restauracao concluida.' if result.returncode == 0 else 'Restauracao incompleta; consulte o journal.')
    elif choice == '2':
        print('Confirmado:', (root / 'confirmed').exists(), 'Restaurado:', (root / 'restored').exists())
        subprocess.run(['systemctl', 'list-timers', 'thinkpad-carousel-rollback.timer', '--no-pager'])
    elif choice == '3':
        break
