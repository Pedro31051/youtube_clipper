# Pacote de Revisão — Fase T1 (Ambiente)

- **Escopo canônico**: `ORIGINAL_REQUEST.md`, Fase T1 — Ambiente
- **Branch**: `agent/corrigir-pacote-t1`
- **Commit de implementação**: `d782b61`
- **Run preservado**: `run_t1_20260727T122944Z`
- **Estado submetido**: `BLOCKED`

## Resultado

A implementação do executor e do verificador T1 está coberta por testes, mas a
execução ambiental não atende 8/8 critérios. Seis checks passaram; fontes e
espaço em disco falharam duas vezes consecutivas. A execução foi interrompida
sem nova tentativa, conforme a regra da fase.

## Conteúdo

| Caminho | Finalidade |
|---|---|
| `runs/run_t1_20260727T122944Z/` | Run completo, incluindo falhas e instalações |
| `diff.patch` | Diff exato de `origin/main...d782b61` |
| `files_changed.txt` | Inventário SHA-256 antes/depois do commit |
| `verify_result.json` | Consolidação determinística dos oito checks |
| `integrity_verify_result.json` | Rechecagem estrutural do run |
| `report.md` | Relatório gerado de eventos e resultado consolidado |
| `DECISOES.md` | Decisões e alternativas |
| `LIMITACOES.md` | Bloqueios e incertezas |
| `CRITICA_INTERNA.md` | Achados da revisão interna |

Este pacote não usa o rótulo `golden`: a execução é deliberadamente preservada
como falha e não autoriza avanço para T2.
