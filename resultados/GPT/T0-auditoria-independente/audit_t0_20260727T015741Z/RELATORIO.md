# Relatório de Auditoria Independente — Fase T0 (run corrigido)

- **Repositório**: `Pedro31051/youtube_clipper`
- **Baseline auditada**: `fbe8cc5462537dbcaa44ddf6c9182ac218b22c25` (ponta de `origin/main`)
- **HEAD da branch no início do run**: `4ffe6f4f5220654d7e315e5a5c893a749a43f721`
- **Run ID**: `audit_t0_20260727T015741Z`
- **Branch**: `agent/auditoria-independente-t0`
- **Motivo deste run**: reprovação do run `audit_t0_20260726T234421Z` pelo
  Parecer de Fiscalização ChatGPT. O run reprovado permanece intacto no
  repositório como tentativa fracassada.

---

## 1. Escopo e baseline

Esta auditoria determina, com provas reproduzíveis versionadas, se a
implementação da Fase T0 cumpre os contratos de auditabilidade, exclusividade
de `run_cmd()`, integridade e portabilidade de evidências, verificação sem
efeitos colaterais, rigor dos testes de mutação, disciplina de branch e
separação entre afirmação narrativa e resultado medido.

O código auditado é idêntico à baseline do plano: `git diff` entre `fbe8cc5` e
o HEAD da branch, restrito a `src/`, `tests/` e `review/`, é vazio
(`evidencias/00-baseline-git.txt`). Os commits desta branch acrescentam apenas
documentação sob `resultados/GPT/`.

Nenhuma correção de código foi implementada. Nenhum arquivo fora de
`resultados/GPT/T0-auditoria-independente/audit_t0_20260727T015741Z/` foi
criado, alterado ou removido.

## 2. Ambiente

Ubuntu 24.04.4 LTS, kernel 6.17.0-1021-gcp, x86_64, usuário
`pedrofelipealvesrocha`. Python 3.12.3 (sistema e venv), Git 2.43.0, FFmpeg e
ffprobe 6.1.1, pytest 9.1.1, Docker 29.6.2. Detalhamento completo, com
dependências declaradas e hashes de todos os arquivos relevantes, em
`INVENTARIO.txt` e `evidencias/01-ambiente.txt`.

## 3. Metodologia

Cada conclusão deste relatório aponta para um arquivo de evidência, um comando
literal e um código de saída. Nenhuma frase de relatório anterior foi aceita
como prova.

O protocolo de captura foi refeito para atender ao parecer de fiscalização:

- **Sequência global contínua.** `scratch/runner.py` mantém o contador em
  `scratch/.seq_state` sob `fcntl.flock`, de modo que processos distintos
  continuam a mesma sequência. `COMANDOS.jsonl` vai de 1 a 23, sem lacunas nem
  repetições, e cada comando tem `cmd_uid` único no formato `<RUN_ID>#NNNN`.
- **Evidência append-only.** Todo arquivo de evidência é aberto em modo `"x"`.
  Sobrescrever é impossível por construção; cada nova tentativa sobre o mesmo
  slot recebe arquivo próprio com sufixo `.attN`.
- **stdout e stderr literais e separados.** O arquivo nomeado no plano contém
  exclusivamente o stdout literal; o `.stderr.txt` irmão contém o stderr
  literal. Nenhum cabeçalho é inserido, nada é mesclado, nada é editado. Os
  metadados vivem apenas em `COMANDOS.jsonl`.
- **Tentativas fracassadas preservadas.** O comando `#0015` terminou com exit 1
  e está preservado com seu stderr, ao lado das tentativas posteriores.

A área oficial `review/T0/` foi tratada como somente-leitura. Nenhum
verificador foi executado contra ela: todas as execuções de `cortes.verify`
ocorreram sobre cópias em `/tmp`, com diretório de trabalho também em `/tmp`. A
integridade da área foi medida por hash antes e depois
(`H04_AREA_OFICIAL_PRESERVADA=True`).

