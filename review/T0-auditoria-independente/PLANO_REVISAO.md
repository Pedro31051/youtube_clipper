# Plano de Revisão Independente — Fase T0

## 1. Identificação

- Repositório: `Pedro31051/youtube_clipper`
- URL: `https://github.com/Pedro31051/youtube_clipper`
- Branch-base: `main`
- Baseline observada na elaboração deste plano:
  `fbe8cc5462537dbcaa44ddf6c9182ac218b22c25`
- Natureza do trabalho: auditoria independente, reprodução de provas e
  documentação.
- Não faz parte deste trabalho: corrigir código, alterar credenciais, publicar
  vídeos, baixar material de terceiros, avançar para T1 ou mesclar alterações.

## 2. Objetivo

Determinar, com provas reproduzíveis salvas no próprio Git, se a implementação
da Fase T0 cumpre de fato os contratos de:

1. auditabilidade;
2. exclusividade de `run_cmd()` para comandos externos;
3. integridade e portabilidade dos eventos e artefatos;
4. verificação independente e sem efeitos colaterais;
5. testes de mutação capazes de rejeitar artefatos corrompidos;
6. disciplina de branch, commit e evidência;
7. separação entre afirmação narrativa e resultado efetivamente medido.

O auditor não deve aceitar como prova frases presentes em relatórios anteriores.
Cada conclusão deverá apontar para um arquivo de evidência, o comando executado
e seu código de saída.

## 3. Regras obrigatórias

1. Começar em uma cópia limpa do repositório.
2. Registrar o SHA exato da baseline antes de qualquer teste.
3. Criar uma branch própria antes de gravar qualquer arquivo:
   `agent/auditoria-independente-t0`.
4. Não trabalhar nem fazer commit diretamente em `main`.
5. Não modificar arquivos em `src/`, `tests/`, `runs/` ou no pacote
   `review/T0/` existente.
6. Não apagar nem corrigir evidências anteriores.
7. Toda saída desta revisão ficará exclusivamente em:
   `review/T0-auditoria-independente/<RUN_ID>/`.
8. Usar um `RUN_ID` UTC determinístico no formato
   `audit_t0_YYYYMMDDTHHMMSSZ`.
9. Arquivos temporários usados para testes de relocação ou mutação devem ficar
   fora do repositório ou dentro de
   `review/T0-auditoria-independente/<RUN_ID>/scratch/`.
10. Não ler, copiar ou registrar cookies, tokens, chaves, arquivos OAuth,
    variáveis secretas ou credenciais do Google/YouTube.
11. Não fazer download de vídeo de terceiros. Para testes de mídia, usar
    apenas o MP4 sintético já versionado ou mídia criada localmente com
    `ffmpeg lavfi`.
12. Não iniciar o dashboard em interface pública. Se for indispensável
    executá-lo, restringir o teste a ambiente isolado e loopback.
13. Não declarar “APROVADO” apenas porque `pytest` terminou verde.
14. Não avançar para T1.
15. Ao terminar, fazer commit e push apenas do diretório desta auditoria.
16. Não mesclar a branch. A decisão final pertence ao revisor humano.

## 4. Estrutura obrigatória do pacote

Criar:

```text
review/T0-auditoria-independente/<RUN_ID>/
├── PACOTE.md
├── RELATORIO.md
├── VEREDITO.json
├── LIMITACOES.md
├── HIPOTESES.csv
├── INVENTARIO.txt
├── COMANDOS.jsonl
├── MANIFESTO_SHA256.txt
├── evidencias/
│   ├── 00-baseline-git.txt
│   ├── 01-ambiente.txt
│   ├── 02-arquivos-relevantes.txt
│   ├── 03-pytest-completo.txt
│   ├── 04-pytest-contracts.txt
│   ├── 05-pytest-mutation.txt
│   ├── 06-subprocess-scan.txt
│   ├── 07-stage-modules.txt
│   ├── 08-portabilidade.txt
│   ├── 09-verificador-readonly.txt
│   ├── 10-corte-duplo.txt
│   ├── 11-dashboard-superficie.txt
│   ├── 12-ci-e-branches.txt
│   ├── 13-git-diff-final.txt
│   └── pytest.xml
└── scratch/
```

Não omitir arquivos sem explicação. Se um teste não puder ser executado,
registrar a causa literal em sua evidência e em `LIMITACOES.md`.

