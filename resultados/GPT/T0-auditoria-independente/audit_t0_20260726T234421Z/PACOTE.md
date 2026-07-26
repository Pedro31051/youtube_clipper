# Pacote de Auditoria Independente T0

- **Baseline**: `fbe8cc5462537dbcaa44ddf6c9182ac218b22c25`
- **Branch**: `agent/auditoria-independente-t0`
- **Run ID**: `audit_t0_20260726T234421Z`
- **Área**: `resultados/GPT/T0-auditoria-independente/audit_t0_20260726T234421Z/`

## Conteúdo do Pacote

- `PACOTE.md`: Resumo e instruções do pacote de auditoria.
- `RELATORIO.md`: Relatório completo de auditoria com metodologia, tabela de hipóteses e achados.
- `VEREDITO.json`: Veredito estruturado em JSON v1.0.
- `LIMITACOES.md`: Declaração de limitações técnicas da auditoria.
- `HIPOTESES.csv`: Tabela detalhada de confirmação/refutação de hipóteses.
- `INVENTARIO.txt`: Lista e hashes SHA-256 de todos os arquivos do pacote T0 baseline.
- `COMANDOS.jsonl`: Log estruturado de cada comando executado na auditoria com timestamps UTC, duração e código de saída.
- `MANIFESTO_SHA256.txt`: Hashes SHA-256 de integridade final de todo o pacote.
- `evidencias/`: 14 arquivos de provas e saídas de comandos (00 a 13 + pytest.xml).

## Instruções para Reprodução

1. Checkout na branch `agent/auditoria-independente-t0`.
2. Rodar a reprodução dos testes:
   ```bash
   .venv/bin/python -m pytest tests/ -v
   .venv/bin/python -m pytest tests/test_contracts.py -v
   .venv/bin/python -m pytest tests/test_mutation.py -v
   ```
3. Verificar a integridade dos arquivos usando o manifesto:
   ```bash
   cd resultados/GPT/T0-auditoria-independente/audit_t0_20260726T234421Z && sha256sum -c MANIFESTO_SHA256.txt
   ```
