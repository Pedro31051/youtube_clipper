import os
import sys
import json
import time
import subprocess
from datetime import datetime, timezone

RUN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EVI_DIR = os.path.join(RUN_DIR, "evidencias")
COMANDOS_FILE = os.path.join(RUN_DIR, "COMANDOS.jsonl")
REPO_ROOT = "/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper"

seq_counter = 0

def run_step(cmd_str, stdout_filename, cwd=REPO_ROOT):
    global seq_counter
    seq_counter += 1
    ts_utc = datetime.now(timezone.utc).isoformat()
    stdout_path_rel = f"evidencias/{stdout_filename}"
    stdout_path_abs = os.path.join(EVI_DIR, stdout_filename)

    start_t = time.time()
    res = subprocess.run(cmd_str, shell=True, cwd=cwd, capture_output=True, text=True)
    duration_ms = int((time.time() - start_t) * 1000)

    output_content = res.stdout
    if res.stderr:
        if output_content:
            output_content += "\n--- STDERR ---\n" + res.stderr
        else:
            output_content = res.stderr

    with open(stdout_path_abs, "w", encoding="utf-8") as f:
        f.write(output_content)

    entry = {
        "seq": seq_counter,
        "ts_utc": ts_utc,
        "cwd": cwd,
        "cmd": cmd_str,
        "exit_code": res.returncode,
        "stdout_path": stdout_path_rel,
        "stderr_path": f"evidencias/{stdout_filename}" if res.stderr else None,
        "duration_ms": duration_ms
    }

    with open(COMANDOS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[{seq_counter}] {cmd_str} -> exit {res.returncode} ({duration_ms}ms)")
    return res

if __name__ == "__main__":
    print(f"Runner initialized for {RUN_DIR}")