## 4. Resultados da suíte declarada

| Execução | Coletados | Aprovados | Falhas | Erros | Duração | Exit | Evidência |
|---|---|---|---|---|---|---|---|
| `pytest tests/` | 462 | 462 | 0 | 0 | 109,98 s | 0 | `evidencias/03-pytest-completo.txt` |
| `pytest tests/test_contracts.py` | 7 | 7 | 0 | 0 | 0,07 s | 0 | `evidencias/04-pytest-contracts.txt` |
| `pytest tests/test_mutation.py` | 17 | 17 | 0 | 0 | 79,00 s | 0 | `evidencias/05-pytest-mutation.txt` |

O JUnit XML está em `evidencias/pytest.xml`.

O número `462 passed` é confirmado de forma independente. Ele comprova que a
suíte existente passa — e nada além disso. Os testes de FFmpeg, ffprobe,
Whisper, YouTube e Google Drive relevantes rodam sob mock; não são prova de
execução real desses serviços. A documentação do projeto
(`PLANO_MELHORIAS.md:4`) declara 406 testes, contra 462 coletados: divergência
registrada como `AUD-T0-011`.

## 5. Tabela de hipóteses

| ID | Hipótese | Estado | Evidência |
|---|---|---|---|
| H01 | Scanner AST não cobre todo o código produtivo | **CONFIRMADA** | `evidencias/06-subprocess-scan.txt` |
| H02 | Módulos de estágio ausentes são ignorados silenciosamente | **CONFIRMADA** | `evidencias/07-stage-modules.txt` |
| H03 | Evidências do golden run não são portáveis | **CONFIRMADA** | `evidencias/08-portabilidade.txt` |
| H04 | O verificador modifica estado ou grava no run errado | **CONFIRMADA** | `evidencias/09-verificador-readonly.txt` |
| H05 | O corte de URL do YouTube aplica o offset duas vezes | **CONFIRMADA** | `evidencias/10-corte-duplo.att3.txt` |
| H06 | O dashboard possui superfície insegura quando exposto | **CONFIRMADA** | `evidencias/11-dashboard-superficie.att3.txt` |
| H07 | Não existe CI independente comprovando a suíte | **CONFIRMADA** | `evidencias/12-ci-e-branches.att2.txt` |
| H08 | A disciplina de branch da própria T0 foi descumprida | **CONFIRMADA** | `evidencias/12-ci-e-branches.att2.txt` |

O run anterior classificou H05 como REFUTADA. Esta auditoria **reverte** essa
classificação: a hipótese é CONFIRMADA por execução do pipeline completo.

## 6. Achados

### AUD-T0-001
- **Título**: O scanner AST de exclusividade de `run_cmd()` varre apenas `src/cortes/`
- **Gravidade**: ALTA
- **Estado**: CONFIRMADO
- **Contrato afetado**: exclusividade de `run_cmd()` para comandos externos
- **Evidência**: `evidencias/06-subprocess-scan.txt` (`#0007`)
- **Como reproduzir**: `.venv/bin/python scratch/h01.py`
- **Resultado observado**: o teste `test_ast_prohibit_subprocess_outside_run_cmd`
  varre 4 arquivos (`src/cortes/`) e deixa 12 arquivos fora do escopo.
  Reaplicando o **mesmo scanner do teste** a todo `src/`, aparecem 13
  ocorrências proibidas em `analyzer.py`, `processor.py`, `video_formatter.py` e
  `web_dashboard.py`, incluindo três `subprocess.run` produtivos.
- **Resultado esperado**: toda invocação de subprocesso do projeto passa
  unicamente por `src/cortes/log.py:run_cmd()`.
- **Impacto**: o contrato de auditabilidade não vale para o pipeline que de fato
  produz os vídeos. Chamadas ao FFmpeg em produção não são registradas em
  `commands.log` nem em `events.jsonl`.