## 5. Protocolo de captura de provas

Para cada comando executado, registrar uma linha em `COMANDOS.jsonl` contendo:

```json
{
  "seq": 1,
  "ts_utc": "ISO-8601",
  "cwd": "diretório",
  "cmd": "comando literal",
  "exit_code": 0,
  "stdout_path": "caminho relativo da evidência",
  "stderr_path": "caminho relativo ou null",
  "duration_ms": 0
}
```

Requisitos:

- nunca substituir uma evidência já capturada;
- preservar stdout e stderr literais;
- não editar manualmente uma saída para fazê-la parecer limpa;
- não remover mensagens de erro;
- mascarar eventual segredo antes de versionar e registrar expressamente que
  houve mascaramento;
- toda afirmação de `RELATORIO.md` deve citar ao menos uma evidência relativa;
- gerar `MANIFESTO_SHA256.txt` somente depois de concluído o pacote;
- o manifesto deve abranger todos os arquivos do pacote, exceto ele próprio;
- depois do manifesto, nenhuma evidência pode ser alterada.

## 6. Ordem da revisão

### Etapa 0 — Preparação e isolamento

1. Confirmar que o repositório correto está aberto.
2. Registrar:
   - `git status --short --branch`;
   - `git remote -v`;
   - `git rev-parse HEAD`;
   - `git branch --show-current`;
   - `git log -10 --oneline --decorate`;
   - data/hora UTC.
3. Se houver alteração não relacionada, parar sem sobrescrevê-la.
4. Atualizar referências remotas sem alterar o working tree.
5. Confirmar que a baseline é a ponta de `origin/main`.
6. Criar a branch `agent/auditoria-independente-t0`.
7. Criar o diretório exclusivo da auditoria.

Saída: `evidencias/00-baseline-git.txt`.

### Etapa 1 — Inventário e ambiente

Registrar, sem instalar silenciosamente:

- sistema operacional;
- arquitetura;
- versão do Python;
- versão do Git;
- versão do FFmpeg e ffprobe;
- versão do pytest;
- dependências declaradas em `pyproject.toml` e `requirements.txt`;
- árvore de arquivos relevantes;
- tamanho e hash dos arquivos do pacote T0 existente;
- existência ou ausência de `.github/workflows/`;
- branches locais e remotas;
- existência de PR relacionado, quando a ferramenta disponível permitir
  consulta autenticada.

Saídas:

- `INVENTARIO.txt`;
- `evidencias/01-ambiente.txt`;
- `evidencias/02-arquivos-relevantes.txt`.

### Etapa 2 — Reprodução da suíte declarada

Executar, nesta ordem:

1. instalação do projeto em ambiente virtual isolado, se necessária;
2. `pytest` completo;
3. `tests/test_contracts.py` isoladamente;
4. `tests/test_mutation.py` isoladamente;
5. geração de JUnit XML.

Registrar:

- comando literal;
- dependências instaladas;
- quantidade coletada;
- aprovados, falhos, pulados e erros;
- duração;
- código de saída.

Não resumir “406 testes verdes” se a contagem real for diferente. Não tratar
testes mockados como prova de execução real de FFmpeg, ffprobe, Whisper,
YouTube ou Google Drive.

Saídas:

- `evidencias/03-pytest-completo.txt`;
- `evidencias/04-pytest-contracts.txt`;
- `evidencias/05-pytest-mutation.txt`;
- `evidencias/pytest.xml`.

### Etapa 3 — Verificações adversariais obrigatórias

Cada hipótese abaixo deverá terminar com um dos estados:

- `CONFIRMADA`;
- `REFUTADA`;
- `INCONCLUSIVA`;
- `BLOQUEADA`.

Registrar os resultados em `HIPOTESES.csv`.

#### H01 — O scanner AST não cobre todo o código produtivo

Verificar se o teste de exclusividade de `run_cmd()` examina todo `src/` ou
somente `src/cortes/`.

Fazer uma busca independente, no mínimo, por:

- `subprocess`;
- `os.system`;
- `os.popen`;
- `os.spawn*`;
- `asyncio.create_subprocess*`;
- `eval`;
- `exec`;
- `__import__`;
- `importlib.import_module`.

Classificar cada ocorrência como autorizada, proibida ou falso positivo.
Verificar especialmente `src/youtube_clipper/processor.py` e
`src/youtube_clipper/analyzer.py`.

