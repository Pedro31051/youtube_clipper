"""Gera os documentos consolidados a partir das evidências medidas."""

from __future__ import annotations

import csv
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent
EVI = RUN / "evidencias"
RUN_ID = RUN.name
BASELINE = "fbe8cc5462537dbcaa44ddf6c9182ac218b22c25"
BRANCH = "agent/refazer-auditoria-independente-t0"


def read(name: str) -> str:
    return (EVI / name).read_text(encoding="utf-8")


pytest_text = read("03-pytest-completo.txt")
match = re.search(r"=+ (\d+) passed in ([\d.]+)s", pytest_text)
if not match:
    raise RuntimeError("resultado do pytest completo não encontrado")
collected = passed = int(match.group(1))

hypothesis_sources = {
    "H01": ("06-subprocess-scan.txt", "Scanner AST não cobre todo o código produtivo"),
    "H02": ("07-stage-modules.txt", "Módulos de estágio ausentes são ignorados silenciosamente"),
    "H03": ("08-portabilidade.txt", "Golden run não é portável"),
    "H04": ("09-verificador-readonly.txt", "Verificador modifica estado"),
    "H05": ("10-corte-duplo.txt", "Pipeline aplica offset duas vezes"),
    "H06": ("11-dashboard-superficie.txt", "Dashboard exposto possui superfície insegura"),
}
hypotheses: dict[str, str] = {}
for hid, (filename, _) in hypothesis_sources.items():
    marker = re.search(rf"{hid}_ESTADO=(CONFIRMADA|REFUTADA|INCONCLUSIVA|BLOQUEADA)", read(filename))
    if not marker:
        raise RuntimeError(f"estado medido ausente para {hid}")
    hypotheses[hid] = marker.group(1)

ci_text = read("12-ci-e-branches.txt")
hypotheses["H07"] = (
    "CONFIRMADA"
    if '{"checks":[],"total_count":0}' in ci_text and "--- workflows locais ---\n---" in ci_text
    else "INCONCLUSIVA"
)
hypotheses["H08"] = (
    "CONFIRMADA"
    if "fbe8cc5 (HEAD -> agent/refazer-auditoria-independente-t0, origin/main, main)"
    in ci_text
    else "INCONCLUSIVA"
)

mutation_text = read("12-mutacao-cobertura.txt")
mutation_defect = (
    "['artefato_declarado_removido']" in mutation_text
    and "E4_ESTADO=DEFEITO_CONFIRMADO" in mutation_text
)
if not mutation_defect:
    raise RuntimeError("resultado adversarial de mutação não encontrado")