- **Contraprova considerada**: as 4 ocorrências em `src/cortes/log.py` são
  legítimas — é o ponto único autorizado.
- **Recomendação**: estender a raiz do scanner a `src/` inteiro e migrar as
  chamadas de `youtube_clipper` para `run_cmd()`.

### AUD-T0-002
- **Título**: O contrato de decorador `@audited` passa por vacuidade
- **Gravidade**: ALTA
- **Estado**: CONFIRMADO
- **Contrato afetado**: integridade da malha de estágios auditados
- **Evidência**: `evidencias/07-stage-modules.txt` (`#0008`)
- **Como reproduzir**: `.venv/bin/python scratch/h02.py`
- **Resultado observado**: 0 dos 9 módulos de `STAGE_MODULES` existem.
  `tests/test_contracts.py:62` executa `if not stage_file.exists(): continue`.
  Teste adversarial em cópia temporária: sem módulo → **PASSOU**; módulo
  presente sem `@audited` → **FALHOU**; módulo presente com `@audited` →
  **PASSOU**. O verde de hoje decorre exclusivamente da ausência.
- **Resultado esperado**: exigir a presença dos módulos declarados ou reportar
  pendência explícita.
- **Impacto**: falsa sensação de cobertura sobre nove estágios inexistentes.
- **Contraprova considerada**: o cenário B prova que a lógica do teste funciona
  quando há o que verificar; o defeito está no escape, não no scanner.
- **Recomendação**: falhar, ou marcar `xfail` explícito, quando um módulo de
  `STAGE_MODULES` não existir.

### AUD-T0-003
- **Título**: O golden run não é verificável fora da máquina original, e os artefatos que ele valida não estão no pacote nem versionados
- **Gravidade**: CRÍTICA
- **Estado**: CONFIRMADO
- **Contrato afetado**: integridade e portabilidade das evidências
- **Evidência**: `evidencias/08-portabilidade.txt` (`#0009`)
- **Como reproduzir**: `.venv/bin/python scratch/h03.py`
- **Resultado observado**: 54 referências absolutas e nenhuma relativa nos
  quatro arquivos do run. Os 5 artefatos declarados em `events.jsonl` apontam
  para `<repo>/runs/run_t0_golden/artifacts/…` — fora do pacote oficial e
  **não versionado** (`git ls-files runs/` retorna 0 arquivos). Duas provas
  independentes:
  1. **Controle**: destruindo os artefatos **da própria cópia relocada**, o
     verificador continua com `overall_passed=true` (10/10). Ele nunca leu a
     cópia.
  2. **Máquina limpa**: clone só com arquivos versionados, executado em
     contêiner sem acesso a `/home` → `overall_passed=false`, 11/14, com
     `artifact_exists`, `artifact_sha256` e `artifact_bytes` falhando.
- **Resultado esperado**: caminhos relativos ao run e artefatos contidos no
  pacote entregue.
- **Impacto**: o `verify_result.json` de 14/14 versionado em `review/T0/` não é
  reproduzível por ninguém que não esteja nesta máquina, neste caminho, com um
  diretório `runs/` que o repositório não distribui.
- **Contraprova considerada**: a cópia íntegra passa 14/14 nesta máquina — é
  exatamente o resultado que o run anterior tomou como prova de portabilidade.
  A prova de controle mostra que esse verde é insensível ao conteúdo da cópia.
- **Recomendação**: gravar caminhos relativos ao diretório do run e versionar
  os artefatos verificados junto com o pacote.

### AUD-T0-004
- **Título**: `cortes.verify` não é read-only e cria um run colateral no diretório de trabalho
- **Gravidade**: ALTA
- **Estado**: CONFIRMADO
- **Contrato afetado**: verificação independente e sem efeitos colaterais
- **Evidência**: `evidencias/09-verificador-readonly.txt` (`#0010`, `#0011`)
- **Como reproduzir**: `.venv/bin/python scratch/h04.py`
- **Resultado observado**: sobre cópia isolada, `verify_result.json` é
  **modificado** dentro do run verificado (hash muda). Fora do run, o
  verificador cria `runs/run_<timestamp>/` no diretório de trabalho corrente,
  com `commands.log` e 2 eventos, porque `cortes.log.get_run_dir()` resolve
  `runs/<run_id>` relativo ao CWD. `H04_VERIFICADOR_READONLY=False`.
