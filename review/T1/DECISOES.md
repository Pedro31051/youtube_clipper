# Registro de Decisões Técnicas — Fase T1

## Decisão 1: Normalização de Offsets Pós-Download em URLs do YouTube (`pipeline.py`)
- **Decisão**: Após a invocação de `downloader.download_segment`, redefinir os parâmetros de corte para `cut_start = 0.0` e `cut_end = float(end_sec - start_sec)`. Para mídias locais, manter os timestamps originais `cut_start = float(start_sec)` e `cut_end = float(end_sec)`.
- **Alternativas Descartadas**: Re-download do arquivo bruto completo do YouTube via `yt-dlp` sem aplicar `-ss/-t` no download.
- **Por quê**: Fazer o download apenas do segmento desejado reduz drasticamente o tráfego de rede e o tempo de parede, além de economizar espaço em disco. A normalização garante que o corte subsequente no `FFmpegProcessor` opere sobre a linha do tempo do arquivo já fatiado ($t=0.0$).

## Decisão 2: Validação de Duração e Formato via `ffprobe` com Saída JSON (`processor.py`)
- **Decisão**: Utilizar `run_cmd` para executar `ffprobe -show_entries format=duration -show_entries stream=codec_type -of json` e tratar de forma resiliente tanto saídas em dicionário JSON quanto retornos numéricos de mocks.
- **Alternativas Descartadas**: Utilizar `subprocess.run` direto fora de `run_cmd`.
- **Por quê**: O uso de `run_cmd` é estritamente obrigatório pelo contrato de auditoria (`test_contracts.py` proíbe chamadas diretas a `subprocess` fora de `src/cortes/log.py`). A checagem via JSON extrai explicitamente o tempo de duração e a presença de streams de vídeo válidas.

## Decisão 3: Verificação Dupla de Mídia Corrompida ou Vazia
- **Decisão**: Rejeitar arquivos onde `st_size <= 1024` ou onde a duração retornada pelo `ffprobe` seja $\le 0.0$ segundos, lançando a exceção `ProcessingError` com código de erro 4.
- **Por quê**: Em execuções anteriores, falhas do FFmpeg em offsets fora de faixa produziam MP4s vazios de 262 bytes com exit code 0. A verificação transforma esse erro silencioso em um erro ruidoso e auditável.

## Decisão 4: Mídia Sintética `lavfi` nos Testes Anti-Regressão (`test_regression_media.py`)
- **Decisão**: Utilizar `ffmpeg -f lavfi -i testsrc=duration=5:size=640x360:rate=30` para gerar arquivos de mídia reais em ambiente offline.
- **Por quê**: Permite testar a extração real de propriedades de vídeo e áudio via FFmpeg/ffprobe sem dependência de rede externa ou de arquivos pesados no repositório.
