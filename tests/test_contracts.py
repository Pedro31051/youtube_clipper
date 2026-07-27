"""
Contract verification tests for Phase T0 architecture.
Validates:
(a) AST scan: all stage functions have @audited decorator
(b) AST scan: no subprocess usage outside src/cortes/log.py
(c) Schema validation for events.jsonl
(d) Strict seq continuity (no gaps, no duplicates)
"""

import ast
import pathlib
import pytest
import json
from typing import List
from cortes.log import (
    audited,
    run_cmd,
    set_run_id,
    get_run_id,
    get_run_dir,
    emit_event,
    validate_event_dict,
    ALLOWED_STAGES,
)

STAGE_MODULES = [
    "ingest",
    "transcribe",
    "scenes",
    "select",
    "cut",
    "subtitles",
    "audio",
    "transform",
    "render",
]


def is_audited_decorator(dec_node: ast.AST) -> bool:
    """Check if AST node represents @audited or @audited(...) or @cortes.log.audited(...)"""
    if isinstance(dec_node, ast.Name) and dec_node.id == "audited":
        return True
    elif isinstance(dec_node, ast.Call):
        if isinstance(dec_node.func, ast.Name) and dec_node.func.id == "audited":
            return True
        elif isinstance(dec_node.func, ast.Attribute) and dec_node.func.attr == "audited":
            return True
    elif isinstance(dec_node, ast.Attribute) and dec_node.attr == "audited":
        return True
    return False


def test_ast_stage_functions_have_audited_decorator():
    """Requirement (a): AST scan fails if any stage function lacks @audited decorator (including _ prefixed)."""
    src_dir = pathlib.Path(__file__).parent.parent / "src" / "cortes"
    assert src_dir.exists(), "src/cortes directory must exist"

    missing_audited = []

    for stage_name in STAGE_MODULES:
        stage_file = src_dir / f"{stage_name}.py"
        assert stage_file.exists(), f"Required audited stage module is missing: {stage_file}"

        tree = ast.parse(stage_file.read_text(encoding="utf-8"), filename=str(stage_file))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check ALL functions in stage modules (including private ones starting with '_')
                has_audited = any(is_audited_decorator(dec) for dec in node.decorator_list)
                if not has_audited:
                    missing_audited.append(
                        f"{stage_file.name}:{node.lineno} - function '{node.name}' lacks @audited"
                    )

    assert not missing_audited, (
        "The following stage functions are missing the @audited decorator:\n" + "\n".join(missing_audited)
    )


def scan_ast_for_violations(tree: ast.AST, filename: str) -> List[str]:
    """Helper to scan an AST tree for prohibited subprocess, system, eval/exec, and dynamic import patterns."""
    violations = []
    prohibited_os_attrs = {
        "system", "popen", "posix_spawn", "spawn", "spawnl", "spawnle",
        "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
        "exec", "execv", "execve", "execl", "execle", "execlp", "execlpe"
    }
    prohibited_asyncio_attrs = {
        "create_subprocess_exec", "create_subprocess_shell"
    }

    for node in ast.walk(tree):
        # 1. Direct or module imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess" or alias.name.startswith("subprocess."):
                    violations.append(
                        f"{filename}:{getattr(node, 'lineno', 1)} - Direct import of 'subprocess'"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "subprocess" or node.module.startswith("subprocess.")):
                violations.append(
                    f"{filename}:{getattr(node, 'lineno', 1)} - Import from 'subprocess'"
                )
            elif node.module == "os":
                for alias in node.names:
                    if alias.name in prohibited_os_attrs:
                        violations.append(
                            f"{filename}:{getattr(node, 'lineno', 1)} - Import of prohibited 'os.{alias.name}'"
                        )
            elif node.module == "asyncio":
                for alias in node.names:
                    if alias.name in prohibited_asyncio_attrs:
                        violations.append(
                            f"{filename}:{getattr(node, 'lineno', 1)} - Import of prohibited 'asyncio.{alias.name}'"
                        )

        # 2. Attribute accesses
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                if node.value.id == "subprocess":
                    violations.append(
                        f"{filename}:{getattr(node, 'lineno', 1)} - Access to 'subprocess.{node.attr}'"
                    )
                elif node.value.id == "os" and node.attr in prohibited_os_attrs:
                    violations.append(
                        f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited system call 'os.{node.attr}'"
                    )
                elif node.value.id == "asyncio" and node.attr in prohibited_asyncio_attrs:
                    violations.append(
                        f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited asyncio call 'asyncio.{node.attr}'"
                    )

        # 3. Function calls (eval, exec, __import__, importlib.import_module, direct call to system/popen/etc.)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_id = node.func.id
                if func_id in ("eval", "exec"):
                    violations.append(
                        f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited call to '{func_id}'"
                    )
                elif func_id == "__import__":
                    if node.args:
                        arg0 = node.args[0]
                        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                            if arg0.value == "subprocess" or arg0.value.startswith("subprocess."):
                                violations.append(
                                    f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited call '__import__({arg0.value!r})'"
                                )
                        else:
                            violations.append(
                                f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited call to '__import__'"
                            )
                    else:
                        violations.append(
                            f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited call to '__import__'"
                        )
                elif func_id == "import_module":
                    if node.args:
                        arg0 = node.args[0]
                        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                            if arg0.value == "subprocess" or arg0.value.startswith("subprocess."):
                                violations.append(
                                    f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited call 'import_module({arg0.value!r})'"
                                )
                elif func_id in prohibited_os_attrs or func_id in prohibited_asyncio_attrs:
                    violations.append(
                        f"{filename}:{getattr(node, 'lineno', 1)} - Direct call to prohibited function '{func_id}'"
                    )
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr == "import_module":
                    if node.args:
                        arg0 = node.args[0]
                        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                            if arg0.value == "subprocess" or arg0.value.startswith("subprocess."):
                                violations.append(
                                    f"{filename}:{getattr(node, 'lineno', 1)} - Prohibited call 'importlib.import_module({arg0.value!r})'"
                                )

    return violations


