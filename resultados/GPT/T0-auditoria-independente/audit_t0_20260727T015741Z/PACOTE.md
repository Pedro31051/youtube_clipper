# Pacote de Auditoria Independente T0 — run corrigido

- **Baseline auditada**: `fbe8cc5462537dbcaa44ddf6c9182ac218b22c25`
- **HEAD da branch no início do run**: `4ffe6f4f5220654d7e315e5a5c893a749a43f721`
- **Branch**: `agent/auditoria-independente-t0`
- **Run ID**: `audit_t0_20260727T015741Z`
- **Substitui**: `audit_t0_20260726T234421Z` (reprovado pelo Parecer de
  Fiscalização ChatGPT). O run reprovado **permanece preservado e intacto**;
  nenhum de seus 29 arquivos foi editado, movido ou apagado.
- **Área**: `resultados/GPT/T0-auditoria-independente/audit_t0_20260727T015741Z/`
- **Veredito**: `NAO_APTA_PARA_T1`

## Conteúdo

| Arquivo | Conteúdo |
|---|---|
| `PACOTE.md` | este resumo e as instruções de reprodução |
| `RELATORIO.md` | relatório completo: escopo, método, hipóteses, 11 achados, portões, contraprovas, veredito |
| `VEREDITO.json` | veredito estruturado, findings e portões acionados |
| `CORRECOES_FISCALIZACAO.md` | resposta ponto a ponto a FISC-GPT-001..009 |
| `HIPOTESES.csv` | tabela de hipóteses com método e comando de reprodução |
| `LIMITACOES.md` | limitações declaradas |
| `INVENTARIO.txt` | ambiente, baseline, dependências e hashes de todos os arquivos relevantes |
| `COMANDOS.jsonl` | 24 comandos, sequência global contínua, `cmd_uid` único |
| `MANIFESTO_SHA256.txt` | hashes do pacote, gerado a partir do índice do Git |
| `evidencias/` | saídas literais; `<slot>.txt` = stdout, `<slot>.stderr.txt` = stderr |
| `scratch/` | `runner.py` e os scripts de hipótese `h01`–`h06`, `h07_mutacao` |

### Convenção das evidências

- `NN-nome.txt` contém **exclusivamente o stdout literal** do comando.
- `NN-nome.stderr.txt` contém **exclusivamente o stderr literal**.
- Nenhum cabeçalho é inserido e nada é mesclado ou editado.
- Tentativas repetidas do mesmo slot recebem sufixo `.att2`, `.att3`, …
  **Nenhuma evidência é sobrescrita**: o runner abre os arquivos em modo `"x"`.
- A tentativa `#0015` terminou com exit 1 e está preservada com seu stderr.

## Resumo das execuções

| Execução | Resultado |
|---|---|
| `pytest tests/` | 462 coletados, 462 aprovados, exit 0, 109,98 s |
| `pytest tests/test_contracts.py` | 7/7, exit 0 |
| `pytest tests/test_mutation.py` | 17/17, exit 0 |
| H01 scanner AST | 13 ocorrências proibidas fora do escopo do teste |
| H02 módulos de estágio | 0/9 existem; verde por vacuidade comprovado |
| H03 portabilidade | 54 caminhos absolutos; 11/14 em máquina limpa |
| H04 verificador | não read-only; run colateral criado no CWD |
| H05 corte duplo | MP4 de 262 B, 0 streams, 0,000 s aceito como sucesso |
| H06 dashboard | sem autenticação; leitura de arquivos e upload arbitrário |
| H07 CI | 0 workflows, 0 check-runs |
| H08 branch | commits T0 em `main` |
| Etapa 4 mutação | 14/14 checks cobertos; remoção de artefatos aprovada |

## Limitações

Ver `LIMITACOES.md`. Em resumo: nenhum acesso ao YouTube, nenhuma credencial
lida, nenhum envio ao Google Drive, dashboard apenas em loopback, máquina limpa
emulada por contêiner local, e nenhuma correção de código implementada.

## Instruções de reprodução

```bash
git checkout agent/auditoria-independente-t0
cd resultados/GPT/T0-auditoria-independente/audit_t0_20260727T015741Z

# 1. Integridade do pacote (o manifesto cobre apenas arquivos versionados)
sha256sum -c MANIFESTO_SHA256.txt

# 2. Suíte declarada, a partir da raiz do repositório
cd ../../../..
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m pytest tests/test_contracts.py -v
.venv/bin/python -m pytest tests/test_mutation.py -v

# 3. Hipóteses adversariais (cada script imprime seu próprio estado)
D=resultados/GPT/T0-auditoria-independente/audit_t0_20260727T015741Z
.venv/bin/python $D/scratch/h01.py          # H01 — escopo do scanner AST
.venv/bin/python $D/scratch/h02.py          # H02 — módulos de estágio
.venv/bin/python $D/scratch/h03.py          # H03 — portabilidade (requer Docker)
.venv/bin/python $D/scratch/h04.py          # H04 — verificador read-only
.venv/bin/python $D/scratch/h05.py          # H05 — corte duplo (requer ffmpeg)
.venv/bin/python $D/scratch/h06.py          # H06 — superfície do dashboard
.venv/bin/python $D/scratch/h07_mutacao.py  # Etapa 4 — testes de mutação
```

O script `h03.py` usa a imagem `t0-audit-clean:1`, construída a partir de
`python:3.12-slim` com `ffmpeg` e `git`. Sem Docker, as camadas H03.1 a H03.3
ainda rodam, e a prova de controle — destruir os artefatos da cópia relocada e
observar que a verificação continua aprovando — já é suficiente para o achado.

Todos os scripts trabalham sobre cópias em `/tmp`. **Nenhum deles escreve em
`review/T0/`, em `src/`, em `tests/` ou em `runs/`.**

## Ordem de gravação no Git

O pacote foi gravado em dois commits, por uma razão de método:

1. **Commit A** — o pacote e o `MANIFESTO_SHA256.txt`, gerado a partir do
   índice do Git para conter apenas arquivos efetivamente versionados
   (correção de FISC-GPT-003).
2. **Commit B** — a validação do manifesto em **checkout limpo**, que só pode
   existir depois do commit A, mais o manifesto-adendo que cobre esses
   arquivos. Ver `evidencias/15-manifesto-checkout-limpo.txt` e
   `MANIFESTO_ADENDO_SHA256.txt`.

Nenhuma evidência do commit A foi alterada pelo commit B; o commit B apenas
acrescenta arquivos. A branch não foi mesclada e nenhum PR pronto para merge
foi aberto.

## Observação sobre o diretório de trabalho

No momento da gravação existia, sem relação com esta auditoria, o diretório
não versionado `resultados/GPT/T0-auditoria-independente/audit_t0_20260727T021704Z/`,
criado por outro processo em execução paralela na mesma máquina. Ele **não foi
tocado nem incluído** neste commit, que adiciona explicitamente apenas o
diretório deste run.
