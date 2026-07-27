"""Etapa 4 do plano — avaliação dos testes de mutação.

Esta etapa foi inteiramente omitida no run anterior. O plano exige mapear cada
check de ``verify.py`` para pelo menos um teste de mutação e registrar:
  1. o teste correspondente de cada check;
  2. checks sem cobertura;
  3. duplicidades de ``check_id``;
  4. se múltiplos MP4s produzem resultados inequivocamente identificáveis;
  5. se a verificação rejeita corrupção relevante.

Nada aqui altera os testes versionados: as mutações experimentais ocorrem em
cópia temporária.
"""

from __future__ import annotations

import ast
import json
import pathlib
import shutil
import subprocess
import tempfile
from collections import Counter

REPO = pathlib.Path(__file__).resolve().parents[5]
VERIFY = REPO / "src" / "cortes" / "verify.py"
MUTATION = REPO / "tests" / "test_mutation.py"
PKG_RUN = REPO / "review" / "T0" / "runs" / "run_t0_golden"
PY = str(REPO / ".venv" / "bin" / "python")

print("== E4.1 — checks declarados em verify.py ==")
tree = ast.parse(VERIFY.read_text(encoding="utf-8"))
checks: list[str] = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "add_check":
        for kw in node.keywords:
            if kw.arg == "check_id" and isinstance(kw.value, ast.Constant):
                checks.append(kw.value.value)
print(f"  {len(checks)} chamadas add_check, {len(set(checks))} check_id distintos")
for c in sorted(set(checks)):
    print(f"    {c}")

print()
print("== E4.2 — cobertura por teste de mutação ==")
mut_src = MUTATION.read_text(encoding="utf-8")
mut_tree = ast.parse(mut_src)
testes = [n.name for n in ast.walk(mut_tree) if isinstance(n, ast.FunctionDef)
          and n.name.startswith("test_")]
print(f"  testes de mutação declarados: {len(testes)}")

cobertura: dict[str, list[str]] = {}
for n in ast.walk(mut_tree):
    if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"):
        corpo = ast.unparse(n)
        for c in set(checks):
            if c in corpo:
                cobertura.setdefault(c, []).append(n.name)

sem_cobertura = sorted(set(checks) - set(cobertura))
for c in sorted(set(checks)):
    marca = "OK " if c in cobertura else "SEM"
    print(f"  [{marca}] {c:<28} -> {cobertura.get(c, [])}")
print(f"  CHECKS SEM TESTE DE MUTAÇÃO CORRESPONDENTE ({len(sem_cobertura)}): {sem_cobertura}")

print()
print("== E4.2b — a mutação atinge o artefato REAL ou uma estrutura sintética? ==")
usa_oficial = ("review/T0" in mut_src) or ("run_t0_golden" in mut_src)
print(f"  os testes de mutação referenciam o pacote oficial review/T0/? {usa_oficial}")
print(f"  fixture de origem: create_synthetic_golden_run(tmp_path) -> run sintético temporário")
for n in ast.walk(mut_tree):
    if isinstance(n, ast.FunctionDef) and n.name == "copy_golden_for_mutation":
        for sub in ast.walk(n):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr == "replace":
                print(f"  tests/test_mutation.py:{sub.lineno} -> {ast.unparse(sub)}")
                print("    O arsenal de mutação REESCREVE os caminhos absolutos antes de")
                print("    verificar. A suíte compensa o defeito de portabilidade e, por")
                print("    construção, nunca pode detectá-lo.")

print()
print("== E4.2c — a asserção sustenta o teste? (mutação do próprio teste, em cópia) ==")
print("  Neutralizar a asserção para 'assert True' seria tautológico e não provaria nada.")
print("  Aplicam-se duas mutações informativas, ambas com FALHA esperada:")
print("    (i)  INVERTER a asserção, mantendo a corrupção do artefato;")
print("    (ii) REMOVER a corrupção do artefato, mantendo a asserção original.")

tmp_t = pathlib.Path(tempfile.mkdtemp(prefix="e4_teste_"))
shutil.copytree(REPO / "tests", tmp_t / "tests")
alvo_teste = tmp_t / "tests" / "test_mutation.py"
original_txt = alvo_teste.read_text(encoding="utf-8")
ALVO = "test_mutation_1_byte_corruption"
env_t = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
         "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(tmp_t)}


def bloco_do_teste(txt: str, nome: str):
    linhas = txt.splitlines()
    ini = next(i for i, l in enumerate(linhas) if l.startswith(f"def {nome}"))
    fim = next((i for i in range(ini + 1, len(linhas)) if linhas[i].startswith("def ")), len(linhas))
    return linhas, ini, fim


