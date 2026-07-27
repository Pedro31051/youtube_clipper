# Relatório de Auditoria Independente — Repetição T0

## 1. Escopo e baseline

Auditoria independente do repositório `Pedro31051/youtube_clipper`, baseline
`fbe8cc5462537dbcaa44ddf6c9182ac218b22c25`, executada na branch `agent/refazer-auditoria-independente-t0` e no run `audit_t0_20260727T022339Z`. O estado Git,
remotos e ausência de diferenças produtivas estão em `evidencias/00-baseline-git.txt`.

## 2. Ambiente

O ambiente isolado usa Python 3.12.3, pytest 9.1.1, FFmpeg/ffprobe 6.1.1 e Git
2.43.0. Versões e dependências completas estão em `evidencias/01-ambiente.txt`;
inventário e hashes do pacote oficial, em `evidencias/02-arquivos-relevantes.txt`.

## 3. Metodologia

Cada comando recebeu sequência global e ID único em `COMANDOS.jsonl`; stdout e
stderr foram preservados em arquivos exclusivos. H03 usou contêiner sem `/home`,
H04 trabalhou apenas em cópia temporária, H05 executou `run_pipeline` com mídia
sintética e ffprobe, e H06 abriu apenas loopback. Provas:
`evidencias/08-portabilidade.txt`, `evidencias/09-verificador-readonly.txt`,
`evidencias/10-corte-duplo.txt` e `evidencias/11-dashboard-superficie.txt`.

## 4. Resultados da suíte

- Suíte completa: **462/462 aprovados**, 0 falhas, 0 pulados, 0 erros
  (`evidencias/03-pytest-completo.txt`, `evidencias/pytest.xml`).
- Contratos: **7/7 aprovados** (`evidencias/04-pytest-contracts.txt`).
- Mutações declaradas: **17/17 aprovadas** (`evidencias/05-pytest-mutation.txt`).
- Contraprova adversarial: remoção integral dos artefatos foi aceita como válida
  (`evidencias/12-mutacao-cobertura.txt`).

## 5. Hipóteses

| ID | Hipótese | Estado |
|---|---|---|
| H01 | Scanner AST não cobre todo o código produtivo | CONFIRMADA |
| H02 | Módulos de estágio ausentes são ignorados silenciosamente | CONFIRMADA |
| H03 | Golden run não é portável | CONFIRMADA |
| H04 | Verificador modifica estado | CONFIRMADA |
| H05 | Pipeline aplica offset duas vezes | CONFIRMADA |
| H06 | Dashboard exposto possui superfície insegura | CONFIRMADA |
| H07 | CI/branch | CONFIRMADA |
| H08 | CI/branch | CONFIRMADA |

Fonte tabular: `HIPOTESES.csv`.

## 6. Achados por gravidade

### AUD-T0-001 — Corte duplo produz MP4 inválido aceito como sucesso

- **ID:** AUD-T0-001
- **Gravidade:** CRÍTICA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Integridade do artefato de mídia e detecção barulhenta de falhas.
- **Evidência:** `evidencias/10-corte-duplo.txt`; comando `audit_t0_20260727T022339Z#0012`.
- **Como reproduzir:** executar o comando de ID 12 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** run_pipeline reaplicou 60–90 s ao segmento local de 30 s; o resultado inválido foi aceito.
- **Resultado esperado:** O segmento já recortado deveria ser processado desde t=0, ou a saída inválida deveria causar erro.
- **Impacto:** Corrupção silenciosa do produto entregue.
- **Contraprova:** A suíte completa passa, mas o cenário realista de offset consumido não faz parte do caminho coberto.
- **Recomendação:** Normalizar o offset após download_segment e validar tamanho, streams e duração com ffprobe.
### AUD-T0-002 — Scanner AST deixa subprocessos produtivos fora de run_cmd

