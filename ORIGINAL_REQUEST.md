# Original User Request

## Initial Request — 2026-07-26T11:50:41Z

Uma ferramenta de linha de comando (CLI) em Python 3.x para automação de cortes de vídeos do YouTube, permitindo processar vídeos, extrair trechos específicos por timestamps e gerar clipes formatados de maneira eficiente e robusta.

Working directory: /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper
Integrity mode: development

## Requirements

### R1. Interface de Linha de Comando e Processamento de Cortes (Python 3.x)
A ferramenta deve fornecer uma interface CLI em Python 3.x que receba URLs de vídeos do YouTube (ou arquivos locais) e parâmetros de tempo (início, fim ou duração), realizando a extração dos cortes com suporte a formatos de saída padrão.

### R2. Arquitetura Modular e Qualidade de Nível de Produção
O projeto deve ser construído com arquitetura modular limpa (separando CLI, download/integração e processamento de mídia), utilizando tipagem (type hints), tratamento de exceções robusto e conformidade com boas práticas Python (PEP 8).

### R3. Suíte de Testes Automatizados e Verificação Programa
Incluir testes automatizados reutilizáveis (utilizando `pytest`) para validação dos parsers de argumento, formatação de timestamps, tratamento de erros de entrada e integração dos módulos da aplicação.

## Verification Resources

- **pytest**: Testes automatizados executáveis via `pytest` para validação programática dos módulos.
- **Validação CLI**: Execução sintática e de help via `python3 -m youtube_clipper --help`.

## Acceptance Criteria

### Funcionalidade CLI
- [ ] O comando CLI aceita parâmetros claros para URL/vídeo de entrada, tempo inicial (`--start`), tempo final (`--end`) e arquivo/diretório de saída (`--output`).
- [ ] Mensagens de erro amigáveis são exibidas para entradas inválidas (ex: formato de timestamp incorreto ou URL inválida).

### Qualidade de Código e Testes
- [ ] A suíte de testes automatizados com `pytest` roda e passa com 100% de sucesso.
- [ ] O código possui type hints em todas as funções/métodos principais e passa em checagens de sintaxe/lint sem erros.

### Documentação
- [ ] `README.md` completo com guia de instalação, requisitos de sistema (ex: `ffmpeg`, `yt-dlp`), instruções de uso da CLI e exemplos de comandos para cortes.

## Follow-up — 2026-07-26T13:04:04Z

# Teamwork Project: YouTube AI Clipper & Analyzer Dashboard

Desenvolvimento de um painel web moderno, responsivo e completo para o YouTube AI Clipper & Analyzer, integrado ao Google Drive MCP, com suíte completa de testes e verificação E2E.

Working directory: /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper
Integrity mode: development

## Requirements

### R1. Painel Web Avançado e Responsivo (Dashboard UI)
Construir uma interface gráfica interativa (com suporte a preview de vídeos, player integrado, lista de cortes com pontuação de engajamento, status de renderização em tempo real e integração em 1-clique com Google Drive).

### R2. Integração Completa de Mídia, Análise e Armazenamento
Integrar os módulos de extração de legendas, pontuação de ganchos virais por IA, renderização de vídeo vertical (Shorts 9:16 com filtros de fundo desfocado) e upload para o Google Drive MCP via credenciais Service Account.

### R3. Suíte de Testes Automatizados e Verificação E2E
Passar 100% dos testes unitários e de integração (pytest), além de validação programática E2E do fluxo completo (URL ➔ Análise ➔ Corte Vertical ➔ Upload GDrive).

## Acceptance Criteria

### Painel Web e Funcionalidades
- [ ] O painel web exibe os cortes ranqueados por engajamento com player de preview, transcrição, hashtags e status de carregamento.
- [ ] Botão de download e botão de envio para o Google Drive funcionam sem erros.
- [ ] Suporte à conversão de vídeos horizontais (16:9) em verticais (9:16) para Shorts/Reels/TikTok.

### Testes e Qualidade
- [ ] Todos os testes unitários e E2E executam e passam com 100% de sucesso via `pytest`.
- [ ] O servidor do painel web inicia sem erros e responde nas APIs de análise e geração de cortes.

