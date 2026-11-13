#!/usr/bin/env python3
"""Monta um curso com cartões e vídeos locais, sem serviços externos."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont


class ErroCurso(Exception):
    """Erro que pode ser explicado diretamente à pessoa."""


def executar(comando):
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode:
        raise ErroCurso(f"Falha em {comando[0]}: {resultado.stderr[-3000:]}")
    return resultado.stdout


def sondar(arquivo):
    dados = json.loads(executar([
        'ffprobe', '-v', 'error', '-show_format', '-show_streams',
        '-of', 'json', str(arquivo)]))
    duracao = float(dados.get('format', {}).get('duration', 0))
    if not math.isfinite(duracao) or duracao <= 0:
        raise ErroCurso('duração ausente ou menor ou igual a zero')
    return duracao, dados['streams']


def carregar_entrada(caminho):
    caminho = Path(caminho).expanduser().resolve()
    texto = caminho.read_text(encoding='utf-8')
    if caminho.suffix.lower() in ('.yaml', '.yml'):
        try:
            import yaml
        except ImportError as erro:
            raise ErroCurso('Para ler YAML, use JSON ou instale: pip install pyyaml') from erro
        try:
            dados = yaml.safe_load(texto)
        except yaml.YAMLError as erro:
            raise ErroCurso(f'YAML inválido: {erro}') from erro
    else:
        dados = json.loads(texto)
    if isinstance(dados, list):
        dados = {'titulo': 'Meu curso', 'capitulos': dados}
    if not isinstance(dados, dict):
        raise ErroCurso('A entrada deve ser um objeto ou uma lista de capítulos.')
    for campo in ('titulo', 'descricao_topo', 'descricao_fim'):
        if campo == 'titulo' or campo in dados:
            if not isinstance(dados.get(campo), str) or (campo == 'titulo' and not dados[campo].strip()):
                raise ErroCurso(f'Campo {campo} deve ser um texto não vazio.' if campo == 'titulo' else f'Campo {campo} deve ser texto.')
    capitulos = dados.get('capitulos')
    if not isinstance(capitulos, list) or not capitulos:
        raise ErroCurso('Informe uma lista não vazia de capítulos.')
    for numero, capitulo in enumerate(capitulos, 1):
        try:
            if not isinstance(capitulo, dict):
                raise ErroCurso('dados devem ser um objeto')
            if not isinstance(capitulo.get('titulo'), str) or not capitulo['titulo'].strip():
                raise ErroCurso('título vazio ou inválido')
            capitulo['titulo'] = ' '.join(capitulo['titulo'].split())
            if not isinstance(capitulo.get('arquivo'), str) or not capitulo['arquivo'].strip():
                raise ErroCurso('informe o arquivo')
            arquivo = Path(capitulo['arquivo']).expanduser()
            if not arquivo.is_absolute():
                arquivo = caminho.parent / arquivo
            arquivo = arquivo.resolve()
            if not arquivo.is_file():
                raise ErroCurso(f'arquivo inexistente: {arquivo}')
            duracao, fluxos = sondar(arquivo)
            if not any(f['codec_type'] == 'video' and not f.get('disposition', {}).get('attached_pic') for f in fluxos):
                raise ErroCurso('arquivo não tem vídeo')
            capitulo.update(arquivo=arquivo, duracao=duracao,
                            tem_audio=any(f['codec_type'] == 'audio' for f in fluxos))
        except (ErroCurso, ValueError) as erro:
            raise ErroCurso(f'Capítulo {numero}: {erro}') from erro
    return dados


def formatar_tempo(segundos, usar_horas=False):
    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if usar_horas or horas:
        return f'{horas}:{minutos:02d}:{segundos:02d}'
    return f'{minutos:02d}:{segundos:02d}'


def fonte(tamanho, peso='SemiBold'):
    caminho = Path(__file__).parent / 'fontes' / 'Sora.ttf'
    if caminho.exists():
        letra = ImageFont.truetype(str(caminho), tamanho)
        letra.set_variation_by_name(peso)
        return letra
    print('Aviso: Sora.ttf ausente; usando DejaVuSans-Bold.', file=sys.stderr)
    return ImageFont.truetype('DejaVuSans-Bold.ttf', tamanho)


def quebrar_linhas(texto, desenho, letra, limite):
    linhas = []
    linha = ''
    for palavra in texto.split():
        candidato = f'{linha} {palavra}'.strip()
        if desenho.textlength(candidato, font=letra) <= limite:
            linha = candidato
            continue
        if linha:
            linhas.append(linha)
        linha = ''
        for caractere in palavra:
            if linha and desenho.textlength(linha + caractere, font=letra) > limite:
                linhas.append(linha)
                linha = ''
            linha += caractere
    if linha:
        linhas.append(linha)
    return linhas


def gerar_cartao(destino, titulo, titulo_curso, numero, total, largura, altura):
    imagem = Image.new('RGB', (largura, altura), '#0c0c10')
    desenho = ImageDraw.Draw(imagem)
    margem = int(largura * .1)
    tamanho = max(8, int(altura * .085))
    while True:
        letra = fonte(tamanho, 'ExtraBold')
        linhas = quebrar_linhas(titulo, desenho, letra, largura * .8)
        if len(linhas) <= 3 or tamanho <= 1:
            break
        tamanho -= 1
    texto = '\n'.join(linhas)
    espacamento = max(1, tamanho // 4)
    caixa = desenho.multiline_textbbox((0, 0), texto, font=letra, spacing=espacamento)
    y = (altura - (caixa[3] - caixa[1])) / 2 - caixa[1]
    desenho.multiline_text((margem, y), texto, font=letra, fill='white', spacing=espacamento)
    desenho.text((margem, altura * .12), f'CAPÍTULO {numero} de {total}',
                 font=fonte(max(1, int(altura * .025))), fill='#FACC15')
    base = y + caixa[3] + altura * .04
    desenho.rectangle((margem, base, margem + largura * .12, base + max(1, altura * .005)), fill='#FACC15')
    tamanho_rodape = max(1, int(altura * .022))
    while tamanho_rodape > 1 and desenho.textlength(titulo_curso, font=fonte(tamanho_rodape)) > largura * .8:
        tamanho_rodape -= 1
    desenho.text((margem, altura * .9), titulo_curso, font=fonte(tamanho_rodape), fill='#cccccc')
    imagem.save(destino)


def gravar_textos(saida, dados, duracoes):
    total = sum(duracoes)
    acumulado = 0.0
    linhas = []
    for capitulo, duracao in zip(dados['capitulos'], duracoes):
        # O primeiro marcador é sempre 00:00, inclusive nos cursos longos.
        tempo = '00:00' if not linhas else formatar_tempo(acumulado, total > 3600)
        linhas.append(f"{tempo} {capitulo['titulo']}")
        acumulado += duracao
    texto = '\n'.join(linhas) + '\n'
    capitulos = saida.with_name(saida.stem + '-capitulos.txt')
    descricao = saida.with_name(saida.stem + '-descricao.txt')
    capitulos.write_text(texto, encoding='utf-8')
    blocos = [dados.get('descricao_topo', '').strip(), 'Capítulos:\n' + texto.rstrip(), dados.get('descricao_fim', '').strip()]
    descricao.write_text('\n\n'.join(b for b in blocos if b) + '\n', encoding='utf-8')
    print(texto, end='')
    return [capitulos, descricao]


def avisar(duracoes):
    if len(duracoes) < 3:
        print('Aviso: o YouTube pede pelo menos 3 capítulos.', file=sys.stderr)
    for numero, duracao in enumerate(duracoes, 1):
        if duracao < 10:
            print(f'Aviso: capítulo {numero} tem menos de 10 s, contando o cartão (regra do YouTube).', file=sys.stderr)


def montar(argumentos, dados, pasta):
    segmentos = []
    duracoes = []
    codificacao = ['-c:v', 'libx264', '-threads', '2', '-crf', '20', '-preset', 'medium',
                   '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '192k',
                   '-video_track_timescale', '90000']
    silencio = ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    for numero, capitulo in enumerate(dados['capitulos'], 1):
        print(f"Montando capítulo {numero}/{len(dados['capitulos'])}: {capitulo['titulo']}", flush=True)
        png = pasta / f'cartao-{numero}.png'
        cartao = pasta / f'cartao-{numero}.mp4'
        video = pasta / f'video-{numero}.mp4'
        gerar_cartao(png, capitulo['titulo'], dados['titulo'], numero, len(dados['capitulos']), argumentos.largura, argumentos.altura)
        executar(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-framerate', str(argumentos.fps), '-i', str(png)] + silencio +
                 ['-map', '0:v:0', '-map', '1:a:0', '-t', str(argumentos.cartao_s)] + codificacao + [str(cartao)])
        entradas = ['-i', str(capitulo['arquivo'])]
        if not capitulo['tem_audio']:
            entradas += silencio
        filtro = (f'scale={argumentos.largura}:{argumentos.altura}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                  f'pad={argumentos.largura}:{argumentos.altura}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={argumentos.fps},setpts=PTS-STARTPTS')
        executar(['ffmpeg', '-v', 'error', '-y', '-filter_threads', '2'] + entradas +
                 ['-map', '0:v:0', '-map', '0:a:0' if capitulo['tem_audio'] else '1:a:0',
                  '-vf', filtro, '-af', 'asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,apad',
                  '-t', str(capitulo['duracao'])] + codificacao + [str(video)])
        segmentos.extend([cartao, video])
        duracoes.append(sondar(cartao)[0] + sondar(video)[0])
    lista = pasta / 'segmentos.txt'
    lista.write_text(''.join(f"file '{s.name}'\n" for s in segmentos), encoding='utf-8')
    executar(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '1', '-i', str(lista),
              '-c', 'copy', '-movflags', '+faststart', str(argumentos.saida)])
    if not argumentos.saida.is_file() or abs(sondar(argumentos.saida)[0] - sum(duracoes)) > 1:
        raise ErroCurso('A duração do MP4 não confere com a soma dos segmentos (tolerância de 1 s).')
    return duracoes


def principal():
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument('entrada', type=Path, help='Arquivo JSON ou YAML do curso')
    analisador.add_argument('--saida', required=True, type=Path, help='MP4 de destino')
    analisador.add_argument('--cartao-s', type=float, default=3, help='Duração de cada cartão em segundos')
    analisador.add_argument('--largura', type=int, default=1920)
    analisador.add_argument('--altura', type=int, default=1080)
    analisador.add_argument('--fps', type=int, default=30)
    analisador.add_argument('--so-capitulos', action='store_true', help='Gera somente os textos estimados')
    analisador.add_argument('--manter-temp', action='store_true', help='Preserva os segmentos temporários')
    argumentos = analisador.parse_args()
    pasta = None
    try:
        for programa in ('ffmpeg', 'ffprobe'):
            if not shutil.which(programa):
                raise ErroCurso(f'{programa} não encontrado. Instale o ffmpeg e coloque seus executáveis no PATH.')
        if not math.isfinite(argumentos.cartao_s) or argumentos.cartao_s <= 0 or argumentos.fps <= 0:
            raise ErroCurso('A duração do cartão e o fps devem ser positivos.')
        if any(valor < 2 or valor % 2 for valor in (argumentos.largura, argumentos.altura)):
            raise ErroCurso('Largura e altura devem ser números pares positivos, de pelo menos 2 pixels.')
        dados = carregar_entrada(argumentos.entrada)
        argumentos.saida = argumentos.saida.expanduser().resolve()
        if argumentos.saida in [argumentos.entrada.resolve()] + [c['arquivo'] for c in dados['capitulos']]:
            raise ErroCurso('A saída não pode substituir a entrada ou um vídeo original.')
        argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
        if argumentos.so_capitulos:
            print('ESTIMATIVA: tempos calculados pelos originais e cartões; nenhum MP4 será criado.')
            duracoes = [c['duracao'] + argumentos.cartao_s for c in dados['capitulos']]
        else:
            pasta = Path(tempfile.mkdtemp(prefix='montar-curso-'))
            duracoes = montar(argumentos, dados, pasta)
        avisar(duracoes)
        caminhos = gravar_textos(argumentos.saida, dados, duracoes)
        if not argumentos.so_capitulos:
            caminhos.insert(0, argumentos.saida)
        total = int(sum(duracoes))
        print(f'Duração total: {total // 60}:{total % 60:02d} | Capítulos: {len(duracoes)}')
        for caminho in caminhos:
            print(f'Gravado: {caminho}')
        return 0
    except (ErroCurso, OSError, ValueError) as erro:
        print(f'Erro: {erro}', file=sys.stderr)
        return 1
    finally:
        if pasta:
            if argumentos.manter_temp:
                print(f'Temporários preservados: {pasta}')
            else:
                shutil.rmtree(pasta)


if __name__ == '__main__':
    sys.exit(principal())
