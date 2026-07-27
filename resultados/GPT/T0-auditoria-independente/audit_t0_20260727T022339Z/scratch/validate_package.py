"""Valida referências e rastreabilidade do pacote antes do manifesto."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent
REPO = RUN.parents[3]

commands = [
    json.loads(line)
    for line in (RUN / "COMANDOS.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
seqs = [item["seq"] for item in commands]
assert seqs == list(range(1, len(seqs) + 1)), seqs
uids = [item["cmd_uid"] for item in commands]
assert len(uids) == len(set(uids)), "cmd_uid duplicado"
for item in commands:
    assert (RUN / item["stdout_path"]).exists(), item
    assert (RUN / item["stderr_path"]).exists(), item

report = (RUN / "RELATORIO.md").read_text(encoding="utf-8")
references = sorted(set(re.findall(r"`((?:evidencias|scratch)/[^`]+)`", report)))
for reference in references:
    assert (RUN / reference).exists(), reference

verdict = json.loads((RUN / "VEREDITO.json").read_text(encoding="utf-8"))
for finding in verdict["findings"]:
    for reference in finding["evidence_paths"]:
        assert (RUN / reference).exists(), reference
    for command_id in finding["reproduction_command_ids"]:
        assert command_id in seqs, command_id

status = subprocess.run(
    ["git", "status", "--short"],
    cwd=REPO,
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()
prefix = "resultados/GPT/T0-auditoria-independente/" + RUN.name + "/"
unexpected = [line for line in status if prefix not in line]
assert not unexpected, unexpected

print(f"commands_contiguous=1..{len(seqs)}")
print(f"command_uids_unique={len(set(uids))}")
print(f"report_references_valid={len(references)}")
print(f"findings_valid={len(verdict['findings'])}")
print(f"unexpected_git_paths={unexpected}")
print(f"verdict={verdict['verdict']}")