Saída: `evidencias/06-subprocess-scan.txt`.

#### H02 — Módulos de estágio ausentes são ignorados silenciosamente

Listar os módulos exigidos por `STAGE_MODULES` e provar quais existem.
Inspecionar se `test_contracts.py` falha ou executa `continue` quando um módulo
está ausente.

Executar um teste adversarial em cópia temporária, sem alterar os testes
versionados, demonstrando o comportamento com um módulo esperado ausente.

Saída: `evidencias/07-stage-modules.txt`.

#### H03 — As evidências do golden run não são portáveis

1. Inventariar todos os caminhos armazenados em:
   - `events.jsonl`;
   - `verify_result.json`;
   - `commands.log`;
   - `report.md`.
2. Separar caminhos absolutos e relativos.
3. Exportar a baseline para um diretório temporário diferente, sem histórico e
   sem aproveitar os caminhos originais.
4. Executar o verificador exatamente como um revisor externo faria.
5. Registrar o código de saída e os checks que passaram ou falharam.

Não ajustar caminhos manualmente durante este teste.

Saída: `evidencias/08-portabilidade.txt`.

#### H04 — O verificador modifica estado ou grava no run errado

1. Gerar hashes de todos os arquivos do run antes da verificação.
2. Registrar a árvore de `runs/` antes do teste.
3. Executar `verify.py` fornecendo apenas o caminho do run.
4. Gerar novamente hashes, árvore, `git status` e timestamps.
5. Identificar:
   - arquivos criados;
   - arquivos modificados;
   - eventos acrescentados;
   - criação de outro run;
   - dependência de `CORTES_RUN_ID` ou `set_run_id()`.
6. Repetir em cópia temporária para não modificar a evidência original.

O verificador somente será considerado read-only se o conteúdo verificado
permanecer byte a byte idêntico e nenhuma gravação inesperada ocorrer.

Saída: `evidencias/09-verificador-readonly.txt`.

#### H05 — O corte de URL do YouTube aplica o offset duas vezes

Não acessar o YouTube. Usar monkeypatch controlado ou fixture local para fazer
o downloader devolver um arquivo já recortado começando em `t=0`, como ocorre
após `download_segment()`.

Testar um intervalo absoluto incompatível com a duração do segmento, por
exemplo fonte retornada de 30 segundos e solicitação original de 60–90
segundos.

Medir:

- comando FFmpeg efetivamente construído;
- código de saída;
- existência e tamanho do MP4;
- duração via ffprobe;
- comportamento final do pipeline.

O teste deve distinguir claramente:

- erro corretamente detectado;
- arquivo inválido aceito como sucesso;
- comportamento não reproduzível.

Saída: `evidencias/10-corte-duplo.txt`.

#### H06 — O dashboard possui superfície insegura quando exposto

Fazer revisão estática e, somente se seguro, teste local isolado para verificar:

- endereço padrão de bind;
- presença ou ausência de autenticação;
- aceitação de URL arbitrária;
- aceitação de `file_path` arbitrário no upload;
- diretório permitido por `/api/download/`;
- alteração global de `YOUTUBE_COOKIES_FILE`;
- comportamento com requisições simultâneas.

Não enviar arquivos ao Drive e não iniciar serviço acessível externamente.

Saída: `evidencias/11-dashboard-superficie.txt`.

#### H07 — Não existe CI independente comprovando a suíte

Verificar:

- `.github/workflows/`;
- status/checks do commit-base, quando acessível;
- configuração de lint, type check e pytest;
- correspondência entre o número de testes documentado e o realmente
  coletado.

Não confundir relatório commitado com execução de CI.

Saída: `evidencias/12-ci-e-branches.txt`.

#### H08 — A disciplina de branch da própria T0 foi descumprida

Verificar:

- branches existentes;
- commits da implementação T0;
- presença ou ausência de PR;
- regra escrita sobre commits na `main`;
- branch que recebeu os commits observados.

Não atribuir intenção. Relatar apenas o histórico demonstrável.

Usar também `evidencias/12-ci-e-branches.txt`.

### Etapa 4 — Avaliação dos testes de mutação

Mapear cada check de `verify.py` para pelo menos um teste de mutação.

Para cada check:

1. identificar o teste correspondente;
2. verificar se a mutação atinge o artefato real ou apenas uma estrutura
   sintética;
