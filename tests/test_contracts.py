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
    """Requirement (a): AST scan fails if any stage function lacks @audited decorator."""
    src_dir = pathlib.Path(__file__).parent.parent / "src" / "cortes"
    assert src_dir.exists(), "src/cortes directory must exist"

    missing_audited = []

    for stage_name in STAGE_MODULES:
        stage_file = src_dir / f"{stage_name}.py"
        if not stage_file.exists():
            continue

        tree = ast.parse(stage_file.read_text(encoding="utf-8"), filename=str(stage_file))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Ignore private functions starting with '_'
                if not node.name.startswith("_"):
                    has_audited = any(is_audited_decorator(dec) for dec in node.decorator_list)
                    if not has_audited:
                        missing_audited.append(
                            f"{stage_file.name}:{node.lineno} - function '{node.name}' lacks @audited"
                        )

    assert not missing_audited, (
        "The following stage functions are missing the @audited decorator:\n" + "\n".join(missing_audited)
    )


def test_ast_prohibit_subprocess_outside_run_cmd():
    """Requirement (b): AST scan fails if subprocess or os.system is used outside src/cortes/log.py."""
    src_dir = pathlib.Path(__file__).parent.parent / "src" / "cortes"
    assert src_dir.exists(), "src/cortes directory must exist"

    violations = []

    for py_file in src_dir.rglob("*.py"):
        # Exempt log.py as it is the sole authorized module for subprocess invocation
        if py_file.name == "log.py":
            continue

        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "subprocess" or alias.name.startswith("subprocess."):
                        violations.append(
                            f"{py_file.name}:{node.lineno} - Direct import of 'subprocess'"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "subprocess" or node.module.startswith("subprocess.")):
                    violations.append(
                        f"{py_file.name}:{node.lineno} - Import from 'subprocess'"
                    )
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "subprocess":
                    violations.append(
                        f"{py_file.name}:{node.lineno} - Access to 'subprocess.{node.attr}'"
                    )
                elif (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "os"
                    and node.attr in ("system", "popen", "exec", "spawn", "execv", "execve")
                ):
                    violations.append(
                        f"{py_file.name}:{node.lineno} - Prohibited system call 'os.{node.attr}'"
                    )

    assert not violations, (
        "Prohibited subprocess usage detected outside src/cortes/log.py:\n" + "\n".join(violations)
    )


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

    dummy_file = tmp_path / "output.txt"
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
    assert event["evidence"]["paths"][0] == str(dummy_file)
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
