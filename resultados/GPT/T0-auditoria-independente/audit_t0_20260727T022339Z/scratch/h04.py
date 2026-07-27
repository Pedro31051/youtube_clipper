"""H04 — O verificador modifica estado ou grava no run errado.

Correção do FISC-GPT-002: o run anterior executou ``cortes.verify`` DIRETAMENTE
contra ``review/T0/runs/run_t0_golden``, alterando a área oficial que o plano
proíbe tocar. Aqui o verificador só é executado sobre CÓPIA ISOLADA em /tmp, e
a integridade da área oficial é medida por hash antes e depois.

Medições:
  H04.1 hash de toda a área review/T0 antes;
  H04.2 hash da cópia + árvore do diretório de trabalho antes;
  H04.3 execução do verificador sobre a cópia;
  H04.4 hash/árvore depois: arquivos criados, modificados, apagados,
        runs colaterais criados no CWD e dependência de CORTES_RUN_ID;
  H04.5 hash da área review/T0 depois + git status, provando que a área
        oficial permaneceu intacta durante esta auditoria.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
PKG_RUN = REPO / "review" / "T0" / "runs" / "run_t0_golden"
OFICIAL = REPO / "review" / "T0"
PY = str(REPO / ".venv" / "bin" / "python")


def tree_hashes(root: pathlib.Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def tree_list(root: pathlib.Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")} if root.exists() else set()


print("== H04.1 — impressão digital da área oficial review/T0 ANTES ==")
oficial_antes = tree_hashes(OFICIAL)
print(f"  arquivos: {len(oficial_antes)}")
for k in sorted(oficial_antes):
    print(f"    {oficial_antes[k]}  {k}")

tmp = pathlib.Path(tempfile.mkdtemp(prefix="h04_"))
sandbox = tmp / "cwd_sandbox"
sandbox.mkdir()
copia = tmp / "run_t0_golden"
shutil.copytree(PKG_RUN, copia)

print()
print("== H04.2 — estado da CÓPIA e do CWD antes ==")
copia_antes = tree_hashes(copia)
cwd_antes = tree_list(sandbox)
print(f"  arquivos na cópia: {len(copia_antes)}")
print(f"  entradas no CWD do verificador: {len(cwd_antes)} -> {sorted(cwd_antes)}")
print(f"  CORTES_RUN_ID definido no ambiente? {'CORTES_RUN_ID' in os.environ}")

print()
print("== H04.3 — execução do verificador sobre a cópia isolada ==")
res = subprocess.run(
    [PY, "-m", "cortes.verify", str(copia)],
    cwd=str(sandbox), capture_output=True, text=True,
    env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
         "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(sandbox)},
)
print(f"  comando: python -m cortes.verify <copia>   (cwd={sandbox})")
print(f"  exit_code={res.returncode}")
print(f"  stderr={res.stderr.strip()[:300] or '<vazio>'}")

print()
print("== H04.4 — efeitos colaterais medidos ==")
copia_depois = tree_hashes(copia)
cwd_depois = tree_list(sandbox)

criados = sorted(set(copia_depois) - set(copia_antes))
apagados = sorted(set(copia_antes) - set(copia_depois))
modificados = sorted(k for k in copia_antes if k in copia_depois and copia_antes[k] != copia_depois[k])

print(f"  DENTRO do run verificado:")
print(f"    criados     ({len(criados)}): {criados}")
print(f"    modificados ({len(modificados)}): {modificados}")
print(f"    apagados    ({len(apagados)}): {apagados}")
for k in modificados:
    print(f"      {k}: {copia_antes[k][:16]}... -> {copia_depois[k][:16]}...")

colaterais = sorted(cwd_depois - cwd_antes)
print(f"  FORA do run verificado, no diretório de trabalho ({len(colaterais)}):")
for c in colaterais:
    print(f"    {c}")
runs_colaterais = [c for c in colaterais if c.startswith("runs/") and c.count("/") == 1]
print(f"    -> runs colaterais criados pelo próprio verificador: {runs_colaterais}")
for rc in runs_colaterais:
    ev = sandbox / rc / "events.jsonl"
    if ev.exists():
        linhas = [l for l in ev.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"       {rc}/events.jsonl -> {len(linhas)} eventos gravados pelo verificador")

readonly = not criados and not modificados and not apagados and not colaterais
print(f"  H04_VERIFICADOR_READONLY={readonly}")

print()
print("== H04.5 — a área oficial review/T0 permaneceu intacta? ==")
oficial_depois = tree_hashes(OFICIAL)
iguais = oficial_antes == oficial_depois
print(f"  hashes idênticos antes/depois: {iguais}")
if not iguais:
    for k in sorted(set(oficial_antes) | set(oficial_depois)):
        if oficial_antes.get(k) != oficial_depois.get(k):
            print(f"    DIVERGE: {k}")
gs = subprocess.run(["git", "status", "--short", "review/", "runs/"],
                    cwd=str(REPO), capture_output=True, text=True)
print(f"  git status --short review/ runs/ ->\n{gs.stdout or '    <limpo>'}")

shutil.rmtree(tmp, ignore_errors=True)
print()
print(f"H04_ESTADO={'CONFIRMADA' if not readonly else 'REFUTADA'}")
print(f"H04_AREA_OFICIAL_PRESERVADA={iguais}")
