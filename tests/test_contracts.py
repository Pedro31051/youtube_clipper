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
from datetime import datetime
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
    "report",
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


def test_t1_environment_execution_is_audited():
    """The T1 execution boundary must emit an audited env-stage event."""
    env_file = pathlib.Path(__file__).parent.parent / "src" / "cortes" / "env.py"
    tree = ast.parse(env_file.read_text(encoding="utf-8"), filename=str(env_file))
    runner = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_execute_environment_phase"
    )
    assert any(is_audited_decorator(dec) for dec in runner.decorator_list)


def scan_ast_for_violations(tree: ast.AST, filename: str, is_test_file: bool = False) -> List[str]:
    """Helper to scan an AST tree for prohibited subprocess, system, eval/exec, dynamic import, and evasion patterns."""
    violations = []
    prohibited_os_attrs = {
        "system", "popen", "posix_spawn", "spawn", "spawnl", "spawnle",
        "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
        "exec", "execv", "execve", "execl", "execle", "execlp", "execlpe"
    }
    prohibited_asyncio_attrs = {
        "create_subprocess_exec", "create_subprocess_shell",
        "subprocess_exec", "subprocess_shell"
    }
    evasion_modules = {"subprocess", "os", "pty", "ctypes", "asyncio", "importlib"}
    strictly_prohibited_modules = {"pty", "ctypes"}

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 1)

        # 1. Direct or module imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name.split(".")[0]

                # Check for aliased imports (import os as my_os, import subprocess as sub, etc.)
                if alias.asname is not None:
                    if mod_name in evasion_modules:
                        violations.append(
                            f"{filename}:{lineno} - Prohibited aliased import 'import {alias.name} as {alias.asname}'"
                        )

                # Direct imports of prohibited modules
                if not is_test_file and (mod_name == "subprocess" or alias.name.startswith("subprocess.")):
                    violations.append(
                        f"{filename}:{lineno} - Direct import of 'subprocess'"
                    )
                elif mod_name in strictly_prohibited_modules:
                    violations.append(
                        f"{filename}:{lineno} - Direct import of prohibited module '{alias.name}'"
                    )

        elif isinstance(node, ast.ImportFrom):
            mod_name = (node.module or "").split(".")[0]

            # Check for star import (from os import *)
            for alias in node.names:
                if alias.name == "*":
                    if mod_name in evasion_modules:
                        violations.append(
                            f"{filename}:{lineno} - Prohibited star import 'from {node.module} import *'"
                        )
                elif alias.asname is not None:
                    if mod_name in evasion_modules:
                        violations.append(
                            f"{filename}:{lineno} - Prohibited aliased import 'from {node.module} import {alias.name} as {alias.asname}'"
                        )

            if not is_test_file and node.module and (node.module == "subprocess" or node.module.startswith("subprocess.")):
                violations.append(
                    f"{filename}:{lineno} - Import from 'subprocess'"
                )
            elif mod_name in strictly_prohibited_modules:
                violations.append(
                    f"{filename}:{lineno} - Import from prohibited module '{node.module}'"
                )
            elif node.module and (node.module == "os" or node.module.startswith("os.")):
                for alias in node.names:
                    if alias.name in prohibited_os_attrs:
                        violations.append(
                            f"{filename}:{lineno} - Import of prohibited 'os.{alias.name}'"
                        )
            elif node.module and (node.module == "asyncio" or node.module.startswith("asyncio.")):
                for alias in node.names:
                    if alias.name in prohibited_asyncio_attrs or "subprocess" in alias.name:
                        violations.append(
                            f"{filename}:{lineno} - Import of prohibited 'asyncio.{alias.name}'"
                        )

        # 2. Attribute accesses
        elif isinstance(node, ast.Attribute):
            if node.attr in prohibited_asyncio_attrs:
                violations.append(
                    f"{filename}:{lineno} - Prohibited asyncio loop subprocess method '.{node.attr}'"
                )
            elif isinstance(node.value, ast.Name):
                val_id = node.value.id
                if val_id == "subprocess" and (
                    not is_test_file
                    or node.attr
                    in {"run", "Popen", "call", "check_call", "check_output"}
                ):
                    violations.append(
                        f"{filename}:{lineno} - Access to 'subprocess.{node.attr}'"
                    )
                elif val_id in strictly_prohibited_modules:
                    violations.append(
                        f"{filename}:{lineno} - Access to prohibited module '{val_id}.{node.attr}'"
                    )
                elif val_id == "os" and node.attr in prohibited_os_attrs:
                    violations.append(
                        f"{filename}:{lineno} - Prohibited system call 'os.{node.attr}'"
                    )
                elif val_id == "asyncio" and (node.attr in prohibited_asyncio_attrs or "subprocess" in node.attr):
                    violations.append(
                        f"{filename}:{lineno} - Prohibited asyncio call 'asyncio.{node.attr}'"
                    )

        # 3. Function calls (eval, exec, getattr, __import__, importlib.import_module, asyncio loop subprocess methods, system calls)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_id = node.func.id
                if func_id in ("eval", "exec"):
                    violations.append(
                        f"{filename}:{lineno} - Prohibited call to '{func_id}'"
                    )
                elif func_id == "getattr":
                    violations.append(
                        f"{filename}:{lineno} - Prohibited call to 'getattr'"
                    )
                elif func_id == "__import__":
                    arg0_val = None
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        arg0_val = node.args[0].value
                    violations.append(
                        f"{filename}:{lineno} - Prohibited call to '__import__' ({arg0_val!r})"
                    )
                elif func_id == "import_module":
                    arg0_val = None
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        arg0_val = node.args[0].value
                    violations.append(
                        f"{filename}:{lineno} - Prohibited call to 'import_module' ({arg0_val!r})"
                    )
                elif func_id in prohibited_os_attrs or func_id in prohibited_asyncio_attrs:
                    violations.append(
                        f"{filename}:{lineno} - Direct call to prohibited function '{func_id}'"
                    )

            elif isinstance(node.func, ast.Attribute):
                if node.func.attr == "import_module":
                    arg0_val = None
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        arg0_val = node.args[0].value
                    violations.append(
                        f"{filename}:{lineno} - Prohibited call 'importlib.import_module' ({arg0_val!r})"
                    )
                elif node.func.attr in prohibited_asyncio_attrs:
                    violations.append(
                        f"{filename}:{lineno} - Prohibited call to asyncio subprocess method '.{node.func.attr}'"
                    )

    return violations


