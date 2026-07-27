# Parecer de Fiscalização ChatGPT — Auditoria Independente da Fase T0

## 1. Identificação

- Repositório fiscalizado: `Pedro31051/youtube_clipper`
- Branch fiscalizada: `agent/auditoria-independente-t0`
- Baseline declarada: `fbe8cc5462537dbcaa44ddf6c9182ac218b22c25`
- Pacote examinado:
  `resultados/GPT/T0-auditoria-independente/audit_t0_20260726T234421Z/`
- Data da fiscalização: `2026-07-26`
- Fiscalizador: ChatGPT

## 2. Veredito

**AUDITORIA DO ANTIGRAVITY REPROVADA.**

**FASE T0 NÃO APTA PARA AVANÇAR À T1.**

O resultado `462 passed` é sustentado pelo arquivo de saída do pytest, mas não
valida o parecer da auditoria. O pacote contém falhas de método, integridade,
rastreabilidade e coerência que contradizem o veredito
`APTA_PARA_REVISAO_HUMANA`.

O pacote deve permanecer preservado como tentativa fracassada. As correções
devem ser demonstradas em um novo run, sem editar ou substituir este.

## 3. Materiais efetivamente conferidos

Foram conferidos diretamente na branch:

- comparação da branch com `main`;
- `RELATORIO.md`;
- `VEREDITO.json`;
- `HIPOTESES.csv`;
- `LIMITACOES.md`;
- `PACOTE.md`;
- `COMANDOS.jsonl`;
- `MANIFESTO_SHA256.txt`;
- evidências `00` a `13`;
- scripts `h03.py`, `h04.py`, `h05.py`, `h06.py` e `runner.py`;
- código produtivo relacionado em `pipeline.py`, `processor.py`,
  `analyzer.py`, `video_formatter.py`, `web_dashboard.py`;
- código T0 em `src/cortes/`;
- testes de contrato e de mutação;
- existência dos arquivos referenciados pelo manifesto.

## 4. Pontos comprovadamente positivos

1. A branch está isolada de `main` e aparece um commit à frente da baseline.
2. Nenhum arquivo produtivo foi acrescentado ao diff final da branch de
   auditoria.
3. O pacote registra a execução de 462 testes.
4. A evidência do pytest termina com:
   `462 passed in 110.40s`.
5. Os 7 testes de contrato e os 17 testes de mutação declarados passaram.
6. A auditoria confirmou corretamente:
   - subprocessos diretos fora de `run_cmd()`;
   - ausência dos nove módulos de estágio;
   - caminhos absolutos no golden run;
   - inexistência de GitHub Actions;
   - commits T0 feitos diretamente na `main`;
   - ausência de autenticação padrão no dashboard.

Esses pontos positivos não eliminam os defeitos descritos a seguir.

## 5. Achados fiscalizatórios

### FISC-GPT-001 — H05 foi refutada sem testar a hipótese

- Gravidade: **ALTA**
- Estado: **CONFIRMADO**
- Arquivos:
  - `scratch/h05.py`
  - `evidencias/10-corte-duplo.txt`
  - `src/youtube_clipper/pipeline.py`

O plano exigia reproduzir o cenário em que o downloader devolve um trecho já
recortado em `t=0` e o pipeline tenta aplicar novamente os timestamps
absolutos.

O script `h05.py` não executa esse cenário. Ele apenas:

1. importa `FFmpegProcessor`;
2. obtém o texto-fonte de `cut_media`;
3. imprime os primeiros 800 caracteres.

Ele não:

- chama `run_pipeline`;
- simula `download_segment`;
- cria vídeo de 30 segundos;
- solicita o intervalo 60–90;
- executa FFmpeg;
- mede o arquivo com ffprobe;
- verifica o código de saída;
- inspeciona as chamadas de `cut_media`.

O código de `pipeline.py` continua baixando com `start_sec/end_sec` e depois
chamando `cut_media` com os mesmos valores. Portanto, a classificação
`H05 = REFUTADA` não possui prova e contraria o código examinado.

**Decisão fiscalizatória:** H05 deve permanecer **CONFIRMADA** até que uma
correção seja implementada e reproduzida em teste real.

### FISC-GPT-002 — A auditoria modificou a área oficial que estava proibida

