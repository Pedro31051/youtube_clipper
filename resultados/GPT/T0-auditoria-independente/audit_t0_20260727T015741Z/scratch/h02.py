"""H02 — Módulos de estágio ausentes são ignorados silenciosamente.

Medição (não narrativa):
1. Lista STAGE_MODULES e prova quais existem em src/cortes/.
2. Localiza no AST do teste o ``continue`` que ignora módulo ausente.
3. Teste adversarial em CÓPIA TEMPORÁRIA (os testes versionados não são
   tocados), em três cenários:
   A) árvore como está hoje (nenhum módulo de estágio) -> teste passa?
   B) um módulo de estágio presente e SEM @audited          -> teste passa?
   C) um módulo de estágio presente e COM @audited          -> teste passa?
   Se A passa e B falha, o verde de hoje é vacuidade, não cobertura.
"""

from __future__ import annotations

import ast
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "tests"))
from test_contracts import STAGE_MODULES  # noqa: E402

print("== H02.1 — módulos de estágio exigidos x existentes ==")
cortes = REPO / "src" / "cortes"
existentes, ausentes = [], []
for m in STAGE_MODULES:
    (existentes if (cortes / f"{m}.py").exists() else ausentes).append(m)
print(f"  STAGE_MODULES declarados ({len(STAGE_MODULES)}): {STAGE_MODULES}")
print(f"  EXISTEM em src/cortes/ ({len(existentes)}): {existentes}")
print(f"  AUSENTES em src/cortes/ ({len(ausentes)}): {ausentes}")
print(f"  arquivos reais em src/cortes/: {sorted(p.name for p in cortes.glob('*.py'))}")

print()
print("== H02.2 — o ramo de escape no AST do teste ==")
test_file = REPO / "tests" / "test_contracts.py"
tree = ast.parse(test_file.read_text(encoding="utf-8"))
for fn in ast.walk(tree):
    if isinstance(fn, ast.FunctionDef) and fn.name == "test_ast_stage_functions_have_audited_decorator":
        for node in ast.walk(fn):
            if isinstance(node, ast.If):
                for sub in node.body:
                    if isinstance(sub, ast.Continue):
                        print(f"  tests/test_contracts.py:{node.lineno} -> "
                              f"'if {ast.unparse(node.test)}: continue'")

print()
print("== H02.3 — teste adversarial em cópia temporária ==")
tmp = pathlib.Path(tempfile.mkdtemp(prefix="h02_"))
shutil.copytree(REPO / "src", tmp / "src")
(tmp / "tests").mkdir()
shutil.copy2(test_file, tmp / "tests" / "test_contracts.py")
shutil.copy2(REPO / "tests" / "conftest.py", tmp / "tests" / "conftest.py")
print(f"  cópia isolada: {tmp}")

PY = str(REPO / ".venv" / "bin" / "python")
NODE = "test_contracts.py::test_ast_stage_functions_have_audited_decorator"
stage_py = tmp / "src" / "cortes" / "ingest.py"

cenarios = [
    ("A_nenhum_modulo_de_estagio_presente", None),
    ("B_modulo_presente_SEM_audited",
     "def run_ingest():\n    return 1\n"),
    ("C_modulo_presente_COM_audited",
     "from cortes.log import audited\n\n\n@audited(stage='ingest')\ndef run_ingest():\n    return 1\n"),
]

resultados = {}
for nome, conteudo in cenarios:
    if conteudo is None:
        stage_py.unlink(missing_ok=True)
    else:
        stage_py.write_text(conteudo, encoding="utf-8")
    res = subprocess.run(
        [PY, "-m", "pytest", NODE, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(tmp / "tests"),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(tmp / "src"),
             "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(tmp)},
    )
    veredito = "PASSOU" if res.returncode == 0 else "FALHOU"
    resultados[nome] = veredito
    print(f"\n  [{nome}] exit={res.returncode} -> {veredito}")
    print("    " + (res.stdout.strip().splitlines() or ["<sem saída>"])[-1])

stage_py.unlink(missing_ok=True)
shutil.rmtree(tmp, ignore_errors=True)

vacuo = (resultados.get("A_nenhum_modulo_de_estagio_presente") == "PASSOU"
         and resultados.get("B_modulo_presente_SEM_audited") == "FALHOU")
print()
print(f"H02_RESULTADOS={resultados}")
print(f"H02_VERDE_POR_VACUIDADE={vacuo}")
print(f"H02_ESTADO={'CONFIRMADA' if vacuo else 'REFUTADA'}")
