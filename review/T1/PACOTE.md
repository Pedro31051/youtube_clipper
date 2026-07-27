# Pacote de Revisão — Fase T1 (Ambiente)

- **Escopo canônico**: `ORIGINAL_REQUEST.md`, Fase T1 — Ambiente
- **Branch**: `agent/corrigir-pacote-t1`
- **Commit de implementação original**: `d782b61`
- **Commit corretivo**: `85161fd`
- **Run golden**: `run_t1_20260727T193302Z`
- **Run bloqueado histórico**: `run_t1_20260727T122944Z`
- **Estado submetido**: `PASSED`

## Resultado

A execução ambiental atende os 8/8 critérios na primeira tentativa. A
rechecagem ambiental read-only repetiu 8/8 e o verificador estrutural aprovou
10/10 checks de eventos, timestamps, comandos e evidências. A suíte completa
passou com 483 testes.

O falso negativo anterior de fontes foi corrigido: `grep` básico tratava `|`
como caractere literal; o check agora usa `grep -Eci` para expressar as três
alternativas documentadas. O espaço foi recuperado exclusivamente de caches e
temporários recriáveis, sem remover código ou evidências.

## Conteúdo

| Caminho | Finalidade |
|---|---|
| `runs/run_t1_20260727T193302Z/` | Run golden completo, aprovado em 8/8 |
| `runs/run_t1_20260727T122944Z/` | Run bloqueado anterior preservado como histórico |
| `diff.patch` | Diff de código exato de `origin/main...85161fd`, excluindo `review/T1/` |
| `files_changed.txt` | Inventário SHA-256 antes/depois do commit |
| `verify_result.json` | Consolidação determinística dos oito checks, 8/8 |
| `environment_reverify_result.json` | Rechecagem ambiental read-only, 8/8 |
| `integrity_verify_result.json` | Rechecagem estrutural do run, 10/10 |
| `pytest_full_results.xml` | Suíte completa, 483 testes aprovados |
| `PACKAGE_MANIFEST.sha256` | Integridade do pacote canônico e da run golden |
| `report.md` | Relatório gerado de eventos e resultado consolidado |
| `DECISOES.md` | Decisões e alternativas |
| `LIMITACOES.md` | Bloqueios e incertezas |
| `CRITICA_INTERNA.md` | Achados da revisão interna |

O pacote usa o rótulo `golden` apenas para a nova execução aprovada. A execução
bloqueada permanece imutável e explicitamente identificada como histórica.
