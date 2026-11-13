"""Verificação local com vídeos sintéticos; não usa o curso real."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
PROGRAMA = RAIZ / 'ferramentas' / 'montar_curso.py'
especificacao = importlib.util.spec_from_file_location('montador', PROGRAMA)
montador = importlib.util.module_from_spec(especificacao)
especificacao.loader.exec_module(montador)
pytestmark = pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='ffmpeg e ffprobe são necessários para estes testes.')


def rodar(entrada, saida, *opcoes):
    return subprocess.run([sys.executable, str(PROGRAMA), str(entrada), '--saida', str(saida),
                           '--cartao-s', '1', '--largura', '640', '--altura', '360', *opcoes],
                          capture_output=True, text=True, timeout=180)


@pytest.fixture
def curso(tmp_path):
    capitulos = []
    for numero, (tamanho, duracao) in enumerate([('1280x720', 2), ('1920x1080', 3), ('640x360', 4)], 1):
        arquivo = tmp_path / f'aula {numero}.mp4'
        comando = ['ffmpeg', '-v', 'error', '-y', '-filter_threads', '2', '-f', 'lavfi', '-i', f'testsrc=size={tamanho}:rate=30']
        if numero != 3:
            comando += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-c:a', 'aac']
        comando += ['-t', str(duracao), '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(arquivo)]
        subprocess.run(comando, check=True, capture_output=True, timeout=60)
        capitulos.append({'arquivo': arquivo.name, 'titulo': f'Aula {numero}', 'extra': 'ignorado'})
    dados = {'titulo': 'Curso de teste', 'descricao_topo': 'Aprenda aqui.', 'descricao_fim': 'Bom estudo!', 'capitulos': capitulos}
    entrada = tmp_path / 'curso.json'
    entrada.write_text(json.dumps(dados), encoding='utf-8')
    return entrada, dados


def segundos(texto):
    valor = 0
    for parte in texto.split(':'):
        valor = valor * 60 + int(parte)
    return valor


def test_montagem_completa(curso, tmp_path):
    entrada, dados = curso
    saida = tmp_path / 'saida' / 'curso.mp4'
    resultado = rodar(entrada, saida, '--manter-temp')
    assert resultado.returncode == 0, resultado.stderr
    pasta = Path(resultado.stdout.split('Temporários preservados: ')[1].strip())
    try:
        assert saida.is_file()
        duracao, fluxos = montador.sondar(saida)
        video = next(f for f in fluxos if f['codec_type'] == 'video')
        audio = next(f for f in fluxos if f['codec_type'] == 'audio')
        assert (video['width'], video['height']) == (640, 360)
        assert video['pix_fmt'] == 'yuv420p'
        assert audio['sample_rate'] == '48000' and audio['channels'] == 2
        assert abs(duracao - 12) <= 1
        linhas = saida.with_name('curso-capitulos.txt').read_text().splitlines()
        assert len(linhas) == 3 and linhas[0].startswith('00:00 ')
        tempos = [segundos(linha.split(' ')[0]) for linha in linhas]
        assert tempos == sorted(set(tempos))
        acumulado = 0
        for numero, tempo in enumerate(tempos, 1):
            assert abs(tempo - acumulado) <= 1
            acumulado += montador.sondar(pasta / f'cartao-{numero}.mp4')[0]
            acumulado += montador.sondar(pasta / f'video-{numero}.mp4')[0]
        assert abs(duracao - acumulado) <= 1
        descricao = saida.with_name('curso-descricao.txt').read_text()
        assert 'Capítulos:' in descricao
        assert descricao.startswith('Aprenda aqui.\n\nCapítulos:')
        assert descricao.endswith('Bom estudo!\n')
        assert all(c['titulo'] in descricao for c in dados['capitulos'])
    finally:
        shutil.rmtree(pasta)


@pytest.mark.parametrize('titulo,arquivo,mensagem', [('Aula', 'ausente.mp4', 'arquivo inexistente'), ('  ', 'ausente.mp4', 'título vazio')])
def test_erros(tmp_path, titulo, arquivo, mensagem):
    entrada = tmp_path / 'invalido.json'
    entrada.write_text(json.dumps([{'titulo': titulo, 'arquivo': arquivo}]))
    resultado = rodar(entrada, tmp_path / 'curso.mp4')
    assert resultado.returncode != 0
    assert 'Capítulo 1' in resultado.stderr and mensagem in resultado.stderr


@pytest.mark.parametrize('valor,esperado', [(0, '00:00'), (65, '01:05'), (3725, '1:02:05')])
def test_formato_tempo(valor, esperado):
    assert montador.formatar_tempo(valor) == esperado


def test_cartao(tmp_path):
    destino = tmp_path / 'cartao.png'
    montador.gerar_cartao(destino, 'Um título grande para conferir a quebra de linhas do cartão', 'Curso de teste', 1, 3, 640, 360)
    with Image.open(destino) as imagem:
        assert imagem.size == (640, 360)
        assert imagem.getpixel((0, 0)) == (12, 12, 16)


@pytest.mark.parametrize('formato', ['json', 'yaml', 'lista'])
def test_so_capitulos(curso, tmp_path, formato):
    entrada, dados = curso
    if formato == 'yaml':
        yaml = pytest.importorskip('yaml', reason='PyYAML opcional não instalado.')
        entrada = tmp_path / 'curso.yaml'
        entrada.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding='utf-8')
    elif formato == 'lista':
        entrada.write_text(json.dumps(dados['capitulos']), encoding='utf-8')
    saida = tmp_path / 'estimativa.mp4'
    resultado = rodar(entrada, saida, '--so-capitulos')
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.startswith('ESTIMATIVA:')
    assert not saida.exists()
    assert saida.with_name('estimativa-capitulos.txt').read_text().splitlines() == ['00:00 Aula 1', '00:03 Aula 2', '00:07 Aula 3']
    assert 'Capítulos:' in saida.with_name('estimativa-descricao.txt').read_text()
    assert 'menos de 10 s' in resultado.stderr
