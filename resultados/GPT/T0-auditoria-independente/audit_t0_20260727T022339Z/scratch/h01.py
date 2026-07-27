"""H01 — O scanner AST não cobre todo o código produtivo.

Medição (não narrativa):
1. Extrai do AST de tests/test_contracts.py a raiz efetivamente varrida pelo
   teste de exclusividade de run_cmd().
2. Reaplica o MESMO scanner (importado do próprio teste) sobre TODO o src/.
3. Classifica cada ocorrência em AUTORIZADA / PROIBIDA / FALSO_POSITIVO.
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "src"))

from test_contracts import scan_ast_for_violations  # noqa: E402

print("== H01.1 — raiz varrida pelo teste de contrato (extraída do AST do teste) ==")
test_src = (REPO / "tests" / "test_contracts.py").read_text(encoding="utf-8")
tree = ast.parse(test_src)
for fn in ast.walk(tree):
    if isinstance(fn, ast.FunctionDef) and fn.name in (
        "test_ast_prohibit_subprocess_outside_run_cmd",
        "test_ast_stage_functions_have_audited_decorator",
    ):
        literals = [
            n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        joined = [x for x in literals if x in ("src", "cortes", "youtube_clipper")]
        print(f"  {fn.name}: componentes de caminho literais = {joined}")

print()
print("== H01.2 — scanner do teste reaplicado a TODO o src/ ==")
src_dir = REPO / "src"
per_pkg: dict[str, list[str]] = {}
for py in sorted(src_dir.rglob("*.py")):
    rel = py.relative_to(REPO)
    pkg = rel.parts[1]
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    v = scan_ast_for_violations(tree, str(rel))
    if v:
        per_pkg.setdefault(pkg, []).extend(v)

for pkg in sorted(per_pkg):
    print(f"\n  --- pacote src/{pkg}/ : {len(per_pkg[pkg])} ocorrências ---")
    for item in per_pkg[pkg]:
        fname = item.split(":")[0]
        if fname.endswith("cortes/log.py"):
            klass = "AUTORIZADA (log.py é o ponto único permitido)"
        else:
            klass = "PROIBIDA pelo contrato"
        print(f"    [{klass}] {item}")

print()
print("== H01.3 — cobertura efetiva ==")
scanned = sorted(str(p.relative_to(REPO)) for p in (src_dir / "cortes").rglob("*.py"))
unscanned = sorted(
    str(p.relative_to(REPO)) for p in src_dir.rglob("*.py")
    if "cortes" not in p.relative_to(REPO).parts
)
print(f"  arquivos DENTRO do escopo do teste ({len(scanned)}): {scanned}")
print(f"  arquivos FORA do escopo do teste ({len(unscanned)}):")
for u in unscanned:
    print(f"    {u}")

proibidas = sum(
    1 for pkg in per_pkg for item in per_pkg[pkg]
    if not item.split(":")[0].endswith("cortes/log.py")
)
print()
print(f"H01_OCORRENCIAS_PROIBIDAS_FORA_DO_ESCOPO={proibidas}")
print(f"H01_ESTADO={'CONFIRMADA' if proibidas > 0 else 'REFUTADA'}")