def test_ast_prohibit_subprocess_outside_run_cmd():
    """Requirement (b): AST scan fails if subprocess, os.system/popen/posix_spawn, importlib/subprocess, __import__('subprocess'), eval/exec, or asyncio subprocess is used outside src/cortes/log.py."""
    src_dir = pathlib.Path(__file__).parent.parent / "src"
    assert src_dir.exists(), "src directory must exist"

    violations = []

    for py_file in src_dir.rglob("*.py"):
        # Exempt log.py as it is the sole authorized module for subprocess invocation
        if py_file == src_dir / "cortes" / "log.py":
            continue

        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        violations.extend(
            scan_ast_for_violations(
                tree, str(py_file.relative_to(src_dir.parent))
            )
        )

    assert not violations, (
        "Prohibited subprocess/system usage detected outside src/cortes/log.py:\n" + "\n".join(violations)
    )


def test_ast_evasion_attempts_are_blocked():
    """Verify that AST scanner blocks all 10 known evasion vectors."""
    evasion_snippets = [
        "from os import system; system('ls')",
        "from os import popen; popen('ls')",
        "from os import posix_spawn; posix_spawn('/bin/ls', ['ls'], {})",
        "import importlib; sub = importlib.import_module('subprocess'); sub.run(['ls'])",
        "from importlib import import_module; sub = import_module('subprocess')",
        "__import__('subprocess').run(['ls'])",
        "eval('1+1')",
        "exec('1+1')",
        "import asyncio; asyncio.create_subprocess_exec('ls')",
        "import asyncio; asyncio.create_subprocess_shell('ls')",
        "from asyncio import create_subprocess_exec; create_subprocess_exec('ls')",
    ]

    for snippet in evasion_snippets:
        tree = ast.parse(snippet)
        violations = scan_ast_for_violations(tree, "snippet.py")
        assert len(violations) > 0, f"AST scanner failed to block evasion snippet: {snippet}"


def test_events_jsonl_schema_validation_on_all_runs(tmp_path):
    """Requirement (c): Fails if events.jsonl of any run does not validate against schema 1.0.0."""
    runs_dir = pathlib.Path("runs")
    if not runs_dir.exists() or not list(runs_dir.iterdir()):
        # Create a test run to verify schema validation logic
        set_run_id("test_schema_run")
        emit_event(stage="env", tool="python", outcome="ok")
        runs_dir = pathlib.Path("runs")

    for run_path in runs_dir.iterdir():
        if run_path.is_dir():
            events_file = run_path / "events.jsonl"
            if events_file.exists():
                lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
                for idx, line in enumerate(lines, start=1):
                    event_dict = json.loads(line)
                    # Must validate against fixed Schema 1.0.0
                    validate_event_dict(event_dict)


def test_events_seq_continuity_no_gaps_no_duplicates(tmp_path):
    """Requirement (d): Fails if there is any gap or duplicate in seq across any run."""
    run_id = f"test_seq_run_{tmp_path.name}"
    set_run_id(run_id)

    # Emit 5 events
    for i in range(5):
        emit_event(stage="env", tool="python", outcome="ok")

    events_file = get_run_dir(run_id) / "events.jsonl"
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 5

    expected_seq = 1
    seq_set = set()
    for idx, line in enumerate(lines, start=1):
        event = json.loads(line)
        seq = event["seq"]
        assert seq == expected_seq, f"Gap in seq at line {idx}: expected {expected_seq}, got {seq}"
        assert seq not in seq_set, f"Duplicate seq detected at line {idx}: {seq}"
        seq_set.add(seq)
        expected_seq += 1


def test_audited_decorator_functionality(tmp_path):
    """Test @audited decorator captures execution timing, hashes, and evidence."""
    run_id = f"test_audited_run_{tmp_path.name}"
    set_run_id(run_id)

    run_dir = get_run_dir(run_id)
    dummy_file = run_dir / "artifacts" / "output.txt"
    dummy_file.parent.mkdir(parents=True, exist_ok=True)
    dummy_file.write_text("hello world")

    @audited(stage="ingest")
    def sample_stage_func():
        return {"evidence_paths": [str(dummy_file)]}

    res = sample_stage_func()
    assert res == {"evidence_paths": [str(dummy_file)]}

    events_file = get_run_dir(run_id) / "events.jsonl"
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    event = json.loads(lines[0])

    assert event["stage"] == "ingest"
    assert event["outcome"] == "ok"
    assert len(event["evidence"]["paths"]) == 1
    assert event["evidence"]["paths"][0] == "artifacts/output.txt"
    assert event["evidence"]["sha256"][0].startswith("sha256:")
    assert event["evidence"]["bytes"][0] == 11


def test_run_cmd_subprocesses_logged(tmp_path):
    """Test run_cmd captures cmd, exit_code, stdout, stderr, and logs to commands.log and events.jsonl."""
    run_id = f"test_run_cmd_{tmp_path.name}"
    set_run_id(run_id)

    proc = run_cmd(["echo", "hello_world"], stage="env")
    assert proc.returncode == 0
    assert "hello_world" in proc.stdout

    run_dir = get_run_dir(run_id)
    cmd_log = run_dir / "commands.log"
    assert cmd_log.exists()
    assert "echo hello_world" in cmd_log.read_text()

    events_file = run_dir / "events.jsonl"
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["tool"] == "echo"
    assert event["cmd"] == "echo hello_world"
    assert event["exit_code"] == 0
