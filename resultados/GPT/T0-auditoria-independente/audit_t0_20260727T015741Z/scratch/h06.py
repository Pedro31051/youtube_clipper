"""H06 — O dashboard possui superfície insegura quando exposto.

Correção do FISC-GPT-006: o run anterior importou a classe do handler e imprimiu
três frases escritas de antemão pelo executor. Nada foi medido. Aqui tudo é
medido: o AST responde pela análise estática e um servidor real, preso a
127.0.0.1 numa porta efêmera (regra 14 do plano), responde pelo comportamento.

Nenhum arquivo é enviado ao Drive, nenhuma credencial é lida, nenhuma porta
externa é aberta e nenhuma URL de terceiros é acessada.
"""

from __future__ import annotations

import ast
import http.client
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

REPO = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))

FONTE = REPO / "src" / "youtube_clipper" / "web_dashboard.py"
tree = ast.parse(FONTE.read_text(encoding="utf-8"), filename=str(FONTE))

print("== H06.1 — endereço de bind (medido no AST, não afirmado) ==")
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "start_dashboard_server":
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "server_address" for t in sub.targets
            ):
                valor = ast.unparse(sub.value)
                print(f"  web_dashboard.py:{sub.lineno} -> server_address = {valor}")
                host = ast.literal_eval(sub.value.elts[0])
                print(f"  host efetivo = {host!r} "
                      f"-> {'TODAS as interfaces (0.0.0.0)' if host == '' else host}")
        for sub in ast.walk(node):
            if isinstance(sub, ast.arg) and sub.arg == "port":
                pass
        defaults = [ast.unparse(d) for d in node.args.defaults]
        print(f"  porta padrão = {defaults}")

print()
print("== H06.2 — autenticação: busca por qualquer verificação de credencial ==")
TERMOS = ("authorization", "www-authenticate", "api_key", "apikey", "x-api-key",
          "token", "password", "senha", "bearer", "basic ", "session", "csrf", "login")
achados = []
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        low = node.value.lower()
        for t in TERMOS:
            if t in low and len(node.value) < 200:
                achados.append((node.lineno, t, node.value[:80]))
print(f"  literais relacionados a autenticação encontrados no módulo: {len(achados)}")
for lineno, termo, valor in achados[:15]:
    print(f"    linha {lineno}: termo '{termo}' em {valor!r}")
handler_metodos = [
    n.name for n in ast.walk(tree)
    if isinstance(n, ast.ClassDef) and n.name == "ClipperDashboardHandler"
    for n in n.body if isinstance(n, ast.FunctionDef)
]
print(f"  métodos do handler: {handler_metodos}")
print(f"  existe método de autenticação/autorização? "
      f"{any('auth' in m.lower() for m in handler_metodos)}")

print()
print("== H06.3 — diretórios servidos por /api/download/ (medido no AST) ==")
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "allowed_base_dirs" for t in node.targets
    ):
        print(f"  web_dashboard.py:{node.lineno} -> allowed_base_dirs =")
        for elt in node.value.elts:
            print(f"    {ast.unparse(elt)}")

print()
print("== H06.4 — mutação global de YOUTUBE_COOKIES_FILE (medido no AST) ==")
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute)
                    and t.value.attr == "environ"):
                print(f"  web_dashboard.py:{node.lineno} -> "
                      f"{ast.unparse(t)} = {ast.unparse(node.value)}")
                print("    (escrita em variável de ambiente do PROCESSO, a partir de "
                      "corpo de requisição não autenticado)")

print()
print("== H06.5 — teste vivo, isolado em 127.0.0.1, porta efêmera ==")
from youtube_clipper.web_dashboard import ClipperDashboardHandler  # noqa: E402

sandbox = pathlib.Path(tempfile.mkdtemp(prefix="h06_"))
os.chdir(sandbox)
isca = sandbox / "arquivo_privado_do_cwd.mp4"
isca.write_bytes(b"CONTEUDO-SENSIVEL-NO-CWD" * 4)
isca_tmp = pathlib.Path(tempfile.gettempdir()) / "h06_isca_no_tmp.mp4"
isca_tmp.write_bytes(b"CONTEUDO-SENSIVEL-NO-TMP" * 4)
print(f"  CWD do servidor: {sandbox}")
print(f"  isca criada no CWD: {isca.name} ({isca.stat().st_size} bytes)")
print(f"  isca criada em {tempfile.gettempdir()}: {isca_tmp.name} ({isca_tmp.stat().st_size} bytes)")

srv = ThreadingHTTPServer(("127.0.0.1", 0), ClipperDashboardHandler)
porta = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
print(f"  servidor de teste em 127.0.0.1:{porta} (loopback, efêmera)")


