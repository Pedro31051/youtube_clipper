"""H03 — As evidências do golden run não são portáveis.

Correção do FISC-GPT-008: o run anterior copiou o golden run para /tmp mantendo
a máquina original intacta e concluiu "14/14 verde" — resultado que nada prova,
porque o verificador podia continuar lendo os artefatos originais.

Aqui a dependência é medida diretamente, em quatro camadas:

  H03.1 inventário de caminhos absolutos x relativos;
  H03.2 procedência: para onde os caminhos declarados apontam e se esses
        artefatos estão sequer versionados no Git;
  H03.3 relocação + PROVA DE CONTROLE: com o run copiado para /tmp, os
        artefatos DA CÓPIA são destruídos. Se o verificador continuar verde,
        está comprovado que ele nunca leu a cópia;
  H03.4 máquina limpa: clone fresco (só arquivos versionados) executado em
        contêiner sem acesso a /home, isto é, sem os caminhos originais.

Nenhum caminho é ajustado manualmente em nenhum momento.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
PKG_RUN = REPO / "review" / "T0" / "runs" / "run_t0_golden"
PY = str(REPO / ".venv" / "bin" / "python")
ABS_RE = re.compile(r"(/(?:home|tmp|var|opt|usr)/[^\s\"',\]]+)")


def run_verifier(run_dir: pathlib.Path, cwd: pathlib.Path) -> subprocess.CompletedProcess:
    """Executa o verificador exatamente como um revisor externo faria."""
    return subprocess.run(
        [PY, "-m", "cortes.verify", str(run_dir)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
             "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(cwd)},
    )


print("== H03.1 — inventário de caminhos no pacote oficial review/T0/runs/run_t0_golden ==")
absolutos, relativos = [], []
for fn in ("events.jsonl", "verify_result.json", "commands.log", "report.md"):
    fp = PKG_RUN / fn
    if not fp.exists():
        print(f"  [{fn}] AUSENTE")
        continue
    hits = ABS_RE.findall(fp.read_text(encoding="utf-8", errors="replace"))
    absolutos.extend((fn, h) for h in hits)
    print(f"  [{fn}] referências absolutas: {len(hits)}")
print(f"  TOTAL de referências absolutas: {len(absolutos)}")
print(f"  TOTAL de referências relativas ao próprio run: {len(relativos)}")

print()
print("== H03.2 — procedência dos artefatos declarados ==")
declared: list[str] = []
for line in (PKG_RUN / "events.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        declared.extend(json.loads(line).get("evidence", {}).get("paths", []))
declared_unicos = sorted(set(declared))
print(f"  caminhos de artefato declarados (únicos): {len(declared_unicos)}")
dentro_pacote = 0
for p in declared_unicos:
    pp = pathlib.Path(p)
    no_pacote = str(pp).startswith(str(PKG_RUN))
    dentro_pacote += int(no_pacote)
    try:
        rel = pp.relative_to(REPO)
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(rel)],
                                 cwd=str(REPO), capture_output=True, text=True).returncode == 0
    except ValueError:
        rel, tracked = pp, False
    print(f"    {p}")
    print(f"      absoluto={pp.is_absolute()}  dentro_do_pacote_review={no_pacote}  "
          f"existe_agora={pp.exists()}  versionado_no_git={tracked}")
print(f"  artefatos declarados que apontam para dentro do pacote oficial: "
      f"{dentro_pacote}/{len(declared_unicos)}")

print()
print("== H03.3 — relocação com PROVA DE CONTROLE ==")
tmp = pathlib.Path(tempfile.mkdtemp(prefix="h03_"))
sandbox = tmp / "sandbox"
sandbox.mkdir()

cenarios = {}

# (a) cópia íntegra
copia_a = tmp / "a_intacta" / "run_t0_golden"
copia_a.parent.mkdir()
shutil.copytree(PKG_RUN, copia_a)
res_a = run_verifier(copia_a, sandbox)
print(f"  (a) cópia íntegra em {copia_a}")
print(f"      exit={res_a.returncode}")

# (b) MESMA cópia, artefatos da cópia destruídos
copia_b = tmp / "b_artefatos_destruidos" / "run_t0_golden"
copia_b.parent.mkdir()
shutil.copytree(PKG_RUN, copia_b)
shutil.rmtree(copia_b / "artifacts")
(copia_b / "artifacts_REMOVIDOS.txt").write_text("artefatos da cópia apagados\n", encoding="utf-8")
res_b = run_verifier(copia_b, sandbox)
print(f"  (b) cópia SEM os próprios artefatos em {copia_b}")
print(f"      exit={res_b.returncode}")

for rotulo, copia, res in (("a_intacta", copia_a, res_a), ("b_artefatos_destruidos", copia_b, res_b)):
    vr = copia / "verify_result.json"
    if vr.exists():
        data = json.loads(vr.read_text(encoding="utf-8"))
        fora = sum(
            1 for c in data["checks"]
            if c["evidence_path"].startswith("/") and not c["evidence_path"].startswith(str(copia))
        )
        cenarios[rotulo] = {
            "exit": res.returncode,
            "overall_passed": data["overall_passed"],
            "passed": f"{data['passed_checks']}/{data['total_checks']}",
            "checks_apontando_para_FORA_da_copia": f"{fora}/{data['total_checks']}",
        }
        print(f"\n  [{rotulo}] {json.dumps(cenarios[rotulo], ensure_ascii=False)}")
        for c in data["checks"]:
            local = "DENTRO-da-copia" if c["evidence_path"].startswith(str(copia)) else "FORA-da-copia"
            print(f"      {c['check_id']:<28} passed={str(c['passed']):<5} [{local}] {c['evidence_path']}")

print()
print("== H03.4 — máquina limpa: clone versionado, contêiner sem /home ==")
clone = tmp / "clone_limpo"
cl = subprocess.run(["git", "clone", "--quiet", "--branch", "agent/auditoria-independente-t0",
                     str(REPO), str(clone)], capture_output=True, text=True)
print(f"  git clone exit={cl.returncode} {cl.stderr.strip()[:200]}")
print(f"  artefatos presentes no clone (só versionados): "
      f"{sorted(p.name for p in (clone / 'review/T0/runs/run_t0_golden/artifacts').rglob('*') if p.is_file())}")
print(f"  runs/ existe no clone? {(clone / 'runs').exists()}  "
      f"(o caminho declarado nos eventos é <repo>/runs/run_t0_golden/...)")

(tmp / "ctr_out").mkdir(exist_ok=True)
docker = subprocess.run(
    ["docker", "run", "--rm", "--network", "none",
     "-v", f"{clone}:/audit:ro", "-v", f"{tmp / 'ctr_out'}:/out",
     "-w", "/out", "-e", "PYTHONPATH=/audit/src", "-e", "PYTHONDONTWRITEBYTECODE=1",
     "t0-audit-clean:1",
     "python3", "-c",
     "import json,shutil,pathlib,sys;"
     "shutil.copytree('/audit/review/T0/runs/run_t0_golden','/out/run_t0_golden');"
     "sys.path.insert(0,'/audit/src');"
     "from cortes.verify import verify_run;"
     "r=verify_run('/out/run_t0_golden');"
     "print(json.dumps({'overall_passed':r['overall_passed'],"
     "'passed':r['passed_checks'],'total':r['total_checks'],"
     "'falhas':[c['check_id']+' :: '+c['measured'] for c in r['checks'] if not c['passed']]},"
     "indent=2,ensure_ascii=False))"],
    capture_output=True, text=True,
)
print(f"  docker exit={docker.returncode}")
print("  --- saída do contêiner (máquina sem os caminhos originais) ---")
print("\n".join("  " + l for l in (docker.stdout or "").splitlines()))
if docker.stderr.strip():
    print("  --- stderr do contêiner ---")
    print("\n".join("  " + l for l in docker.stderr.splitlines()[-15:]))

print()
print("== H03 — síntese ==")
a = cenarios.get("a_intacta", {})
b = cenarios.get("b_artefatos_destruidos", {})
print(f"  cópia íntegra ...................... {a.get('passed')} overall={a.get('overall_passed')}")
print(f"  cópia com artefatos destruídos ..... {b.get('passed')} overall={b.get('overall_passed')}")
print(f"  checks apontando para fora da cópia. {a.get('checks_apontando_para_FORA_da_copia')}")
insensivel = a.get("overall_passed") is True and b.get("overall_passed") is True
print(f"  H03_VERIFICADOR_INSENSIVEL_A_DESTRUICAO_DA_COPIA={insensivel}")
maquina_limpa_falhou = docker.returncode != 0 or '"overall_passed": false' in docker.stdout.lower()
print(f"  H03_MAQUINA_LIMPA_FALHOU={maquina_limpa_falhou}")
print(f"H03_ESTADO={'CONFIRMADA' if insensivel else 'INCONCLUSIVA'}")
print(f"H03_SANDBOX={tmp}")