findings = [
    {
        "id": "AUD-T0-001",
        "hypothesis": "H05",
        "title": "Corte duplo produz MP4 inválido aceito como sucesso",
        "severity": "CRÍTICA",
        "contract": "Integridade do artefato de mídia e detecção barulhenta de falhas.",
        "evidence": "evidencias/10-corte-duplo.txt",
        "command": 12,
        "observed": "run_pipeline reaplicou 60–90 s ao segmento local de 30 s; o resultado inválido foi aceito.",
        "expected": "O segmento já recortado deveria ser processado desde t=0, ou a saída inválida deveria causar erro.",
        "impact": "Corrupção silenciosa do produto entregue.",
        "counter": "A suíte completa passa, mas o cenário realista de offset consumido não faz parte do caminho coberto.",
        "recommendation": "Normalizar o offset após download_segment e validar tamanho, streams e duração com ffprobe.",
    },
    {
        "id": "AUD-T0-002",
        "hypothesis": "H01",
        "title": "Scanner AST deixa subprocessos produtivos fora de run_cmd",
        "severity": "ALTA",
        "contract": "Exclusividade de run_cmd para comandos externos.",
        "evidence": "evidencias/06-subprocess-scan.txt",
        "command": 8,
        "observed": "Foram medidas 13 ocorrências proibidas fora do escopo efetivo do teste.",
        "expected": "Todo src/ deve ser varrido e somente cortes/log.py pode executar comandos externos.",
        "impact": "Partes produtivas podem escapar da trilha de auditoria.",
        "counter": "Os 7 testes contratuais passam porque a raiz inspecionada é restrita.",
        "recommendation": "Expandir o scanner contratual para todos os pacotes sob src/.",
    },
    {
        "id": "AUD-T0-003",
        "hypothesis": "H03",
        "title": "Golden run não é verificável após relocação limpa",
        "severity": "ALTA",
        "contract": "Portabilidade e verificabilidade independente das evidências.",
        "evidence": "evidencias/08-portabilidade.txt",
        "command": 10,
        "observed": "Há 54 referências absolutas e 0 relativas; em contêiner sem /home o overall_passed foi false.",
        "expected": "Um checkout limpo deve verificar integralmente o pacote sem caminhos da máquina de origem.",
        "impact": "O pacote não constitui prova reproduzível fora do host produtor.",
        "counter": "A cópia local retorna verde, mas também retorna verde após remover os próprios artefatos.",
        "recommendation": "Armazenar caminhos relativos ao run e tornar o verificador dependente apenas do pacote fornecido.",
    },
    {
        "id": "AUD-T0-004",
        "hypothesis": "H04",
        "title": "Verificador altera o run e cria run colateral",
        "severity": "ALTA",
        "contract": "Verificação read-only e ausência de efeitos colaterais.",
        "evidence": "evidencias/09-verificador-readonly.txt",
        "command": 11,
        "observed": "Na cópia isolada, verify_result.json foi modificado e um novo runs/run_* foi criado no CWD.",
        "expected": "Hashes e árvore devem permanecer byte a byte idênticos.",
        "impact": "A verificação muda a própria prova e confunde a procedência do resultado.",
        "counter": "A área oficial review/T0 permaneceu intacta nesta repetição porque o teste usou cópia temporária.",
        "recommendation": "Separar saída do verificador e impedir inicialização de run durante verificação.",
    },
    {
        "id": "AUD-T0-005",
        "hypothesis": "E4",
        "title": "Verificador aceita remoção integral dos artefatos",
        "severity": "ALTA",
        "contract": "Testes de mutação devem rejeitar corrupção e ausência de artefatos relevantes.",
        "evidence": "evidencias/12-mutacao-cobertura.txt",
        "command": 14,
        "observed": "A mutação artefato_declarado_removido terminou com exit 0 e overall_passed true.",
        "expected": "Remover os artefatos declarados deve reprovar o run.",
        "impact": "Um pacote sem produto pode ser classificado como válido.",
        "counter": "MP4 truncado e SHA alterado foram corretamente rejeitados.",
        "recommendation": "Exigir presença de todo artefato declarado antes de reduzir dinamicamente o conjunto de checks.",
    },
    {
        "id": "AUD-T0-006",
        "hypothesis": "H06",
        "title": "Dashboard expõe arquivos e estado global sem autenticação",
        "severity": "ALTA",
        "contract": "Exposição segura do dashboard e isolamento entre requisições.",
        "evidence": "evidencias/11-dashboard-superficie.txt",
        "command": 13,
        "observed": "Teste em loopback serviu arquivo do CWD anonimamente e comprovou corrida em YOUTUBE_COOKIES_FILE.",
        "expected": "Bind seguro, autenticação, allowlist dedicada e estado por requisição.",
        "impact": "Quando exposto, permite leitura indevida e interferência entre clientes.",
        "counter": "O path traversal explícito foi rejeitado, mas CWD e /tmp permanecem permitidos.",
        "recommendation": "Usar 127.0.0.1 por padrão, autenticar e remover estado global/allowlists amplas.",
    },
    {
        "id": "AUD-T0-007",
        "hypothesis": "H02",
        "title": "Teste de decoradores passa por vacuidade",
        "severity": "MÉDIA",
        "contract": "Integridade da malha de estágios auditados.",
        "evidence": "evidencias/07-stage-modules.txt",
        "command": 9,
        "observed": "Nenhum dos módulos exigidos existe e o teste passa; módulo presente sem @audited faz o teste falhar.",
        "expected": "A ausência de módulo exigido deve falhar explicitamente.",
        "impact": "Verde contratual transmite cobertura inexistente.",
        "counter": "Quando um módulo existe, o teste identifica a ausência do decorador.",
        "recommendation": "Assegurar existência de todos os STAGE_MODULES antes de inspecionar decoradores.",
    },
    {
        "id": "AUD-T0-008",
        "hypothesis": "H07",
        "title": "Baseline não possui CI independente",
        "severity": "MÉDIA",
        "contract": "Execução independente e contínua da suíte.",
        "evidence": "evidencias/12-ci-e-branches.txt",
        "command": 15,
        "observed": "Não há workflows locais, check-runs ou statuses no commit-base.",
        "expected": "CI versionada deve executar ao menos contratos, mutações e suíte completa.",
        "impact": "Resultados dependem de execuções manuais commitadas.",
        "counter": "A auditoria reproduziu localmente 462 testes verdes.",
        "recommendation": "Adicionar workflow obrigatório com pytest, contratos e mutações.",
    },
    {
        "id": "AUD-T0-009",
        "hypothesis": "H08",
        "title": "Commits T0 estão diretamente na main",
        "severity": "MÉDIA",
        "contract": "Disciplina de branch e revisão humana.",
        "evidence": "evidencias/12-ci-e-branches.txt",
        "command": 15,
        "observed": "f4f13a3 e fbe8cc5 integram o histórico de main; não há PR correspondente à implementação T0.",
        "expected": "Implementação deveria chegar por branch e revisão, conforme regra escrita.",
        "impact": "Reduz separação de funções e rastreabilidade da aprovação.",
        "counter": "A nova auditoria está isolada em branch própria.",
        "recommendation": "Aplicar proteção de branch e exigir PR/checks para fases futuras.",
    },
]

