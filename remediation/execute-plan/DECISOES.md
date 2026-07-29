# Decisões — execução do plano de melhorias

## Fase 0 — baseline e isolamento

- As alterações são feitas na branch local `codex/execute-improvement-plan`, criada a
  partir de `ff86df462238a34db2fb7f2a96e680c7d3e5fbcf`.
- Nenhum commit, push, publicação ou alteração de credenciais faz parte desta execução.
- O NotebookLM `YouTube Clipper — Arquitetura, IA, Vídeo e Operação` é a fonte de
  consulta para dúvidas de prioridade e arquitetura.

## Fase 1 — validação física compartilhada

- Toda saída de mídia passa a poder ser validada por um único gateway baseado em
  `ffprobe`.
- O comando externo continua passando por `cortes.log.run_cmd`; chamadas diretas a
  `subprocess` permanecem proibidas.
- A validação mínima exige arquivo regular maior que 1 KiB, duração positiva e stream
  de vídeo. Renders verticais também exigem a resolução solicitada.
- Alternativa descartada: validar apenas existência e tamanho. O FFmpeg pode retornar
  sucesso e ainda produzir um contêiner sem duração ou stream utilizável.

## Fases seguintes

As decisões de ingestão, segurança, dashboard e empacotamento serão registradas neste
documento à medida que seus patches forem implementados e verificados.

## Fase 2 — ingestão e download

- `run_ingest` usa download completo, sem fabricar o intervalo inválido `0–0`.
- O pipeline de corte continua usando download segmentado e normaliza o arquivo baixado
  para `0..(fim-início)`, evitando corte duplo.
- Cookies são dependência explícita de cada `YouTubeDownloader`; a CLI e o dashboard
  não mutam mais `YOUTUBE_COOKIES_FILE` durante uma requisição.
- A compatibilidade de leitura da variável de ambiente foi mantida apenas como fallback
  para operadores existentes.
- `nocheckcertificate` é removido mesmo se aparecer nas opções customizadas.
- O fallback de arquivo baixado só aceita artefatos novos ou alterados pela execução.

Alternativa descartada: consultar duração para transformar `0–0` em um segmento. A
ingestão precisa da fonte completa e o downloader já oferece um fluxo sem range.

## Fase 3 — proteção de dados e recursos

- O Google Drive usa somente o escopo `drive.file`; upload é privado por padrão.
- Link `anyone/reader` exige `public_link=True` explícito e o resultado informa se a
  publicação foi solicitada.
- Caminhos padrão de credenciais deixaram de apontar para a máquina do autor e agora
  usam `~/.config/youtube_clipper/`, sem criar ou alterar arquivos de credenciais.
- O dashboard aceita no máximo 64 KiB de JSON por padrão e rejeita `Content-Length`
  ausente, inválido, zero, negativo ou acima do limite.
- Análise e render usam um semáforo não bloqueante, com um job por padrão; excesso
  recebe HTTP 503 e o slot é liberado mesmo quando o job falha.
- Downloads HTTP são transmitidos em blocos de 1 MiB e permanecem confinados ao
  `output_dir` dedicado.

Alternativa descartada: manter uploads públicos para preservar o link. `webViewLink`
continua existindo para usuários autorizados, sem ampliar a permissão do arquivo.

## Fase 4 — empacotamento, CI e operação

- A versão mínima passa a Python 3.10, alinhada à sintaxe usada e ao suporte atual do
  `yt-dlp`; a CI cobre 3.10 e 3.12.
- CUDA/cuBLAS/cuDNN saem da instalação base e entram no extra `gpu`; a CI comum instala
  `.[dev]` e o runner NVIDIA instala `.[dev,gpu]`.
- Benchmarks empíricos recebem o marcador `performance`. A CI funcional os exclui e o
  workflow GPU os executa explicitamente, sem transformar variação de hardware em falha
  funcional.
- `requirements.txt` delega a fonte de dependências ao `pyproject.toml`, evitando listas
  divergentes.
- `.gitignore` protege cookies, tokens, credenciais, `.env`, parciais de download e o
  diretório de saída.

Alternativa descartada: tornar Python 3.12 obrigatório. O código e as dependências
suportam 3.10, e uma matriz preserva compatibilidade sem limitar operadores.

