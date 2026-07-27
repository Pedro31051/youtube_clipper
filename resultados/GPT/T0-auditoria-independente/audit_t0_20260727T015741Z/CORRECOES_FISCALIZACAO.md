# Resposta ponto a ponto ao Parecer de Fiscalização ChatGPT

Este run existe porque o parecer de fiscalização reprovou o run
`audit_t0_20260726T234421Z`. Aquele pacote **permanece intacto** no repositório
como tentativa fracassada, conforme a condição 1 do parecer. Nada nele foi
editado, movido ou apagado.

Cada achado fiscalizatório é respondido abaixo com o que foi feito e onde a
prova está.

---

## FISC-GPT-001 — H05 foi refutada sem testar a hipótese

**Corrigido.** A hipótese agora é reproduzida de ponta a ponta em
`scratch/h05.py`:

- fonte sintética de 30 s criada com `ffmpeg lavfi` (nenhum download de
  terceiros, nenhuma credencial lida);
- `YouTubeDownloader` substituído por um dublê que devolve esse arquivo já
  recortado começando em `t=0`, exatamente como o `download_ranges` do yt-dlp
  entrega;
- `run_pipeline()` real chamado com o intervalo absoluto 60–90 s;
- `subprocess.run` espionado para capturar o comando FFmpeg literal;
- saída medida por `ffprobe`;
- **cenário de controle** com o intervalo 0–10 s, para separar defeito do
  pipeline de defeito do próprio ensaio.

Resultado: `-ss 60.0` é reaplicado a um arquivo de 30 s, o pipeline retorna com
sucesso, e o MP4 produzido tem 262 bytes, zero streams e duração 0,000 s. O
controle 0–10 s produz um arquivo válido de 10,024 s.

**H05 passa de REFUTADA para CONFIRMADA**, com a classificação exigida pelo
plano: `ARQUIVO_INVALIDO_ACEITO_COMO_SUCESSO`.

Prova: `evidencias/10-corte-duplo.att3.txt` (comando `#0014`).

---

## FISC-GPT-002 — A auditoria modificou a área oficial proibida

**Corrigido.** Nenhum verificador foi executado contra `review/T0/` nesta
auditoria. Toda execução de `cortes.verify` ocorre sobre cópia em `/tmp`, com
diretório de trabalho também em `/tmp`.

Além disso, `scratch/h04.py` mede por hash a árvore inteira de `review/T0`
antes e depois da execução e registra `git status` das áreas `review/` e
`runs/`.

Resultado medido: `H04_AREA_OFICIAL_PRESERVADA=True`, `git status` limpo.
A suíte completa também foi checada da mesma forma:
`REVIEW_T0_INTACTO_APOS_PYTEST=SIM`.

Provas: `evidencias/09-verificador-readonly.txt` (`#0010`),
`evidencias/03-pytest-completo.txt` (`#0004`).

---

## FISC-GPT-003 — O manifesto referenciava arquivo inexistente no Git

**Corrigido.** O manifesto deste run é gerado **a partir do índice do Git**, não
do sistema de arquivos: somente arquivos efetivamente versionados entram nele.
Todo o run foi executado com `PYTHONDONTWRITEBYTECODE=1` e não há `__pycache__`
no pacote.

A validação foi feita em **checkout limpo**, e não no diretório de trabalho —
ver `evidencias/15-manifesto-checkout-limpo.txt` e a seção correspondente de
`PACOTE.md`.

---

## FISC-GPT-004 — Tentativas fracassadas foram sobrescritas

**Corrigido no runner.** `scratch/runner.py` abre todo arquivo de evidência com
o modo `"x"`: se o caminho já existe, a gravação falha em vez de sobrescrever.
Cada nova tentativa sobre o mesmo slot recebe arquivo próprio
(`<slot>.att2.txt`, `<slot>.att3.txt`, …), e `stdout` e `stderr` são gravados
**literalmente e em arquivos separados**, sem cabeçalho, mescla ou edição.

O mecanismo foi exercitado de fato neste run. A tentativa `#0015`
(`11-dashboard-superficie`, att1) terminou com **exit 1** e está preservada com
119 bytes de stdout e 1125 bytes de stderr, ao lado das tentativas seguintes
bem-sucedidas. O slot `10-corte-duplo` guarda três tentativas.

---