- **ID:** AUD-T0-002
- **Gravidade:** ALTA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Exclusividade de run_cmd para comandos externos.
- **Evidência:** `evidencias/06-subprocess-scan.txt`; comando `audit_t0_20260727T022339Z#0008`.
- **Como reproduzir:** executar o comando de ID 8 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** Foram medidas 13 ocorrências proibidas fora do escopo efetivo do teste.
- **Resultado esperado:** Todo src/ deve ser varrido e somente cortes/log.py pode executar comandos externos.
- **Impacto:** Partes produtivas podem escapar da trilha de auditoria.
- **Contraprova:** Os 7 testes contratuais passam porque a raiz inspecionada é restrita.
- **Recomendação:** Expandir o scanner contratual para todos os pacotes sob src/.
### AUD-T0-003 — Golden run não é verificável após relocação limpa

- **ID:** AUD-T0-003
- **Gravidade:** ALTA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Portabilidade e verificabilidade independente das evidências.
- **Evidência:** `evidencias/08-portabilidade.txt`; comando `audit_t0_20260727T022339Z#0010`.
- **Como reproduzir:** executar o comando de ID 10 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** Há 54 referências absolutas e 0 relativas; em contêiner sem /home o overall_passed foi false.
- **Resultado esperado:** Um checkout limpo deve verificar integralmente o pacote sem caminhos da máquina de origem.
- **Impacto:** O pacote não constitui prova reproduzível fora do host produtor.
- **Contraprova:** A cópia local retorna verde, mas também retorna verde após remover os próprios artefatos.
- **Recomendação:** Armazenar caminhos relativos ao run e tornar o verificador dependente apenas do pacote fornecido.
### AUD-T0-004 — Verificador altera o run e cria run colateral

- **ID:** AUD-T0-004
- **Gravidade:** ALTA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Verificação read-only e ausência de efeitos colaterais.
- **Evidência:** `evidencias/09-verificador-readonly.txt`; comando `audit_t0_20260727T022339Z#0011`.
- **Como reproduzir:** executar o comando de ID 11 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** Na cópia isolada, verify_result.json foi modificado e um novo runs/run_* foi criado no CWD.
- **Resultado esperado:** Hashes e árvore devem permanecer byte a byte idênticos.
- **Impacto:** A verificação muda a própria prova e confunde a procedência do resultado.
- **Contraprova:** A área oficial review/T0 permaneceu intacta nesta repetição porque o teste usou cópia temporária.
- **Recomendação:** Separar saída do verificador e impedir inicialização de run durante verificação.
### AUD-T0-005 — Verificador aceita remoção integral dos artefatos

- **ID:** AUD-T0-005
- **Gravidade:** ALTA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Testes de mutação devem rejeitar corrupção e ausência de artefatos relevantes.
- **Evidência:** `evidencias/12-mutacao-cobertura.txt`; comando `audit_t0_20260727T022339Z#0014`.
- **Como reproduzir:** executar o comando de ID 14 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** A mutação artefato_declarado_removido terminou com exit 0 e overall_passed true.
- **Resultado esperado:** Remover os artefatos declarados deve reprovar o run.
- **Impacto:** Um pacote sem produto pode ser classificado como válido.
- **Contraprova:** MP4 truncado e SHA alterado foram corretamente rejeitados.
- **Recomendação:** Exigir presença de todo artefato declarado antes de reduzir dinamicamente o conjunto de checks.
### AUD-T0-006 — Dashboard expõe arquivos e estado global sem autenticação

- **ID:** AUD-T0-006
- **Gravidade:** ALTA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Exposição segura do dashboard e isolamento entre requisições.
- **Evidência:** `evidencias/11-dashboard-superficie.txt`; comando `audit_t0_20260727T022339Z#0013`.
- **Como reproduzir:** executar o comando de ID 13 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** Teste em loopback serviu arquivo do CWD anonimamente e comprovou corrida em YOUTUBE_COOKIES_FILE.
- **Resultado esperado:** Bind seguro, autenticação, allowlist dedicada e estado por requisição.
- **Impacto:** Quando exposto, permite leitura indevida e interferência entre clientes.
- **Contraprova:** O path traversal explícito foi rejeitado, mas CWD e /tmp permanecem permitidos.
- **Recomendação:** Usar 127.0.0.1 por padrão, autenticar e remover estado global/allowlists amplas.
### AUD-T0-007 — Teste de decoradores passa por vacuidade

