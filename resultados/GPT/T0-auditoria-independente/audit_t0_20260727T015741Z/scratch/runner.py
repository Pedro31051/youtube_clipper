"""Runner de captura de provas — auditoria independente T0 (run corrigido).

Correções aplicadas em resposta ao parecer de fiscalização ChatGPT:

- FISC-GPT-004: evidência é append-only. Um arquivo de evidência já existente
  NUNCA é sobrescrito; cada nova tentativa sobre o mesmo slot recebe um arquivo
  próprio (``<slot>.att2.txt``, ``<slot>.att3.txt``, ...). Tentativas fracassadas
  ficam preservadas com stdout e stderr literais.
- FISC-GPT-005: a sequência de comandos é global, contínua e sobrevive à troca de
  processo. O contador vive em ``scratch/.seq_state`` protegido por ``fcntl``.
  Cada comando recebe também um identificador único ``cmd_uid``.
- Protocolo do plano (secção 5): stdout e stderr são gravados LITERALMENTE em
  arquivos separados, sem cabeçalho, sem edição e sem mesclagem. Metadados ficam
  exclusivamente em COMANDOS.jsonl.

Uso:
    python3 runner.py <slot> <cmd...>          # executa e registra
    python3 runner.py --cwd <dir> <slot> <cmd...>
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

RUN_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EVI_DIR = os.path.join(RUN_DIR, "evidencias")
SCRATCH_DIR = os.path.join(RUN_DIR, "scratch")
COMANDOS_FILE = os.path.join(RUN_DIR, "COMANDOS.jsonl")
SEQ_STATE_FILE = os.path.join(SCRATCH_DIR, ".seq_state")
RUN_ID = os.path.basename(RUN_DIR)
REPO_ROOT = os.path.abspath(os.path.join(RUN_DIR, "..", "..", "..", ".."))


def next_seq() -> int:
    """Reserva o próximo número de sequência global sob trava de arquivo.

    O contador é persistido em disco, de modo que processos distintos continuem
    a mesma sequência em vez de reiniciar em 1 (FISC-GPT-005).
    """
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    with open(SEQ_STATE_FILE, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            raw = fh.read().strip()
            current = int(raw) if raw else 0
            nxt = current + 1
            fh.seek(0)
            fh.truncate()
            fh.write(str(nxt))
            fh.flush()
            os.fsync(fh.fileno())
            return nxt
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def reserve_attempt(slot: str) -> tuple[int, str, str]:
    """Escolhe nomes de arquivo inéditos para o slot, sem jamais sobrescrever.

    Returns:
        (attempt, caminho relativo do stdout, caminho relativo do stderr)
    """
    os.makedirs(EVI_DIR, exist_ok=True)
    attempt = 1
    while True:
        suffix = "" if attempt == 1 else f".att{attempt}"
        out_rel = f"evidencias/{slot}{suffix}.txt"
        err_rel = f"evidencias/{slot}{suffix}.stderr.txt"
        out_abs = os.path.join(RUN_DIR, out_rel)
        err_abs = os.path.join(RUN_DIR, err_rel)
        if not os.path.exists(out_abs) and not os.path.exists(err_abs):
            return attempt, out_rel, err_rel
        attempt += 1


def run_step(cmd, slot: str, cwd: str = REPO_ROOT, shell: bool = False) -> subprocess.CompletedProcess:
    """Executa um comando, preserva stdout/stderr literais e registra o metadado."""
    seq = next_seq()
    attempt, out_rel, err_rel = reserve_attempt(slot)
    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    ts_utc = datetime.now(timezone.utc).isoformat()

    start_t = time.monotonic()
    res = subprocess.run(
        cmd,
        shell=shell,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
    )
    duration_ms = int((time.monotonic() - start_t) * 1000)

    # Gravação literal e exclusiva: nada é concatenado, editado ou removido.
    with open(os.path.join(RUN_DIR, out_rel), "x", encoding="utf-8") as fh:
        fh.write(res.stdout or "")
    with open(os.path.join(RUN_DIR, err_rel), "x", encoding="utf-8") as fh:
        fh.write(res.stderr or "")

    entry = {
        "seq": seq,
        "cmd_uid": f"{RUN_ID}#{seq:04d}",
        "slot": slot,
        "attempt": attempt,
        "ts_utc": ts_utc,
        "cwd": cwd,
        "cmd": cmd_str,
        "exit_code": res.returncode,
        "stdout_path": out_rel,
        "stderr_path": err_rel,
        "stdout_bytes": len((res.stdout or "").encode("utf-8")),
        "stderr_bytes": len((res.stderr or "").encode("utf-8")),
        "duration_ms": duration_ms,
    }

    with open(COMANDOS_FILE, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    print(f"[seq={seq} uid={entry['cmd_uid']} slot={slot} att={attempt}] "
          f"exit={res.returncode} {duration_ms}ms -> {out_rel}")
    return res


def main() -> int:
    argv = sys.argv[1:]
    cwd = REPO_ROOT
    if argv and argv[0] == "--cwd":
        cwd = argv[1]
        argv = argv[2:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    slot, cmd = argv[0], argv[1:]
    res = run_step(cmd, slot, cwd=cwd)
    return res.returncode


if __name__ == "__main__":
    raise SystemExit(main())
