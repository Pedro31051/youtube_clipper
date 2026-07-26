# Pacote de Revisão — Fase T0 (Remediação da Iteração 1)

- **Fase**: T0 — Fundação de Evidência & Auditabilidade Zero-Trust (Remediação Iteração 1)
- **Branch**: `main`
- **Commit**: `f4f13a34df1067678a36602336881774023b4d8a`
- **Data/Hora**: 2026-07-26T22:54:00Z
- **Autor**: Worker T0_3

---

## 1. Visão Geral do Pacote Remediado

Este pacote consolida a remediação da **Fase T0**, corrigindo integralmente todas as vulnerabilidades apontadas nos relatórios do Challenger (`challenger_t0_1`) e Auditor:
1. **Refatoração AST em `tests/test_contracts.py`**: Varredura expandida para proibir `os.system`, `os.popen`, `os.posix_spawn`, `importlib.import_module("subprocess")`, `__import__("subprocess")`, `eval`, `exec`, `asyncio.create_subprocess_exec`, `asyncio.create_subprocess_shell`. Verificação de `@audited` em 100% das funções (incluindo as iniciadas por `_`).
2. **Refatoração de `src/cortes/log.py`**: Cálculo determinístico de `seq` ignorando linhas em branco (`seq = len([l for l in lines if l.strip()]) + 1`).
3. **Refatoração de `src/cortes/verify.py`**: Comparação de timestamps ISO com `datetime.fromisoformat` (suporte a `Z` e `+00:00`), verificação de ordem lógica de estágios (DAG do pipeline) e ignorar linhas em branco em `events.jsonl`.
4. **Expansão de `tests/test_mutation.py`**: 17 testes de mutação sintética cobrindo 100% das 14 checagens do `verify.py`.

---

## 2. Conteúdo do Pacote (`review/T0/`)

| Arquivo / Diretório | Descrição |
|---|---|
| `PACOTE.md` | Índice geral com metadados do commit, branch, resumo de alterações remediadas. |
| `runs/run_t0_golden/` | Execução golden autêntica completa contendo `events.jsonl`, `commands.log`, artefatos de evidência, `verify_result.json` e `report.md`. |
| `diff.patch` | Patch `git diff` completo das alterações introduzidas na Fase T0. |
| `files_changed.txt` | Lista detalhada de arquivos com hashes SHA-256 e tamanhos. |
| `verify_result.json` | Cópia consolidada do resultado de verificação zero-trust (14/14 checks aprovados). |
| `report.md` | Cópia consolidada do relatório determinístico gerado a partir do run golden. |
| `DECISOES.md` | Registro de decisões técnicas e correções de arquitetura. |
| `LIMITACOES.md` | Limitações conhecidas para a Fase T1. |
| `CRITICA_INTERNA.md` | Resumo consolidado de críticas internas e remediações. |
