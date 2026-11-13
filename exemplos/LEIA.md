Copie `meu-curso.json` e troque o título e as descrições pelos seus textos.
Em cada capítulo, troque `titulo` e `arquivo` pelo seu vídeo.
Os caminhos são relativos ao JSON: `videos/aula1.mp4` fica em `exemplos/videos/`; também vale caminho absoluto ou `~`.
Sem vídeos ainda? `python3 ferramentas/videos_de_teste.py` cria 3 de teste em `exemplos/videos/`.
Na raiz do projeto, rode: `python3 ferramentas/montar_curso.py exemplos/meu-curso.json --saida saida/curso.mp4`.
Pegue o MP4, os capítulos e a descrição em `saida/`; use `--so-capitulos` para gerar apenas uma estimativa em texto.
