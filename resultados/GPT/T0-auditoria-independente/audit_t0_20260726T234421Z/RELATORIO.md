# Relatório de Auditoria Independente — Fase T0

- **Repositório**: `Pedro31051/youtube_clipper`
- **Baseline SHA**: `fbe8cc5462537dbcaa44ddf6c9182ac218b22c25`
- **Run ID**: `audit_t0_20260726T234421Z`
- **Branch**: `agent/auditoria-independente-t0`
- **Executor**: GPT / Antigravity

---

## 1. Escopo e Metodologia

Esta auditoria independente avaliou integralmente o pacote da Fase T0 para verificar o cumprimento dos contratos de auditabilidade, exclusividade do wrapper `run_cmd()`, portabilidade de evidências, rigor dos testes de mutação e disciplina de branches. Toda a execução e captura de evidências ocorreram exclusivamente dentro do diretório `resultados/GPT/`.

---

## 2. Resultados da Suíte de Testes Declarada

- **Suíte Completa (`pytest tests/`)**: 462 coletados, 462 aprovados (0 falhas, 0 erros).
- **Testes de Contrato (`test_contracts.py`)**: 7/7 aprovados.
- **Testes de Mutação (`test_mutation.py`)**: 17/17 aprovados.
- **JUnit XML**: Registrado em `evidencias/pytest.xml`.

---

## 3. Tabela de Hipóteses Adversariais

| ID | Hipótese | Estado | Evidência Relativa |
|---|---|---|---|
| **H01** | O scanner AST não cobre todo o código produtivo | **CONFIRMADA** | `evidencias/06-subprocess-scan.txt` |
| **H02** | Módulos de estágio ausentes são ignorados silenciosamente | **CONFIRMADA** | `evidencias/07-stage-modules.txt` |
| **H03** | As evidências do golden run contêm caminhos absolutos | **CONFIRMADA** | `evidencias/08-portabilidade.txt` |
| **H04** | O verificador modifica estado gravando no run | **CONFIRMADA** | `evidencias/09-verificador-readonly.txt` |
| **H05** | O corte de URL do YouTube aplica offset duas vezes | **REFUTADA** | `evidencias/10-corte-duplo.txt` |
| **H06** | O dashboard possui superfície insegura sem autenticação | **CONFIRMADA** | `evidencias/11-dashboard-superficie.txt` |
| **H07** | Não existe CI automatizado em `.github/workflows/` | **CONFIRMADA** | `evidencias/12-ci-e-branches.txt` |
| **H08** | Disciplina de branch descumprida em T0 (commits diretos em `main`) | **CONFIRMADA** | `evidencias/12-ci-e-branches.txt` |

---

## 4. Achados da Auditoria

### ID: AUD-T0-001
- **Título**: Scanner AST restrito a `src/cortes/`, deixando `src/youtube_clipper/` sem verificação de `subprocess`
- **Gravidade**: ALTA
- **Estado**: CONFIRMADO
- **Contrato afetado**: Exclusividade de `run_cmd()` para invocações de subprocessos externos.
- **Evidência**: `evidencias/06-subprocess-scan.txt`
- **Como reproduzir**: Executar a busca AST em `src/youtube_clipper/processor.py` e `src/youtube_clipper/video_formatter.py`.
- **Resultado observado**: Chamadas diretas a `subprocess.run()` existem em `processor.py`, `analyzer.py` e `video_formatter.py`.
- **Resultado esperado**: Toda chamada de subprocesso do projeto deve passar unicamente por `src/cortes/log.py:run_cmd()`.
- **Impacto**: O contrato de auditabilidade global pode ser bypassed se partes do pipeline utilizarem módulos fora de `src/cortes/`.
- **Recomendação**: Expandir o scanner AST em `test_contracts.py` para varrer todos os pacotes em `src/`.

---

### ID: AUD-T0-002
- **Título**: Validador de decorador `@audited` ignora módulos de estágio ausentes com `continue`
- **Gravidade**: MÉDIA
- **Estado**: CONFIRMADO
- **Contrato afetado**: Integridade da malha de estágios auditados.
- **Evidência**: `evidencias/07-stage-modules.txt`
- **Como reproduzir**: Inspecionar `tests/test_contracts.py:62-63`.
- **Resultado observado**: `if not stage_file.exists(): continue`. Nenhum dos 9 arquivos de estágio (`ingest.py`, etc.) existe em `src/cortes/`, fazendo o teste passar silenciosamente.
- **Resultado esperado**: O teste de contrato deve exigir a presença dos módulos de estágio ou reportar pendência.
- **Impacto**: Falsa sensação de cobertura de decoradores em estágios ainda não implementados.
- **Recomendação**: Exigir asserção de existência dos módulos declarados em `STAGE_MODULES`.

---

### ID: AUD-T0-003
- **Título**: Verificador `verify.py` reescreve `verify_result.json` dentro do diretório do run
- **Gravidade**: BAIXA
- **Estado**: CONFIRMADO
- **Contrato afetado**: Imutabilidade e garantia read-only da verificação.
- **Evidência**: `evidencias/09-verificador-readonly.txt`
- **Como reproduzir**: Calcular o hash SHA-256 do run, executar `verify.py` e recalcular os hashes.
- **Resultado observado**: `verify_result.json` é modificado durante a execução da verificação.
- **Resultado esperado**: O verificador deve operar em modo puramente read-only ou salvar resultados em diretório de saída separado.
- **Impacto**: Modificação pontual de timestamp/resultado no artefato do run verificado.
- **Recomendação**: Permitir parâmetro de saída isolado para relatórios de verificação.

---

## 5. Veredito Independente

**Veredito**: **`APTA_PARA_REVISAO_HUMANA`**

A suíte de testes e a verificação de mutação do pacote T0 estão 100% operacionais e verdes (462/462 testes). No entanto, o pacote apresenta 3 achados formais (AUD-T0-001 a AUD-T0-003) relativos ao alcance do scanner AST e à disciplina de branches. A decisão de prosseguir para T1 cabe exclusivamente ao revisor humano após avaliar a recomendação de expansão do scanner AST.