- **Resultado esperado**: conteúdo verificado byte a byte idêntico e nenhuma
  gravação inesperada.
- **Impacto**: verificar altera o objeto verificado; o resultado depende do
  diretório de onde se executa.
- **Contraprova considerada**: a alteração é determinística e o `git status`
  da área oficial permanece limpo nesta auditoria — mas isso porque a área
  oficial não foi tocada, e não porque o verificador seja inócuo.
- **Recomendação**: aceitar um diretório de saída separado e nunca escrever
  dentro do run verificado.

### AUD-T0-005
- **Título**: O pipeline reaplica o offset absoluto e aceita um MP4 inválido como sucesso
- **Gravidade**: CRÍTICA
- **Estado**: CONFIRMADO
- **Contrato afetado**: correção funcional do corte e detecção de falha
- **Evidência**: `evidencias/10-corte-duplo.att3.txt` (`#0014`)
- **Como reproduzir**: `.venv/bin/python scratch/h05.py`
- **Resultado observado**: `run_pipeline()` chama
  `download_segment(start=60, end=90)`, que devolve um arquivo já recortado
  começando em `t=0`, e em seguida chama `cut_media(start=60, end=90)` sobre
  esse mesmo arquivo. O comando construído é
  `ffmpeg -y -ss 60.0 -i <arquivo de 30 s> -t 30.0 -c:v libx264 -c:a aac …`.
  FFmpeg retorna 0, o pipeline **não levanta exceção** e devolve o caminho de
  saída como sucesso. O arquivo produzido tem 262 bytes, **zero streams** e
  duração **0,000 s**.
- **Resultado esperado**: erro explícito, ou uso de offset relativo ao segmento
  já recortado.
- **Impacto**: qualquer corte de URL do YouTube com `start` maior ou igual à
  duração do segmento entrega ao usuário um arquivo vazio anunciado como
  sucesso. `processor.py` valida apenas `outp.exists()`, não o conteúdo.
- **Contraprova considerada**: o cenário de controle, com intervalo 0–10 s no
  mesmo arranjo, produz um MP4 válido de 10,024 s
  (`H05_CONTROLE_OK=True`). O defeito é do pipeline, não do ensaio.
- **Recomendação**: usar offset relativo após `download_segment()` e validar o
  artefato por `ffprobe` antes de declarar sucesso.

### AUD-T0-006
- **Título**: O dashboard expõe leitura de arquivos, upload de caminho arbitrário e estado global mutável, sem qualquer autenticação
- **Gravidade**: ALTA
- **Estado**: CONFIRMADO
- **Contrato afetado**: segurança da superfície exposta
- **Evidência**: `evidencias/11-dashboard-superficie.att3.txt` (`#0018`)
- **Como reproduzir**: `.venv/bin/python scratch/h06.py`
- **Resultado observado**, tudo medido em servidor vivo preso a `127.0.0.1`
  numa porta efêmera:
  - `web_dashboard.py:882` — `server_address = ('', port)`, isto é, todas as
    interfaces, porta padrão 8080;
  - zero literais de autenticação no módulo; nenhum método de autorização no
    handler; nenhuma resposta 401/403 em nenhum caso testado;
  - `GET /api/download/<nome>` devolveu **HTTP 200 com o conteúdo** de iscas
    plantadas no diretório de trabalho e em `/tmp`, sem credencial — a
    allowlist inclui `Path.cwd()` e `tempfile.gettempdir()`;
  - `POST /api/gdrive-upload {"file_path": "/etc/passwd"}` entregou o caminho
    absoluto ao uploader sem validação (envio real bloqueado por dublê);
  - `web_dashboard.py:751` e `:791` gravam
    `os.environ['YOUTUBE_COOKIES_FILE']` a partir do corpo da requisição;
  - com 8 clientes simultâneos, **7 de 8** rodaram sob o arquivo de cookies de
    outro cliente.