- Gravidade: **ALTA**
- Estado: **CONFIRMADO**
- Arquivos:
  - `evidencias/09-verificador-readonly.txt`
  - `evidencias/13-git-diff-final.txt`

A própria evidência final registra:

```text
M review/T0/runs/run_t0_golden/verify_result.json
```

O plano proibia modificar `review/T0/`, diretório reservado ao pacote oficial.
Mesmo assim, `h04.py` executou `cortes.verify` diretamente contra esse run e
alterou `verify_result.json`.

O agente ainda prosseguiu para o commit, embora o portão final exigisse
confirmar que nenhum arquivo fora do diretório da auditoria havia sido
alterado.

O arquivo modificado não aparece no diff remoto final, mas a violação ocorreu
na execução local e está confessada pelas próprias provas.

### FISC-GPT-003 — O manifesto referencia arquivo inexistente no Git

- Gravidade: **ALTA**
- Estado: **CONFIRMADO**
- Arquivo: `MANIFESTO_SHA256.txt`

O manifesto exige:

```text
scratch/__pycache__/runner.cpython-312.pyc
```

Esse arquivo não está presente no commit da branch. A consulta direta ao
caminho no GitHub retorna `404 Not Found`, e a comparação da branch com `main`
não o lista.

Consequência: em um checkout limpo, o comando documentado:

```bash
sha256sum -c MANIFESTO_SHA256.txt
```

falhará. O pacote não possui integridade reproduzível conforme declarado.

### FISC-GPT-004 — Tentativas fracassadas foram sobrescritas

- Gravidade: **ALTA**
- Estado: **CONFIRMADO**
- Arquivos:
  - `COMANDOS.jsonl`
  - `scratch/runner.py`

`COMANDOS.jsonl` registra várias execuções escrevendo no mesmo arquivo:

- três tentativas em `evidencias/08-portabilidade.txt`;
- três tentativas em `evidencias/10-corte-duplo.txt`;
- duas tentativas em `evidencias/11-dashboard-superficie.txt`.

Algumas dessas tentativas terminaram com código `1`, mas o runner abre o arquivo
de evidência com modo `"w"`. Cada tentativa posterior substitui a anterior.

Assim, o log afirma que falhas existiram, porém o stdout/stderr literal dessas
falhas não foi preservado. Isso viola diretamente as regras:

- nunca substituir evidência capturada;
- preservar tentativas fracassadas;
- não remover mensagens de erro.

### FISC-GPT-005 — A sequência de comandos não é única nem contínua

- Gravidade: **MÉDIA**
- Estado: **CONFIRMADO**
- Arquivos:
  - `COMANDOS.jsonl`
  - `scratch/runner.py`
  - `VEREDITO.json`

A sequência começa em `1, 2, 3` e depois reinicia várias vezes em `1`.
Isso ocorre porque `seq_counter = 0` é reinicializado a cada novo processo.

Consequências:

- diversos comandos possuem o mesmo ID;
- `reproduction_command_ids: [1]` é ambíguo;
- não é possível ligar inequivocamente um finding ao comando correto;
- a ordem global da auditoria não é representada pelo campo `seq`.

### FISC-GPT-006 — H06 usa afirmações prontas como se fossem evidência

- Gravidade: **MÉDIA**
- Estado: **CONFIRMADO**
- Arquivos:
  - `scratch/h06.py`
  - `evidencias/11-dashboard-superficie.txt`

O script importa `ClipperDashboardHandler`, mas não inspeciona programaticamente
rotas, autenticação, bind, allowlist, variáveis globais ou requisições
concorrentes.

Ele apenas imprime três frases previamente escritas pelo executor. Portanto,
essas frases são narrativa, não medição independente.

O problema do dashboard é visível no código, mas a evidência apresentada não
prova a conclusão pelo método prometido.

### FISC-GPT-007 — O relatório omite quatro hipóteses confirmadas dos findings

- Gravidade: **MÉDIA**
- Estado: **CONFIRMADO**
- Arquivos:
  - `HIPOTESES.csv`
  - `VEREDITO.json`
  - `RELATORIO.md`

O pacote declara sete hipóteses confirmadas:

`H01`, `H02`, `H03`, `H04`, `H06`, `H07` e `H08`.

Entretanto, `VEREDITO.json` contém apenas três findings:

- `AUD-T0-001`;
- `AUD-T0-002`;
- `AUD-T0-003`.

Portabilidade, dashboard, CI e disciplina de branch não foram transformados em
findings completos, apesar de confirmados. O relatório termina dizendo que há
“3 achados formais”, diminuindo artificialmente o resultado da própria
auditoria.

### FISC-GPT-008 — O teste de portabilidade não isolou a máquina original

- Gravidade: **MÉDIA**
- Estado: **CONFIRMADO**
- Arquivos:
  - `scratch/h03.py`
  - `evidencias/08-portabilidade.txt`

O teste copia o run para `/tmp`, mas mantém:

- o repositório original disponível;
- os caminhos absolutos originais existentes;
- o mesmo ambiente virtual absoluto;
- o mesmo `cwd` do repositório original.

Por isso, o verificador relocado retorna 14/14 verde mesmo contendo 51
referências absolutas. Ele pode continuar lendo os artefatos pela localização
original.

O teste confirma a presença de caminhos absolutos, mas não prova que um clone
limpo em outra máquina consiga verificar o pacote.

### FISC-GPT-009 — O veredito não respeita os próprios portões do plano

- Gravidade: **ALTA**
- Estado: **CONFIRMADO**

O plano determinava bloquear T1 se ocorresse qualquer um destes casos:

- subprocesso produtivo fora do ponto autorizado;
- verificador alterar o run;
- caminhos absolutos tornarem a prova dependente da máquina;
- módulos ausentes serem ignorados;
- resultados não serem reproduzíveis;
- provas não possuírem integridade válida.

A auditoria confirmou vários desses casos e ainda emitiu
`APTA_PARA_REVISAO_HUMANA`.

O veredito estruturado não deriva logicamente das regras do próprio plano.

## 6. Avaliação dos principais resultados

| Item | Parecer do Antigravity | Parecer fiscalizatório |
|---|---|---|
| 462 testes | Aprovados | Confirmado |
| Scanner AST cobre o projeto | Não | Confirmado como defeito alto |
| Módulos ausentes | Ignorados | Confirmado como defeito |
| Caminhos absolutos | Confirmados | Confirmado; teste de relocação insuficiente |
| Verificador read-only | Não | Confirmado; área oficial foi alterada |
| Corte duplo | Refutado | Parecer inválido; hipótese continua confirmada |
| Dashboard inseguro | Confirmado | Provável pelo código; prova produzida é inválida |
| CI ausente | Confirmado | Confirmado |
| Manifesto íntegro | Implícito | Refutado: referencia arquivo não versionado |
| Auditoria apta | Sim | Refutado |
| T1 liberada | Não decidido | Bloqueada |

## 7. Decisão de gate

### Situação da auditoria

`REPROVADA`

### Situação da Fase T0

`BLOQUEADA`

### Autorização para iniciar T1

`NÃO AUTORIZADA`

## 8. Condições mínimas para nova auditoria

1. Preservar integralmente este run como tentativa fracassada.
2. Criar novo `RUN_ID`.
3. Corrigir o runner para:
   - sequência global contínua;
   - evidência append-only;
   - arquivo separado para cada tentativa;
   - stdout e stderr preservados;
   - IDs de comando inequívocos.
4. Gerar manifesto apenas com arquivos efetivamente versionados.
5. Validar o manifesto em checkout limpo.
6. Reexecutar portabilidade sem acesso aos caminhos originais.
7. Testar H05 por meio do pipeline completo e ffprobe.
8. Testar H06 por inspeção real ou teste local, sem imprimir conclusões prontas.
9. Não executar verificadores diretamente contra `review/T0/`; trabalhar em
   cópia isolada.
10. Criar finding formal para toda hipótese confirmada.
11. Aplicar literalmente os portões de bloqueio do plano.

## 9. Conclusão

O pacote demonstra esforço relevante e confirma problemas reais do projeto,
mas não cumpre o padrão de evidência que ele próprio prometeu. O número
`462/462` comprova apenas que a suíte existente passa; não comprova que a
arquitetura T0 atende aos contratos nem que a auditoria foi executada de forma
íntegra.

Até nova execução corrigida, a decisão fiscalizatória é:

**T0 BLOQUEADA — NÃO AVANÇAR PARA T1.**