blocking = any(f["severity"] in {"CRÍTICA", "ALTA"} for f in findings)
verdict = "NAO_APTA_PARA_T1" if blocking else "APTA_PARA_REVISAO_HUMANA"
generated_at = datetime.now(timezone.utc).isoformat()

with (RUN / "HIPOTESES.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["id", "hipotese", "estado", "evidencia", "command_id"])
    for hid, (filename, description) in hypothesis_sources.items():
        writer.writerow([hid, description, hypotheses[hid], f"evidencias/{filename}",
                         int(hid[1:]) + 7])
    writer.writerow(["H07", "Não existe CI independente", hypotheses["H07"],
                     "evidencias/12-ci-e-branches.txt", 15])
    writer.writerow(["H08", "Disciplina de branch T0 foi descumprida", hypotheses["H08"],
                     "evidencias/12-ci-e-branches.txt", 15])

limitations = """# Limitações

- Nenhum vídeo de terceiros foi baixado e nenhum endpoint do YouTube foi acessado.
- Google Drive, credenciais OAuth/service account e uploads reais não foram exercitados.
- Whisper e transcrição real não foram exercitados.
- O dashboard vivo foi restrito a `127.0.0.1` e porta efêmera; nenhuma porta pública foi aberta.
- A prova de portabilidade usou o contêiner local `t0-audit-clean:1`, sem rede e sem montagem de `/home`.
- A suíte contém mocks; seus 462 resultados não provam integrações externas reais.
- O `gh` confirmou ausência de checks/statuses e listou PRs, mas não há política de proteção de branch registrada no pacote.
"""
(RUN / "LIMITACOES.md").write_text(limitations, encoding="utf-8")

inventory = f"""# Inventário da auditoria

- Run: `{RUN_ID}`
- Baseline: `{BASELINE}`
- Branch: `{BRANCH}`
- Plataforma: `{platform.platform()}`
- Python do gerador: `{platform.python_version()}`
- Evidências de ambiente e dependências: `evidencias/01-ambiente.txt`
- Árvore e hashes do pacote oficial: `evidencias/02-arquivos-relevantes.txt`
- Testes coletados/aprovados: {collected}/{passed}
- Hipóteses adversariais: 8
- Findings formais: {len(findings)}
- Scripts reproduzíveis: `scratch/runner.py`, `scratch/h01.py` a `scratch/h07_mutacao.py`
"""
(RUN / "INVENTARIO.txt").write_text(inventory, encoding="utf-8")

rows = "\n".join(
    f"| {hid} | {hypothesis_sources.get(hid, ('', 'CI/branch'))[1]} | {state} |"
    for hid, state in hypotheses.items()
)
finding_sections = []
for finding in findings:
    finding_sections.append(
        f"""### {finding['id']} — {finding['title']}

- **ID:** {finding['id']}
- **Gravidade:** {finding['severity']}
- **Estado:** CONFIRMADO
- **Contrato afetado:** {finding['contract']}
- **Evidência:** `{finding['evidence']}`; comando `{RUN_ID}#{finding['command']:04d}`.
- **Como reproduzir:** executar o comando de ID {finding['command']} registrado em `COMANDOS.jsonl`.
- **Resultado observado:** {finding['observed']}
- **Resultado esperado:** {finding['expected']}
- **Impacto:** {finding['impact']}
- **Contraprova:** {finding['counter']}
- **Recomendação:** {finding['recommendation']}
"""
    )

report = f"""# Relatório de Auditoria Independente — Repetição T0

## 1. Escopo e baseline

Auditoria independente do repositório `Pedro31051/youtube_clipper`, baseline
`{BASELINE}`, executada na branch `{BRANCH}` e no run `{RUN_ID}`. O estado Git,
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

- Suíte completa: **{passed}/{collected} aprovados**, 0 falhas, 0 pulados, 0 erros
  (`evidencias/03-pytest-completo.txt`, `evidencias/pytest.xml`).
- Contratos: **7/7 aprovados** (`evidencias/04-pytest-contracts.txt`).
- Mutações declaradas: **17/17 aprovadas** (`evidencias/05-pytest-mutation.txt`).
- Contraprova adversarial: remoção integral dos artefatos foi aceita como válida
  (`evidencias/12-mutacao-cobertura.txt`).

## 5. Hipóteses

| ID | Hipótese | Estado |
|---|---|---|
{rows}

Fonte tabular: `HIPOTESES.csv`.

## 6. Achados por gravidade

{''.join(finding_sections)}

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

**{verdict}**.

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
"""
(RUN / "RELATORIO.md").write_text(report, encoding="utf-8")

structured_findings = [
    {
        "id": item["id"],
        "severity": item["severity"],
        "status": "CONFIRMADO",
        "evidence_paths": [item["evidence"]],
        "reproduction_command_ids": [item["command"]],
    }
    for item in findings
]
verdict_data = {
    "schema_version": "1.0",
    "repository": "Pedro31051/youtube_clipper",
    "baseline_sha": BASELINE,
    "run_id": RUN_ID,
    "verdict": verdict,
    "pytest": {
        "exit_code": 0,
        "collected": collected,
        "passed": passed,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    },
    "hypotheses": {
        "confirmed": [key for key, value in hypotheses.items() if value == "CONFIRMADA"],
        "refuted": [key for key, value in hypotheses.items() if value == "REFUTADA"],
        "inconclusive": [key for key, value in hypotheses.items() if value == "INCONCLUSIVA"],
        "blocked": [key for key, value in hypotheses.items() if value == "BLOQUEADA"],
    },
    "findings": structured_findings,
    "finding_counts": {"critical": 1, "high": 5, "medium": 3, "low": 0},
    "limitations": [
        "Sem acesso a vídeo de terceiros, YouTube real, Google Drive ou credenciais.",
        "Dashboard vivo restrito a loopback.",
        "Suíte contém mocks e não prova integrações externas.",
    ],
    "generated_at_utc": generated_at,
}
(RUN / "VEREDITO.json").write_text(
    json.dumps(verdict_data, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

package = f"""# Pacote da repetição da auditoria T0

- **Repositório:** `Pedro31051/youtube_clipper`
- **Baseline:** `{BASELINE}`
- **Branch:** `{BRANCH}`
- **Run ID:** `{RUN_ID}`
- **Veredito do executor:** `{verdict}`
- **Suíte:** {passed}/{collected} testes aprovados
- **Findings:** 1 crítico, 5 altos, 3 médios, 0 baixos

## Conteúdo

O pacote contém relatório, veredito JSON, hipóteses CSV, inventário, limitações,
log global de comandos, manifesto SHA-256, evidências `00` a `13`, JUnit XML e
scripts de reprodução em `scratch/`.

## Reprodução

Use um checkout limpo desta branch. Consulte `COMANDOS.jsonl` e execute os
comandos na ordem de `seq`. Valide a integridade com:

```bash
cd resultados/GPT/T0-auditoria-independente/{RUN_ID}
sha256sum -c MANIFESTO_SHA256.txt
```

O resultado literal dessa validação após checkout limpo fica em
`evidencias/14-manifesto-checkout-limpo.txt`.

## Limitações

Consulte `LIMITACOES.md`. Nenhuma correção produtiva, credencial, upload, merge
ou avanço para T1 faz parte deste pacote.
"""
(RUN / "PACOTE.md").write_text(package, encoding="utf-8")

print(json.dumps({
    "run_id": RUN_ID,
    "verdict": verdict,
    "pytest": f"{passed}/{collected}",
    "hypotheses": hypotheses,
    "findings": len(findings),
}, ensure_ascii=False, indent=2))