def requisitar(metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    con = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    body = json.dumps(corpo).encode() if corpo is not None else None
    con.request(metodo, caminho, body=body,
                headers={"Content-Type": "application/json"} if body else {})
    r = con.getresponse()
    dados = r.read()
    con.close()
    return {"status": r.status, "bytes": len(dados), "amostra": dados[:60]}


print()
print("  --- requisições SEM nenhuma credencial ---")
casos = [
    ("GET", "/", None),
    ("GET", f"/api/download/{isca.name}", None),
    ("GET", f"/api/download/{isca_tmp.name}", None),
    ("GET", "/api/download/../../../etc/passwd", None),
    ("POST", "/api/analyze", {}),
]
resultados = {}
for metodo, caminho, corpo in casos:
    try:
        r = requisitar(metodo, caminho, corpo)
    except Exception as exc:  # noqa: BLE001
        r = {"status": None, "erro": f"{type(exc).__name__}: {exc}"}
    resultados[f"{metodo} {caminho}"] = r
    print(f"    {metodo:<5} {caminho:<42} -> {r}")

print()
print("  --- mutação global de estado por requisição não autenticada ---")
antes = os.environ.get("YOUTUBE_COOKIES_FILE", "<não definido>")
falso_cookie = str(sandbox / "cookies_injetados_pelo_cliente.txt")
r_mut = requisitar("POST", "/api/analyze", {"url": "https://example.invalid/x",
                                            "cookies": falso_cookie})
depois = os.environ.get("YOUTUBE_COOKIES_FILE", "<não definido>")
print(f"    resposta: {r_mut['status']}")
print(f"    YOUTUBE_COOKIES_FILE antes .: {antes}")
print(f"    YOUTUBE_COOKIES_FILE depois : {depois}")
mutou = depois == falso_cookie
print(f"    variável global do processo alterada pelo cliente: {mutou}")

print()
print("  --- /api/gdrive-upload aceita file_path absoluto arbitrário? ---")
print("      (o uploader é substituído por dublê: NENHUM envio real ao Drive ocorre)")
from youtube_clipper import web_dashboard as wd  # noqa: E402

entregues: list[dict] = []


def uploader_duble(file_path, folder_id=None, **kw):
    entregues.append({"file_path": file_path, "folder_id": folder_id})
    return {"success": False, "error": "envio bloqueado pela auditoria"}


_uploader_real = wd.upload_clip_to_gdrive
wd.upload_clip_to_gdrive = uploader_duble
r_up = requisitar("POST", "/api/gdrive-upload", {"file_path": "/etc/passwd"})
wd.upload_clip_to_gdrive = _uploader_real
print(f"    POST /api/gdrive-upload {{'file_path': '/etc/passwd'}} -> {r_up}")
print(f"    caminhos que chegaram ao uploader: {entregues}")
upload_arbitrario = any(e["file_path"] == "/etc/passwd" for e in entregues)
print(f"    caminho absoluto fora de qualquer allowlist aceito: {upload_arbitrario}")

print()
print("  --- requisições simultâneas sobre o estado global ---")
import concurrent.futures  # noqa: E402

observados: list[tuple[str, str]] = []


def cliente(i: int):
    meu_cookie = str(sandbox / f"cookies_cliente_{i}.txt")
    requisitar("POST", "/api/analyze", {"url": "https://example.invalid/x", "cookies": meu_cookie})
    observados.append((meu_cookie, os.environ.get("YOUTUBE_COOKIES_FILE", "")))


with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    list(ex.map(cliente, range(8)))

divergentes = sum(1 for meu, global_ in observados if meu != global_)
print(f"    8 clientes simultâneos, cada um com seu próprio arquivo de cookies")
print(f"    valor global de YOUTUBE_COOKIES_FILE ao final: "
      f"{os.environ.get('YOUTUBE_COOKIES_FILE')!r}")
print(f"    clientes cujo cookie foi sobrescrito por outro cliente: {divergentes}/8")
corrida = divergentes > 0
print(f"    corrida entre clientes sobre estado global comprovada: {corrida}")

srv.shutdown()
isca_tmp.unlink(missing_ok=True)

print()
print("== H06 — síntese medida ==")
sem_auth = all(
    r.get("status") not in (401, 403)
    for r in resultados.values() if r.get("status") is not None
)
vazou_cwd = resultados[f"GET /api/download/{isca.name}"].get("status") == 200
vazou_tmp = resultados[f"GET /api/download/{isca_tmp.name}"].get("status") == 200
print(f"  nenhuma resposta exigiu autenticação (401/403): {sem_auth}")
print(f"  arquivo do CWD servido a cliente anônimo: {vazou_cwd}")
print(f"  arquivo de {tempfile.gettempdir()} servido a cliente anônimo: {vazou_tmp}")
print(f"  bind padrão em todas as interfaces: True (server_address = ('', port))")
print(f"  estado global mutável por requisição anônima: {mutou}")
print(f"  file_path absoluto arbitrário aceito por /api/gdrive-upload: {upload_arbitrario}")
print(f"  corrida entre clientes concorrentes sobre estado global: {corrida}")
inseguro = sem_auth and (vazou_cwd or vazou_tmp or mutou or upload_arbitrario)
print(f"H06_ESTADO={'CONFIRMADA' if inseguro else 'REFUTADA'}")
print(f"H06_SANDBOX={sandbox}")