## Follow-up — 2026-07-26T14:09:39Z

# Teamwork Project: YouTube AI Clipper - Solução Definitiva Google Drive

Desenvolvimento da solução definitiva de integração do Google Drive (suportando OAuth2 de Usuário e Service Account) no projeto YouTube AI Clipper, garantindo uploads automáticos sem restrição de cota na pasta do usuário 1mYLUnTMhdflzmYhee804Nj52jBQuOI8H.

Working directory: /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper
Integrity mode: development

## Requirements

### R1. Solução Definitiva de Autenticação e Upload no Google Drive
Implementar o fluxo completo de autenticação OAuth2 (com suporte a token.json e variáveis de ambiente GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN) e manter fallback transparente para Service Account (service-account.json). Permitir o upload direto para pastas pessoais de usuários (1mYLUnTMhdflzmYhee804Nj52jBQuOI8H).

### R2. Integração no CLI e Painel Web (Dashboard UI)
Conectar a solução de upload no Google Drive aos comandos CLI (--gdrive, --cookies) e à API REST/interface visual do Web Dashboard (/api/gdrive-upload).

### R3. Suíte de Testes Automatizados e Validação E2E
Executar 100% dos testes unitários e de integração via pytest, assegurando zero regressões.

## Acceptance Criteria

### Google Drive Integration
- [ ] O módulo gdrive_uploader.py realiza uploads sem o erro 403 storageQuotaExceeded quando configurado com OAuth2.
- [ ] Fallback automático para service-account.json quando OAuth2 não estiver disponível.
- [ ] Suporte à especificação de folder_id via CLI e API.

### Qualidade e Testes
- [ ] Todos os 406+ testes unitários e de integração executam e passam com 100% de sucesso (pytest).
- [ ] O servidor do painel web responde corretamente ao envio para o Google Drive.

## Follow-up — 2026-07-26T22:38:30Z

# MISSÃO

Construir o núcleo local de uma "fábrica de cortes": um pipeline em Python que
transforma um vídeo longo em um Short vertical 9:16 com legendas, áudio tratado
e uma camada de contribuição editorial própria. Rodará em Linux com GPU NVIDIA
e 32 vCPU.

Nesta missão NÃO existe nuvem, NÃO existe publicação e NÃO existe LLM no
pipeline. É só a máquina local.

# A REGRA QUE GOVERNA TODAS AS OUTRAS

Vocês NÃO têm autoridade para declarar que algo funcionou.

O trabalho de vocês é produzir ARTEFATOS e EVIDÊNCIA em disco. Um revisor
externo (humano assistido por outro modelo) vai ler os artefatos, reexecutar
as medições e emitir o veredito. Ele não vai ler a narrativa de vocês para
decidir — vai ler os arquivos.

Consequências práticas, todas obrigatórias:

1. Nenhum relatório de resultado é escrito à mão. Relatório é SAÍDA DE SCRIPT,
   gerado a partir dos eventos e dos artefatos.
2. Toda afirmação precisa apontar para um arquivo que existe, com hash.
   Afirmação sem evidência é defeito, não estilo.
3. Tentativas que falharam ficam registradas. Apagar run fracassado é
   falsificação de histórico e reprova a fase inteira.
4. Se algo não funciona, escrevam que não funciona. O documento LIMITACOES.md
   é obrigatório e não pode estar vazio. Um relatório sem limitações é lido
   como relatório não confiável.
5. Não usem mock de FFmpeg, ffprobe ou Whisper no caminho crítico. Teste com
   mock passa e produção quebra.

# FASE T0 — FUNDAÇÃO DE EVIDÊNCIA (fazer ANTES de qualquer pipeline)

Objetivo: o mecanismo de log e verificação existir e ser confiável antes de
existir qualquer funcionalidade.