def rodar(rotulo: str, esperado: str) -> None:
    r = subprocess.run(
        [PY, "-m", "pytest", f"tests/test_mutation.py::{ALVO}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=str(tmp_t), capture_output=True, text=True, env=env_t)
    obtido = "PASSOU" if r.returncode == 0 else "FALHOU"
    veredito = "OK (asserção sustenta o teste)" if obtido == esperado else \
               "DEFEITO (asserção não sustenta o teste)"
    print(f"  [{rotulo}] exit={r.returncode} -> {obtido} (esperado {esperado}) :: {veredito}")
    print(f"    {(r.stdout.strip().splitlines() or ['<sem saída>'])[-1]}")


# Controle: o teste íntegro deve passar.
alvo_teste.write_text(original_txt, encoding="utf-8")
rodar("controle: teste íntegro", "PASSOU")

# (i) inverter a asserção
linhas, ini, fim = bloco_do_teste(original_txt, ALVO)
inv = list(linhas)
for i in range(ini, fim):
    s = inv[i].strip()
    if s.startswith("assert ") and not s.startswith("assert not "):
        indent = len(inv[i]) - len(inv[i].lstrip())
        inv[i] = " " * indent + "assert not (" + s[len("assert "):].split(", ")[0] + ")"
alvo_teste.write_text("\n".join(inv) + "\n", encoding="utf-8")
rodar("(i) asserção invertida", "FALHOU")

# (ii) remover a corrupção do artefato, preservando as asserções
linhas, ini, fim = bloco_do_teste(original_txt, ALVO)
sem = list(linhas)
removidas = 0
for i in range(ini, fim):
    if "f.write(" in sem[i]:
        indent = len(sem[i]) - len(sem[i].lstrip())
        sem[i] = " " * indent + "pass  # gravação da corrupção neutralizada pela auditoria"
        removidas += 1
alvo_teste.write_text("\n".join(sem) + "\n", encoding="utf-8")
print(f"  (linhas de corrupção neutralizadas em (ii): {removidas})")
rodar("(ii) corrupção removida", "FALHOU")

alvo_teste.write_text(original_txt, encoding="utf-8")
shutil.rmtree(tmp_t, ignore_errors=True)

print()
print("== E4.3 — duplicidade de check_id com múltiplos MP4s ==")
tmp = pathlib.Path(tempfile.mkdtemp(prefix="e4_"))
sandbox = tmp / "cwd"
sandbox.mkdir()
copia = tmp / "run_dois_mp4"
shutil.copytree(PKG_RUN, copia)
mp4_original = copia / "artifacts" / "render" / "short.mp4"
segundo = copia / "artifacts" / "render" / "segundo_video.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
     "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
     "-c:v", "libx264", "-c:a", "aac", "-shortest", str(segundo)],
    capture_output=True, text=True,
)
print(f"  segundo MP4 injetado na cópia: {segundo.name} "
      f"({segundo.stat().st_size} bytes, 320x240, 2 s)")

subprocess.run([PY, "-m", "cortes.verify", str(copia)], cwd=str(sandbox),
               capture_output=True, text=True,
               env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                    "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(sandbox)})
res = json.loads((copia / "verify_result.json").read_text(encoding="utf-8"))
contagem = Counter(c["check_id"] for c in res["checks"])
duplicados = {k: v for k, v in contagem.items() if v > 1}
print(f"  total_checks={res['total_checks']} overall_passed={res['overall_passed']}")
print(f"  check_id duplicados: {duplicados}")
for c in res["checks"]:
    if contagem[c["check_id"]] > 1:
        print(f"    {c['check_id']:<22} passed={str(c['passed']):<5} "
              f"measured={c['measured']:<28} evidence_path={c['evidence_path']}")
identificavel = all(
    len({c["evidence_path"] for c in res["checks"] if c["check_id"] == cid}) == n
    for cid, n in duplicados.items()
)
print(f"  cada ocorrência duplicada tem evidence_path distinto (identificável): {identificavel}")

print()
print("== E4.4 — a verificação rejeita corrupção relevante? ==")
casos = {}
for rotulo, mutacao in (
    ("mp4_truncado", "truncar"),
    ("events_sha_alterado", "sha"),
    ("artefato_declarado_removido", "remover"),
):
    alvo = tmp / f"run_{rotulo}"
    shutil.copytree(PKG_RUN, alvo)
    if mutacao == "truncar":
        m = alvo / "artifacts" / "render" / "short.mp4"
        m.write_bytes(m.read_bytes()[:1024])
    elif mutacao == "sha":
        ev = alvo / "events.jsonl"
        ev.write_text(ev.read_text(encoding="utf-8").replace("sha256:64843e05", "sha256:deadbeef"),
                      encoding="utf-8")
    elif mutacao == "remover":
        shutil.rmtree(alvo / "artifacts")
    r = subprocess.run([PY, "-m", "cortes.verify", str(alvo)], cwd=str(sandbox),
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                            "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(sandbox)})
    d = json.loads((alvo / "verify_result.json").read_text(encoding="utf-8"))
    casos[rotulo] = {"exit": r.returncode, "overall_passed": d["overall_passed"],
                     "total_checks": d["total_checks"],
                     "falhas": [c["check_id"] for c in d["checks"] if not c["passed"]]}
    print(f"  [{rotulo}] {json.dumps(casos[rotulo], ensure_ascii=False)}")

print()
print("== Etapa 4 — síntese ==")
print(f"  checks sem cobertura de mutação: {len(sem_cobertura)} -> {sem_cobertura}")
print(f"  duplicidade de check_id observada: {bool(duplicados)}")
aceita_corrupcao = [k for k, v in casos.items() if v["overall_passed"]]
print(f"  corrupções ACEITAS como válidas pelo verificador: {aceita_corrupcao}")
print(f"E4_ESTADO={'DEFEITO_CONFIRMADO' if (sem_cobertura or aceita_corrupcao or duplicados) else 'OK'}")
shutil.rmtree(tmp, ignore_errors=True)
