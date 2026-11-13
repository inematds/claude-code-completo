#!/usr/bin/env python3
"""Cria 3 vídeos curtos de teste (barras coloridas + tom) para experimentar o montar_curso.py sem ter vídeos seus.

Uso: python3 ferramentas/videos_de_teste.py [pasta]   (padrão: exemplos/videos)
Gera aula1.mp4, aula2.mp4 e aula3.mp4, de 12 s cada, com ffmpeg local.
"""
from pathlib import Path
import shutil
import subprocess
import sys


def principal():
    pasta = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'exemplos' / 'videos')
    if not shutil.which('ffmpeg'):
        print('Erro: ffmpeg não encontrado. Instale o ffmpeg e rode de novo.', file=sys.stderr)
        return 1
    pasta.mkdir(parents=True, exist_ok=True)
    for numero, (tamanho, tom) in enumerate((('1280x720', 440), ('1920x1080', 554), ('1280x720', 659)), 1):
        destino = pasta / f'aula{numero}.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y',
                        '-f', 'lavfi', '-i', f'testsrc2=size={tamanho}:rate=30:duration=12',
                        '-f', 'lavfi', '-i', f'sine=frequency={tom}:duration=12',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(destino)],
                       check=True)
        print(f'Gravado: {destino}')
    return 0


if __name__ == '__main__':
    sys.exit(principal())