- **ID:** AUD-T0-007
- **Gravidade:** MÉDIA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Integridade da malha de estágios auditados.
- **Evidência:** `evidencias/07-stage-modules.txt`; comando `audit_t0_20260727T022339Z#0009`.
- **Como reproduzir:** executar o comando de ID 9 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** Nenhum dos módulos exigidos existe e o teste passa; módulo presente sem @audited faz o teste falhar.
- **Resultado esperado:** A ausência de módulo exigido deve falhar explicitamente.
- **Impacto:** Verde contratual transmite cobertura inexistente.
- **Contraprova:** Quando um módulo existe, o teste identifica a ausência do decorador.
- **Recomendação:** Assegurar existência de todos os STAGE_MODULES antes de inspecionar decoradores.
### AUD-T0-008 — Baseline não possui CI independente

- **ID:** AUD-T0-008
- **Gravidade:** MÉDIA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Execução independente e contínua da suíte.
- **Evidência:** `evidencias/12-ci-e-branches.txt`; comando `audit_t0_20260727T022339Z#0015`.
- **Como reproduzir:** executar o comando de ID 15 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** Não há workflows locais, check-runs ou statuses no commit-base.
- **Resultado esperado:** CI versionada deve executar ao menos contratos, mutações e suíte completa.
- **Impacto:** Resultados dependem de execuções manuais commitadas.
- **Contraprova:** A auditoria reproduziu localmente 462 testes verdes.
- **Recomendação:** Adicionar workflow obrigatório com pytest, contratos e mutações.
### AUD-T0-009 — Commits T0 estão diretamente na main

- **ID:** AUD-T0-009
- **Gravidade:** MÉDIA
- **Estado:** CONFIRMADO
- **Contrato afetado:** Disciplina de branch e revisão humana.
- **Evidência:** `evidencias/12-ci-e-branches.txt`; comando `audit_t0_20260727T022339Z#0015`.
- **Como reproduzir:** executar o comando de ID 15 registrado em `COMANDOS.jsonl`.
- **Resultado observado:** f4f13a3 e fbe8cc5 integram o histórico de main; não há PR correspondente à implementação T0.
- **Resultado esperado:** Implementação deveria chegar por branch e revisão, conforme regra escrita.
- **Impacto:** Reduz separação de funções e rastreabilidade da aprovação.
- **Contraprova:** A nova auditoria está isolada em branch própria.
- **Recomendação:** Aplicar proteção de branch e exigir PR/checks para fases futuras.


## 7. Contraprovas consideradas

O verde de 462 testes foi preservado como resultado positivo, mas não anulou as
execuções adversariais. O verificador rejeitou MP4 truncado e SHA alterado, porém
aceitou ausência de todos os artefatos. O path traversal explícito do dashboard
foi bloqueado, porém arquivos nas allowlists amplas foram servidos sem autenticação.
Provas: `evidencias/12-mutacao-cobertura.txt` e
`evidencias/11-dashboard-superficie.txt`.

## 8. Limitações

As limitações integrais estão em `LIMITACOES.md`.

## 9. Veredito independente

**NAO_APTA_PARA_T1**.

O veredito é derivado dos portões: há subprocessos fora de `run_cmd`, golden run
não portável, verificador não read-only, teste contratual vacuamente verde,
mutação relevante aceita, mídia inválida aceita como sucesso e ausência de CI.
Cada condição está provada, respectivamente, em
`evidencias/06-subprocess-scan.txt`, `evidencias/08-portabilidade.txt`,
`evidencias/09-verificador-readonly.txt`, `evidencias/07-stage-modules.txt`,
`evidencias/12-mutacao-cobertura.txt`, `evidencias/10-corte-duplo.txt` e
`evidencias/12-ci-e-branches.txt`.

## 10. Condições objetivas para nova revisão

Corrigir e provar novamente os nove findings; exigir especialmente zero
subprocessos produtivos fora de `run_cmd`, verificação portátil/read-only,
rejeição de artefatos ausentes, saída de mídia válida para URL segmentada,
dashboard isolado/autenticado e CI obrigatória. A decisão final permanece com o
revisor humano.