- **Resultado esperado**: autenticação obrigatória, bind em loopback por
  padrão, allowlist restrita e estado por requisição.
- **Impacto**: exposto na rede, o dashboard permite ler arquivos do diretório
  de trabalho e de `/tmp`, enviar arquivos arbitrários do host ao Drive e
  contaminar as credenciais de outros usuários.
- **Contraprova considerada**: a travessia de caminho **é** bloqueada
  (`GET /api/download/../../../etc/passwd` → HTTP 400). A exposição não decorre
  de travessia, e sim da própria allowlist e da ausência de autenticação.
- **Recomendação**: bind em `127.0.0.1` por padrão, autenticação obrigatória,
  allowlist restrita a um diretório de saída dedicado e estado de cookies por
  requisição.

### AUD-T0-007
- **Título**: Não existe integração contínua comprovando a suíte
- **Gravidade**: MÉDIA
- **Estado**: CONFIRMADO
- **Contrato afetado**: reprodutibilidade independente
- **Evidência**: `evidencias/12-ci-e-branches.att2.txt` (`#0019`)
- **Como reproduzir**: consulta autenticada à API do GitHub, registrada na
  evidência.
- **Resultado observado**: `.github/` não existe; a API retorna
  `total_count = 0` para workflows e `total = 0` para check-runs do commit
  baseline; o status do commit é `pending` com 0 contextos.
- **Resultado esperado**: pipeline de CI executando lint, type check e pytest.
- **Impacto**: todo resultado verde é auto-declarado pelo executor.
- **Contraprova considerada**: relatórios commitados não são execução de CI.
- **Recomendação**: adicionar workflow que rode a suíte em runner limpo.

### AUD-T0-008
- **Título**: Os commits de implementação da T0 foram feitos diretamente em `main`
- **Gravidade**: MÉDIA
- **Estado**: CONFIRMADO
- **Contrato afetado**: disciplina de branch, commit e evidência
- **Evidência**: `evidencias/12-ci-e-branches.att2.txt` (`#0019`)
- **Resultado observado**: `f4f13a3` (implementação T0) e `fbe8cc5`
  (remediação T0) estão em `origin/main`. `agents.md:31` proíbe expressamente
  "commit na main". Não há PR de implementação; o único PR aberto é o da
  fiscalização.
- **Resultado esperado**: implementação em branch própria, revisada por PR.
- **Impacto**: a baseline auditada nunca passou por revisão antes de virar
  `main`.
- **Contraprova considerada**: nenhuma. Relata-se apenas o histórico
  demonstrável, sem atribuir intenção.
- **Recomendação**: proteger `main` e exigir PR.

### AUD-T0-009
- **Título**: A ausência de artefatos reduz silenciosamente o número de checks e é aprovada como sucesso
- **Gravidade**: ALTA
- **Estado**: CONFIRMADO
- **Contrato afetado**: capacidade de a verificação rejeitar corrupção
- **Evidência**: `evidencias/14-mutacao-cobertura.att3.txt` (`#0022`),
  `evidencias/08-portabilidade.txt` (`#0009`)
- **Como reproduzir**: `.venv/bin/python scratch/h07_mutacao.py`
- **Resultado observado**: três corrupções relevantes foram aplicadas a cópias
  do run oficial. MP4 truncado → rejeitado (exit 1, 4 checks falham). SHA
  declarado alterado → rejeitado (exit 1). **Diretório `artifacts/` removido →
  `overall_passed=true`, exit 0, e `total_checks` cai de 14 para 10.** Os
  checks de mídia não falham: simplesmente deixam de existir, porque
  `verify.py:386` os deriva de `rglob("*.mp4")`.