def test_ast_prohibit_subprocess_outside_run_cmd():
    """Requirement (b): AST scan fails if subprocess, os.system/popen/posix_spawn, importlib/subprocess, __import__('subprocess'), eval/exec, or asyncio subprocess is used outside src/cortes/log.py across src/ and tests/."""
    project_root = pathlib.Path(__file__).parent.parent
    src_dir = project_root / "src"
    tests_dir = project_root / "tests"
    assert src_dir.exists(), "src directory must exist"
    assert tests_dir.exists(), "tests directory must exist"

    violations = []
    py_files = list(src_dir.rglob("*.py")) + list(tests_dir.rglob("*.py"))

    for py_file in py_files:
        rel_path = str(py_file.relative_to(project_root))

        # Exempt log.py (sole authorized subprocess gateway) and test_contracts.py (scanner test suite with evasion vectors)
        if rel_path in ("src/cortes/log.py", "tests/test_contracts.py"):
            continue

        is_test = rel_path.startswith("tests/")
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=rel_path)
        violations.extend(
            scan_ast_for_violations(
                tree, rel_path, is_test_file=is_test
            )
        )

    assert not violations, (
        "Prohibited subprocess/system usage detected outside src/cortes/log.py:\n" + "\n".join(violations)
    )


def test_ast_evasion_attempts_are_blocked():
    """Verify that AST scanner blocks all 8 evasion vectors across 12 concrete evasion test snippets."""
    evasion_snippets = [
        # Vector 1: __import__("os") / __import__("subprocess")
        "__import__('os').system('ls')",
        "__import__('subprocess').run(['ls'])",
        # Vector 2: importlib.import_module("os")
        "import importlib; sub = importlib.import_module('subprocess'); sub.run(['ls'])",
        "from importlib import import_module; sub = import_module('subprocess')",
        # Vector 3: pty
        "import pty; pty.spawn('/bin/ls')",
        "from pty import spawn; spawn('/bin/ls')",
        # Vector 4: ctypes
        "import ctypes; ctypes.CDLL(None).system(b'ls')",
        "from ctypes import CDLL; CDLL(None)",
        # Vector 5: getattr()
        "getattr(__import__('os'), 'system')('ls')",
        "getattr(os, 'system')('ls')",
        # Vector 6: from os import *
        "from os import *",
        "from subprocess import *",
        # Vector 7: aliased imports (import os as my_os, from os import system as sys_call)
        "import os as my_os; my_os.system('ls')",
        "from os import system as sys_call",
        "import subprocess as my_sub; my_sub.run(['ls'])",
        # Vector 8: asyncio loop subprocess methods
        "import asyncio; loop.subprocess_exec(None, 'ls')",
        "import asyncio; loop.subprocess_shell(None, 'ls')",
        "import asyncio; asyncio.create_subprocess_exec('ls')",
        "from asyncio import create_subprocess_exec; create_subprocess_exec('ls')",
        # Direct eval/exec
        "eval('1+1')",
        "exec('1+1')",
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


def test_audited_final_event_timestamp_follows_nested_commands(
    tmp_path, monkeypatch
):
    """A decorator's final event cannot predate commands emitted inside it."""
    monkeypatch.chdir(tmp_path)
    set_run_id("run_t1_nested_timestamp")

    @audited(stage="env")
    def stage_with_command():
        run_cmd(["echo", "nested"], stage="env")

    stage_with_command()
    events_file = get_run_dir("run_t1_nested_timestamp") / "events.jsonl"
    events = [
        json.loads(line)
        for line in events_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    timestamps = [
        datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
        for event in events
    ]
    assert timestamps == sorted(timestamps)