Entregar:

  src/cortes/log.py
    - Decorator @audited(stage=...) que mede duração, calcula sha256 dos
      artefatos declarados e escreve um evento. Logar é efeito colateral de
      executar, não escolha do programador.
    - Função run_cmd(...) — ÚNICO ponto autorizado de subprocesso no projeto.
      Captura cmd, cwd, exit_code, stdout, stderr, duração; escreve em
      commands.log e emite evento.
    - Escrita append-only em runs/<run_id>/events.jsonl, com seq estritamente
      crescente, sem buracos.

  Schema de evento (FIXO — não alterar sem registrar em LIMITACOES.md):
  {
    "schema_version": "1.0.0", "run_id": "...", "seq": 1,
    "ts": "ISO-8601 UTC", "agent": "<qual subagente>",
    "video_id": "...", "clip_id": "... | null",
    "stage": "env|ingest|transcribe|scenes|select|cut|subtitles|audio|transform|render|verify|report",
    "attempt": 1, "severity": "info|warn|error", "duration_ms": 0,
    "tool": "...", "cmd": "... | null", "exit_code": 0,
    "args_hash": "sha256:...",
    "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
    "trace": {"span_id": "...", "parent_span_id": "..."},
    "evidence": {"paths": [], "sha256": [], "bytes": []},
    "outcome": "ok|fail", "error": null, "claim": null
  }

  Regras do schema:
  - evento com outcome "ok" em estágio produtor DEVE ter evidence.paths não
    vazio, e cada path deve existir com o hash declared;
  - "cmd" é obrigatório quando "tool" é executável externo;
  - "claim" é o único campo de texto interpretativo e só vale acompanhado de
    evidence.paths.

  src/cortes/verify.py
    - Recebe APENAS o caminho do run. Não recebe nada de vocês.
    - Re-mede tudo do zero (ffprobe, pyloudnorm, hashes, contagens).
    - Emite verify_result.json: {check_id, passed, measured, expected,
      evidence_path} por item.

  src/cortes/report.py
    - Gera report.md exclusivamente a partir de events.jsonl e
      verify_result.json. Não pode conter frase que não derive desses dois.

  tests/test_contracts.py — falha o build se:
    (a) alguma função de estágio não tiver @audited (varredura por AST);
    (b) existir "subprocess." fora de run_cmd (varredura por AST);
    (c) events.jsonl de qualquer run não validar contra o schema;
    (d) houver buraco ou duplicata em seq.

  TESTE DE MUTAÇÃO (obrigatório nesta fase): criem uma fixture sintética,
  quebrem-na de propósito (dimensão errada, áudio amplificado, byte trocado)
  e PROVEM que verify.py acusa cada uma. Registrem a prova no run.
  Um verificador que passa verde com artefato quebrado é o pior defeito
  possível — pior que não ter verificador.

PARE AO FIM DE T0. Produza o pacote de revisão e aguarde veredito.

# FASE T1 — AMBIENTE

Verificar e registrar, com saída literal de comando em env_check.json:
  python3 --version                     → ≥ 3.11
  ffmpeg -version                       → precisa conter libass E libfreetype
  ffprobe -version                      → exit 0
  python3 -c "import soundfile"         → exit 0
  fc-list | grep -ci "inter|roboto|noto" → ≥ 1
  nvidia-smi --query-gpu=name,memory.total --format=csv → registrar GPU
  df -B1G --output=avail . | tail -1    → ≥ 20
  git --version                         → exit 0

Cada check vira {check_id, cmd, stdout, exit_code, pass}. Instalem o que faltar
e registrem a instalação como evento. Se um check falhar duas vezes seguidas,
PAREM e reportem — não improvisem contorno.

PARE AO FIM DE T1.

# FASE T2 — SHORT TÉCNICO PONTA A PONTA

De UM arquivo de vídeo local (o revisor indicará qual; até lá, usem uma fonte
de licença aberta e registrem a prova da licença), produzir
runs/<run_id>/artifacts/<clip_id>/short.mp4.

Pipeline: ingest → transcribe (faster-whisper/WhisperX, GPU, timestamps por
palavra) → scenes (PySceneDetect) → select (heurística determinística: maior
densidade de fala numa janela de 20–58 s alinhada a fronteira de cena) →
cut (-c copy) → subtitles (.ass via pysubs2) → audio (loudnorm 2 passos) →
render (crop/pad 9:16, 1080×1920, legenda queimada via libass) → report.