- **Resultado esperado**: a ausência de um artefato exigido deve reprovar, e o
  conjunto de checks deve ser fixo.
- **Impacto**: um run esvaziado passa na verificação. Isso também explica por
  que a prova de controle de portabilidade continuou verde.
- **Contraprova considerada**: `artifact_exists` existe, mas valida os
  caminhos absolutos declarados, não o conteúdo do pacote — e por isso lê os
  arquivos da máquina original.
- **Recomendação**: derivar os checks de mídia dos artefatos **declarados**, não
  do que houver em disco, e reprovar quando faltarem.

### AUD-T0-010
- **Título**: `check_id` duplicado torna o resultado ambíguo com múltiplos MP4s
- **Gravidade**: BAIXA
- **Estado**: CONFIRMADO
- **Contrato afetado**: rastreabilidade do resultado de verificação
- **Evidência**: `evidencias/14-mutacao-cobertura.att3.txt` (`#0022`)
- **Resultado observado**: com dois MP4s no run, `video_resolution`,
  `audio_stream_count`, `video_duration_range` e `audio_lufs_loudness` aparecem
  duas vezes cada, com o mesmo `check_id`. Só o `evidence_path` distingue as
  ocorrências — e `video_resolution` grava caminho **relativo** enquanto os
  demais gravam **absoluto**.
- **Resultado esperado**: identificador único por artefato verificado e formato
  de caminho consistente.
- **Impacto**: baixo hoje, porque o `evidence_path` ainda permite distinguir;
  alto se algum consumidor indexar por `check_id`.
- **Recomendação**: compor `check_id` com o identificador do artefato e
  uniformizar o formato do caminho.

### AUD-T0-011
- **Título**: A contagem de testes documentada diverge da coletada
- **Gravidade**: BAIXA
- **Estado**: CONFIRMADO
- **Contrato afetado**: correspondência entre documentação e execução
- **Evidência**: `evidencias/12-ci-e-branches.att2.txt` (`#0019`),
  `evidencias/03-pytest-completo.txt` (`#0004`)
- **Resultado observado**: `PLANO_MELHORIAS.md:4` documenta 406 testes; a
  coleta real é 462.
- **Impacto**: baixo, mas o plano exige registrar divergência entre suíte
  documentada e executada.
- **Recomendação**: atualizar a documentação ou justificar a diferença.

## 7. Aplicação literal dos portões do plano

A seção 7 do plano manda bloquear T1 se ocorrer **qualquer** um dos casos
abaixo. Sete ocorreram.

| Portão do plano | Acionado | Evidência |
|---|---|---|
| Subprocesso produtivo fora do ponto autorizado | **SIM** | `06-subprocess-scan.txt` — 13 ocorrências |
| Verificador alterar o run ou depender de estado externo | **SIM** | `09-verificador-readonly.txt` — `verify_result.json` alterado, run colateral no CWD |
| Golden run não puder ser verificado após relocação | **SIM** | `08-portabilidade.txt` — 11/14 em máquina limpa |
| Caminhos absolutos tornarem a prova dependente da máquina | **SIM** | `08-portabilidade.txt` — 54 referências absolutas, 0 relativas |
| Teste contratual passar por ausência silenciosa dos módulos | **SIM** | `07-stage-modules.txt` — cenário A passa, B falha |
| Teste de mutação não rejeitar corrupção relevante | **SIM** | `14-mutacao-cobertura.att3.txt` — remoção de artefatos aprovada |
| Arquivo de mídia inválido ser aceito como sucesso | **SIM** | `10-corte-duplo.att3.txt` — 262 B, 0 streams, 0,000 s |
| Provas não possuírem hashes | não | `MANIFESTO_SHA256.txt` |
| Resultados não puderem ser reproduzidos | não | 462/462 reproduzidos nesta auditoria |
| Suíte documentada divergir materialmente da executada | parcial | `AUD-T0-011` — 406 documentados x 462 coletados |