3. confirmar que remover ou inverter a asserção faria o teste falhar;
4. registrar checks sem cobertura;
5. registrar duplicidades de `check_id`;
6. verificar se múltiplos MP4s produzem resultados inequivocamente
   identificáveis.

Não modificar permanentemente os testes. Qualquer mutação experimental ocorrerá
em cópia temporária.

Incluir a conclusão em `RELATORIO.md` e as provas nos arquivos de pytest e de
portabilidade aplicáveis.

### Etapa 5 — Consolidação do relatório

`RELATORIO.md` deverá conter:

1. escopo e baseline;
2. ambiente;
3. metodologia;
4. resultados da suíte;
5. tabela de hipóteses;
6. achados ordenados por gravidade;
7. evidência e reprodução de cada achado;
8. contraprovas consideradas;
9. limitações;
10. veredito independente;
11. condições objetivas para nova revisão.

Cada achado deve usar:

```text
ID:
Título:
Gravidade: CRÍTICA | ALTA | MÉDIA | BAIXA
Estado: CONFIRMADO | REFUTADO | INCONCLUSIVO | BLOQUEADO
Contrato afetado:
Evidência:
Como reproduzir:
Resultado observado:
Resultado esperado:
Impacto:
Contraprova:
Recomendação:
```

Não implementar a recomendação nesta branch.

### Etapa 6 — Veredito estruturado

Criar `VEREDITO.json` com:

```json
{
  "schema_version": "1.0",
  "repository": "Pedro31051/youtube_clipper",
  "baseline_sha": "SHA",
  "run_id": "RUN_ID",
  "verdict": "APTA_PARA_REVISAO_HUMANA|NAO_APTA_PARA_T1|INCONCLUSIVA",
  "pytest": {
    "exit_code": 0,
    "collected": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "errors": 0
  },
  "hypotheses": {
    "confirmed": [],
    "refuted": [],
    "inconclusive": [],
    "blocked": []
  },
  "findings": [
    {
      "id": "AUD-T0-001",
      "severity": "ALTA",
      "status": "CONFIRMADO",
      "evidence_paths": [],
      "reproduction_command_ids": []
    }
  ],
  "limitations": [],
  "generated_at_utc": "ISO-8601"
}
```

O veredito permitido não é “T0 concluída”. A revisão pode apenas indicar se o
pacote está apto para decisão humana ou se deve permanecer bloqueado antes de
T1.

### Etapa 7 — Integridade final

1. Confirmar que nenhum arquivo fora do diretório da auditoria foi alterado.
2. Registrar `git status` e `git diff --stat`.
3. Registrar o diff completo referente ao pacote.
4. Gerar SHA-256 de todas as evidências e documentos.
5. Validar que cada caminho citado em `RELATORIO.md` existe.
6. Validar que cada finding de `VEREDITO.json` aponta para evidência existente.
7. Preencher `PACOTE.md` com:
   - baseline;
   - branch;
   - run ID;
   - lista de arquivos;
   - resumo das execuções;
   - limitações;
   - instrução de reprodução.

Saídas:

- `evidencias/13-git-diff-final.txt`;
- `MANIFESTO_SHA256.txt`;
- `PACOTE.md`.

## 7. Portões de decisão

### Bloquear avanço para T1 se ocorrer qualquer um destes casos

- subprocesso produtivo fora do ponto autorizado;
- verificador alterar o run ou depender de estado externo não declarado;
- golden run não puder ser verificado após relocação;
- caminhos absolutos tornarem a prova dependente da máquina original;
- teste contratual passar por ausência silenciosa dos módulos examinados;
- teste de mutação não rejeitar corrupção relevante;
- arquivo de mídia inválido ser aceito como sucesso;
- provas não possuírem hashes;
- resultados não puderem ser reproduzidos;
- suíte documentada divergir materialmente da suíte executada sem
  justificativa.

### Apta para revisão humana somente se

- todas as evidências forem reproduzíveis a partir da baseline;
- o pacote estiver íntegro e com hashes;
- nenhum achado crítico ou alto confirmado permanecer sem reconhecimento;
- limitações estiverem registradas;
- o relatório não fizer afirmações sem prova;
- a branch contiver exclusivamente o pacote de auditoria.

## 8. Ordem obrigatória de gravação no Git

