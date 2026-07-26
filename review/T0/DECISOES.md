# Registro de Decisões Técnicas — Fase T0 (Remediado)

## Decisão 1: Fortalecimento de Varredura AST Anti-Evasão (`test_contracts.py`)
- **Decisão**: Expandir a análise estática AST para detectar acessos diretos, dinâmicos e disfarçados a subprocessos e comandos de sistema (`os.system`, `os.popen`, `os.posix_spawn`, `importlib.import_module("subprocess")`, `__import__("subprocess")`, `eval`, `exec`, `asyncio.create_subprocess_*`). Exigir o decorador `@audited` em todas as funções de estágio sem exceções de prefixo `_`.
- **Racional**: Elimina vetores de evasão de auditoria e garante controle estrito sobre a execução de comandos.

## Decisão 2: Comparação de Timestamps ISO via `datetime.fromisoformat` (`verify.py`)
- **Decisão**: Substituir comparações de string ASCII por parsing de datetime com fuso horário ISO 8601 (`datetime.fromisoformat`).
- **Racional**: Evita falhas falsas de monotonicidade decorrentes da diferença léxica entre sufixos `Z` e `+00:00`.

## Decisão 3: Verificação de Sequência e DAG do Pipeline (`verify.py`)
- **Decisão**: Validar a ordem cronológica e lógica das transições de estágio no `seq_integrity`.
- **Racional**: Assegura que execuções fora de ordem (ex: `render` antes de `ingest`) sejam rejeitadas pelo verificador zero-trust.

## Decisão 4: Cobertura Completa de Mutação Sintética (`test_mutation.py`)
- **Decisão**: Implementar 17 testes de mutação cobrindo a totalidade dos 14 checks de `verify.py`.
- **Racional**: Garante regressão zero e prova que cada verificação falha adequadamente quando corrompida.