Os requisitos de "apta para revisão humana" também não são satisfeitos: há
achados críticos e altos confirmados, e as evidências do pacote T0 **não** são
reproduzíveis a partir da baseline em outra máquina.

## 8. Contraprovas consideradas

Registram-se os pontos em que a implementação **resistiu** ao ataque:

1. Os 14 checks de `verify.py` têm, cada um, ao menos um teste de mutação
   correspondente. Nenhum check ficou descoberto.
2. A asserção de `test_mutation_1_byte_corruption` sustenta o teste: invertê-la
   faz falhar, e remover a corrupção do artefato mantendo a asserção também faz
   falhar. O teste mede o que promete.
3. Corrupção de bytes do MP4 e adulteração do SHA declarado **são** rejeitadas
   pelo verificador.
4. A travessia de caminho no dashboard é bloqueada com HTTP 400.
5. O pipeline funciona corretamente quando o intervalo é compatível com o
   segmento (controle 0–10 s → 10,024 s).
6. `review/T0/` permaneceu íntegra durante toda esta auditoria, inclusive após
   a suíte completa.
7. A branch contém exclusivamente pacotes de auditoria sob `resultados/GPT/`.

Uma ressalva metodológica sobre o item 1: os testes de mutação operam sobre um
run **sintético** criado em `tmp_path`, nunca sobre o pacote oficial, e
`copy_golden_for_mutation` (`tests/test_mutation.py:138`) **reescreve os
caminhos absolutos** antes de verificar. A suíte, por construção, compensa o
defeito de portabilidade e jamais poderia detectá-lo.

## 9. Limitações

Ver `LIMITACOES.md`.

## 10. Veredito independente

**`NAO_APTA_PARA_T1`.**

A suíte de 462 testes passa, e isso foi confirmado de forma independente. Mas
`462 passed` prova apenas que a suíte existente passa. Sete portões de bloqueio
do plano foram acionados, com dois achados CRÍTICOS e quatro ALTOS. O pacote de
evidências da Fase T0 não é verificável fora desta máquina, o verificador altera
aquilo que verifica, um run esvaziado é aprovado, e o pipeline entrega arquivos
de vídeo vazios anunciados como sucesso.

A Fase T0 permanece **BLOQUEADA**. A decisão final pertence ao revisor humano.

## 11. Condições objetivas para desbloqueio

1. Migrar as chamadas de subprocesso de `src/youtube_clipper/` para `run_cmd()`
   e estender o scanner AST a todo `src/` (`AUD-T0-001`).
2. Fazer o contrato de `@audited` falhar quando um módulo de `STAGE_MODULES`
   não existir (`AUD-T0-002`).
3. Gravar caminhos relativos ao run e versionar, dentro do pacote entregue, os
   artefatos que ele declara (`AUD-T0-003`).
4. Tornar `cortes.verify` estritamente read-only, com diretório de saída
   separado e sem criar runs colaterais (`AUD-T0-004`).
5. Corrigir o offset após `download_segment()` e validar o artefato por
   `ffprobe` antes de declarar sucesso (`AUD-T0-005`).
6. Fechar a superfície do dashboard: bind em loopback, autenticação, allowlist
   restrita e estado por requisição (`AUD-T0-006`).
7. Adicionar CI que execute a suíte em runner limpo (`AUD-T0-007`).
8. Proteger `main` e exigir PR (`AUD-T0-008`).
9. Derivar os checks de mídia dos artefatos declarados e reprovar quando
   faltarem (`AUD-T0-009`).
10. Tornar `check_id` único por artefato e uniformizar o formato do caminho
    (`AUD-T0-010`).
11. Reconciliar a contagem de testes documentada (`AUD-T0-011`).
12. Regerar o golden run após as correções e revalidá-lo em checkout limpo,
    em máquina sem acesso aos caminhos originais.