verify.py deve provar, medindo:
  - 1080×1920, fps constante
  - 20 s ≤ duração ≤ 58 s   (abaixo de 60 s, por decisão de projeto)
  - exatamente 1 faixa de áudio
  - LUFS integrado do arquivo FINAL entre −16 e −13
  - 0 ≤ selection.start_ms < selection.end_ms ≤ duração da fonte
  - todo evento de legenda mapeia palavras do transcript no mesmo intervalo
    (tolerância ±200 ms) e nenhum evento fora de [start, end]
  - sha256 de cada artefato bate com o declarado nos eventos

AVISO IMPORTANTE: este Short NÃO é o produto final. Um vídeo que é só recorte
+ legenda é, literalmente, o exemplo de conteúdo não monetizável na política do
YouTube. T2 prova que a mecânica funciona. O produto nasce em T3.

PARE AO FIM DE T3.

# FASE T3 — CAMADA DE TRANSFORMAÇÃO (portão de produto)

Adicionar ao pipeline pelo menos um elemento editorial ORIGINAL, verificável
por asserção:
  (a) faixa de narração/comentário autoral (TTS local ou arquivo de voz
      fornecido) com duração ≥ 8 s; e/ou
  (b) overlay analítico gerado (infográfico, destaque de dado, estrutura
      visual) presente no vídeo final.

Além disso: campo template_variant no clip_id/metadados, e regra de que o
variant precisa diferir dos últimos 5 renders — há política específica do
YouTube contra conteúdo produzido por template com pouca variação.

verify.py ganha os checks correspondentes, e o teste de mutação ganha o caso
"remover a narração ⇒ verify DEVE falhar".

PARE AO FIM DE T3.

# FASE T4 — CONTRATO DE LOG COMPLETO

Instrumentar todos os estágios com @audited, garantir que 100% dos subprocessos
passam por run_cmd, e deixar test_contracts.py verde no CI. Nenhum estágio pode
escapar da auditoria.

PARE AO FIM DE T4.

# FASE T5 — FIXTURES GOLDEN

Três fixtures de material com licença verificada e registrada:
  g1: fala contínua, ~2 min
  g2: multi-cena com cortes bruscos, ~3 min
  g3: caso adverso — música/ruído + silêncio, ~2 min

Cada fixture guarda a PROVA da licença junto (URL, autor, licença, data,
captura da página). Suíte roda o pipeline REAL nas três. Critério: 3/3 verdes
em duas execuções consecutivas.

PARE AO FIM DE T5.

# PACOTE DE REVISÃO (obrigatório ao fim de CADA fase)

Criar review/<fase>/ contendo:
  PACOTE.md          índice: commit, branch, fase, o que mudou, o que falta
  runs/<run_id>/     o run completo, INCLUINDO os que falharam
  diff.patch         git diff completo da branch vs base
  files_changed.txt  lista com hash antes/depois
  verify_result.json consolidado
  report.md          gerado por report.py
  DECISOES.md        cada decisão técnica + alternativa descartada + porquê
  LIMITACOES.md      o que não funciona, o que foi pulado, o que é frágil
  CRITICA_INTERNA.md o que o Reviewer/Critic/Auditor encontraram, incluindo
                     discordâncias não resolvidas entre vocês

# PROIBIÇÕES ABSOLUTAS

Vocês NÃO podem, em nenhuma circunstância:
  - publicar, agendar ou fazer upload de qualquer coisa no YouTube;
  - criar, ler ou alterar credenciais, chaves de API, OAuth, service accounts;
  - habilitar APIs no Google Cloud ou tocar em configuração de faturamento;
  - baixar vídeo de terceiro (yt-dlp só para material próprio ou CC BY
    verificado, com a prova registrada);
  - apagar ou editar qualquer coisa dentro de runs/ depois de criada;
  - fazer commit direto na main — trabalhem em branch;
  - declarar uma fase concluída (só o revisor externo declara);
  - avançar para a fase seguinte antes do veredito.

# DISCIPLINA DE ARQUIVOS (regra dura)