## FISC-GPT-005 — A sequência de comandos não era única nem contínua

**Corrigido no runner.** O contador vive em `scratch/.seq_state`, protegido por
`fcntl.flock`, e portanto sobrevive à troca de processo. Cada comando recebe
ainda um identificador único `cmd_uid` no formato `<RUN_ID>#NNNN`, além de
`slot` e `attempt`.

`COMANDOS.jsonl` deste run vai de 1 a 23, sem lacunas e sem repetições. Os
`reproduction_command_ids` de `VEREDITO.json` usam `cmd_uid`, que identifica um
único comando de forma inequívoca.

---

## FISC-GPT-006 — H06 usava afirmações prontas como se fossem evidência

**Corrigido.** `scratch/h06.py` não imprime nenhuma conclusão pré-escrita. Ele
mede:

- endereço de bind, lido do AST (`server_address = ('', port)`) e confirmado
  pela semântica de socket;
- autenticação, por varredura de literais e de métodos do handler — zero
  ocorrências;
- allowlist de `/api/download/`, lida do AST;
- mutação de `os.environ['YOUTUBE_COOKIES_FILE']`, localizada no AST em duas
  linhas;
- comportamento vivo: servidor real em `127.0.0.1` numa porta efêmera, com
  requisições anônimas, iscas em disco, `file_path` absoluto arbitrário
  entregue a um dublê do uploader (nenhum envio real ao Drive) e oito clientes
  simultâneos disputando o estado global.

Prova: `evidencias/11-dashboard-superficie.att3.txt` (`#0018`).

---

## FISC-GPT-007 — O relatório omitia hipóteses confirmadas dos findings

**Corrigido.** Toda hipótese confirmada virou finding formal. São **onze**
findings (`AUD-T0-001` a `AUD-T0-011`), contra três do run anterior, incluindo
portabilidade, dashboard, CI, disciplina de branch e dois defeitos estruturais
descobertos nesta rodada.

---

## FISC-GPT-008 — O teste de portabilidade não isolou a máquina original

**Corrigido com duas provas independentes.**

1. **Prova de controle**: a cópia relocada teve os **próprios artefatos
   destruídos** e o verificador continuou aprovando (`overall_passed=true`).
   Isso demonstra diretamente que ele nunca leu a cópia.
2. **Máquina limpa**: clone contendo apenas arquivos versionados, executado em
   contêiner sem acesso a `/home`. Resultado: `overall_passed=false`, 11 de 14
   checks.

Descobriu-se ainda que os cinco artefatos declarados não apontam para o pacote
oficial, e sim para `runs/run_t0_golden/`, que **não é versionado**.

Prova: `evidencias/08-portabilidade.txt` (`#0009`).

---

## FISC-GPT-009 — O veredito não respeitava os próprios portões do plano

**Corrigido.** A seção 7 de `RELATORIO.md` percorre literalmente cada portão de
bloqueio da seção 7 do plano e aponta a evidência que o aciona. Sete portões
foram acionados. O veredito é `NAO_APTA_PARA_T1`.

---

## Condições adicionais do parecer

| Condição | Situação |
|---|---|
| Preservar o run fracassado | Cumprida: `audit_t0_20260726T234421Z` intacto |
| Criar novo RUN_ID | Cumprida: `audit_t0_20260727T015741Z` |
| Sequência global contínua | Cumprida: 1..23 sem lacunas |
| Evidência append-only | Cumprida: modo `"x"`, nunca sobrescreve |
| Arquivo separado por tentativa | Cumprida: sufixo `.attN` |
| stdout e stderr preservados | Cumprida: arquivos separados e literais |
| IDs de comando inequívocos | Cumprida: `cmd_uid` |
| Manifesto só com arquivos versionados | Cumprida: gerado do índice do Git |
| Validar manifesto em checkout limpo | Cumprida: `evidencias/15-manifesto-checkout-limpo.txt` |
| Portabilidade sem os caminhos originais | Cumprida: contêiner sem `/home` + prova de controle |
| H05 por pipeline completo e ffprobe | Cumprida |
| H06 por inspeção real | Cumprida |
| Não executar verificador contra `review/T0/` | Cumprida e comprovada por hash |
| Finding formal para toda hipótese confirmada | Cumprida: 11 findings |
| Aplicar literalmente os portões do plano | Cumprida: seção 7 do relatório |
