"""Regression tests for the formal Phase T1 environment contract."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cortes.env import (
    ENVIRONMENT_CHECKS,
    run_environment_phase,
    summarize_environment_run,
    verify_environment_run,
)


PASSING_OUTPUTS = {
    "python3 --version": "Python 3.12.3\n",
    "ffmpeg -version": (
        "ffmpeg version 6.1 --enable-libass --enable-libfreetype\n"
    ),
    "ffprobe -version": "ffprobe version 6.1\n",
    'python3 -c "import soundfile"': "",
    'fc-list | grep -Eci "inter|roboto|noto"': "4\n",
    "nvidia-smi --query-gpu=name,memory.total --format=csv": (
        "name, memory.total [MiB]\nTesla T4, 15360 MiB\n"
    ),
    "df -B1G --output=avail . | tail -1": "20\n",
    "git --version": "git version 2.43.0\n",
}


def _passing_run_cmd(cmd, **_kwargs):
    command = cmd if isinstance(cmd, str) else " ".join(cmd)
    return SimpleNamespace(
        returncode=0,
        stdout=PASSING_OUTPUTS.get(command, ""),
        stderr="",
    )


def test_environment_phase_writes_all_literal_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("cortes.env.run_cmd", side_effect=_passing_run_cmd):
        phase = run_environment_phase("run_t1_test_all_pass")

    result = phase["result"]
    assert result["overall_passed"] is True
    assert len(result["checks"]) == 8
    assert [item["cmd"] for item in result["checks"]] == [
        check.cmd for check in ENVIRONMENT_CHECKS
    ]
    stored = json.loads(
        (tmp_path / "runs/run_t1_test_all_pass/env_check.json").read_text()
    )
    assert stored == result


def test_fonts_check_uses_regex_alternation() -> None:
    """The documented alternatives must not be treated as a literal pipe."""
    fonts = next(
        check for check in ENVIRONMENT_CHECKS
        if check.check_id == "fonts_available"
    )
    assert fonts.cmd == 'fc-list | grep -Eci "inter|roboto|noto"'


def test_environment_phase_retries_failure_and_records_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    soundfile_attempts = 0
    commands = []

    def fake_run(cmd, **kwargs):
        nonlocal soundfile_attempts
        command = cmd if isinstance(cmd, str) else " ".join(cmd)
        commands.append((command, kwargs.get("attempt")))
        if command == 'python3 -c "import soundfile"':
            soundfile_attempts += 1
            if soundfile_attempts == 1:
                return SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr="ModuleNotFoundError: soundfile\n",
                )
        return _passing_run_cmd(cmd, **kwargs)

    with patch("cortes.env.run_cmd", side_effect=fake_run):
        phase = run_environment_phase(
            "run_t1_test_install",
            install_missing=True,
        )

    assert phase["result"]["overall_passed"] is True
    assert soundfile_attempts == 2
    assert any("apt-get install --yes python3-soundfile" in cmd for cmd, _ in commands)
    history = phase["result"]["attempt_history"]
    assert [item["attempt"] for item in history if item["check_id"] == "soundfile_import"] == [1, 2]


def test_environment_phase_refuses_to_modify_existing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "runs/run_t1_existing"
    existing.mkdir(parents=True)
    (existing / "events.jsonl").write_text("{}\n")

    with pytest.raises(FileExistsError, match="Refusing to modify existing run"):
        run_environment_phase("run_t1_existing")


def test_verifier_rejects_tampered_declaration(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run_t1_verify"
    run_dir.mkdir()
    declared = {
        "checks": [
            {
                "check_id": check.check_id,
                "cmd": check.cmd,
                "stdout": PASSING_OUTPUTS[check.cmd],
                "exit_code": 0,
                "pass": True,
            }
            for check in ENVIRONMENT_CHECKS
        ]
    }
    declared["checks"][0]["cmd"] = "python --version"
    (run_dir / "env_check.json").write_text(json.dumps(declared))

    with patch("cortes.env.run_cmd", side_effect=_passing_run_cmd):
        result = verify_environment_run(run_dir)

    assert result["overall_passed"] is False
    failed = [check["check_id"] for check in result["checks"] if not check["passed"]]
    assert failed == ["python_version"]


def test_summary_preserves_recorded_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_t1_blocked"
    run_dir.mkdir()
    checks = [
        {
            "check_id": check.check_id,
            "cmd": check.cmd,
            "stdout": PASSING_OUTPUTS[check.cmd],
            "exit_code": 0,
            "pass": True,
        }
        for check in ENVIRONMENT_CHECKS
    ]
    fonts = next(item for item in checks if item["check_id"] == "fonts_available")
    fonts.update({"stdout": "0\n", "exit_code": 1, "pass": False})
    (run_dir / "env_check.json").write_text(json.dumps({"checks": checks}))

    result = summarize_environment_run(run_dir)

    assert result["overall_passed"] is False
    assert result["passed_checks"] == 7
    assert result["failed_checks"] == 1