Só existem três lugares onde vocês podem escrever:

  src/ e tests/    → código
  runs/<run_id>/   → execução e evidência (imutável após criada)
  review/<fase>/   → o pacote de revisão

NADA solto na raiz do repositório. Nenhum relatório intermediário, nenhum
rascunho, nenhum "NOTES.md", "SUMMARY.md", "PROGRESS.md" ou similar fora dessas
pastas. Se um subagente precisa de espaço de rascunho, use
runs/<run_id>/scratch/ e registre.

Motivo: há relato público de este modo despejar dezenas de arquivos .md no
diretório de trabalho. Isso torna a revisão impossível e será tratado como
defeito de processo.

# COMO TRABALHAR

- Cada subagente (Worker, Reviewer, Critic, Auditor) registra seu nome no campo
  "agent" de todo evento que emite. Preciso saber quem fez o quê.
- O Reviewer, o Critic e o Auditor do time são bem-vindos, mas o relatório
  deles é INSUMO, não conclusão. Eles não fecham fase. Podem e devem escrever
  o que encontraram em review/<fase>/CRITICA_INTERNA.md — inclusive discordância
  entre vocês, que é informação útil para mim.
- Emitam um evento por estágio mesmo quando ele demora. Silêncio longo sem
  evento é indistinguível de loop travado, e eu trato como falha.
- Um estágio escreve num diretório de saída próprio. Nada sobrescreve nada.
- Nomes de arquivo determinísticos (clip_id derivado de hash), para que duas
  execuções iguais produzam os mesmos caminhos.
- Decisão técnica relevante vai para DECISOES.md no momento em que é tomada,
  não no fim. A memória canônica do projeto é o repositório, não o contexto
  de vocês.
- Quando estiverem em dúvida entre duas abordagens, implementem a mais simples
  e registrem a outra em DECISOES.md como alternativa considerada.
- Se algo bloquear, PAREM e reportem o bloqueio com evidência. Não contornem
  silenciosamente.

Comecem por T0. Não pulem T0.

## Follow-up — 2026-07-27T03:51:29Z

Implement Phase T1 (Baseline anti-regression & double-cut fix) for the YouTube Clipper project to eliminate silent MP4 file corruption and establish programmatic media output verification.

Working directory: /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper
Integrity mode: development

## Requirements

### R1. Double-Cut Correction in Pipeline
Fix segment offset handling in `src/youtube_clipper/pipeline.py`. When downloading YouTube segments, `download_segment` already extracts the cut slice starting at t=0. The pipeline must normalize offsets (`cut_start = 0.0`, `cut_end = end_sec - start_sec`) for YouTube inputs before calling `cut_media`, while retaining absolute timestamps for direct local media files.

### R2. Media Validation Guardrails in Processor
Enhance `cut_media` in `src/youtube_clipper/processor.py` to validate that generated output MP4 files are valid. Verify that file size is strictly greater than 1024 bytes and that `ffprobe` returns a valid positive duration. Raise `ProcessingError` if media output is corrupted, empty, or unreadable.

### R3. Media Output Baseline & Regression Test Suite
Create `tests/test_regression_media.py` using synthetic test videos generated via `ffmpeg -f lavfi -i testsrc` to verify duration, resolution, and minimum file size of rendered clips. Include unit tests simulating double-cut scenarios (e.g. 30s input file with start=60) expecting `ProcessingError`. Ensure 100% of existing pytest test cases continue to pass.

## Acceptance Criteria

### Media Pipeline Guardrails & Correctness
- [ ] `cut_media` validates output MP4 files with `st_size > 1024` and valid `ffprobe` duration, throwing `ProcessingError` on failure.
- [ ] Pipeline correctly normalizes cut start/end offsets for YouTube downloaded segments vs local files without secondary offset miscalculations.
- [ ] Double-cut scenarios return descriptive errors (`ProcessingError`) rather than silent exit 0 corrupted 262-byte MP4s.

### Testing & Quality Bar
- [ ] `tests/test_regression_media.py` tests synthetic MP4 generation and validates output clip duration, resolution, and size.
- [ ] Full `pytest` execution passes with 100% success rate across all unit, integration, and regression test suites.
