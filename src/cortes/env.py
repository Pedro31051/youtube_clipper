"""Phase T1 environment checks and independent re-verification."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Sequence

from cortes.log import audited, run_cmd, set_run_id


@dataclass(frozen=True)
class EnvironmentCheck:
    """One literal T1 command and its acceptance predicate."""

    check_id: str
    cmd: str
    predicate: Callable[[int, str], bool]


def _version_at_least_3_11(exit_code: int, stdout: str) -> bool:
    match = re.search(r"Python\s+(\d+)\.(\d+)", stdout)
    return bool(
        exit_code == 0
        and match
        and (int(match.group(1)), int(match.group(2))) >= (3, 11)
    )


def _ffmpeg_has_required_libraries(exit_code: int, stdout: str) -> bool:
    return (
        exit_code == 0
        and "--enable-libass" in stdout
        and "--enable-libfreetype" in stdout
    )


def _exit_zero(exit_code: int, _stdout: str) -> bool:
    return exit_code == 0


def _integer_at_least(minimum: int) -> Callable[[int, str], bool]:
    def predicate(exit_code: int, stdout: str) -> bool:
        try:
            return exit_code == 0 and int(stdout.strip()) >= minimum
        except ValueError:
            return False

    return predicate


ENVIRONMENT_CHECKS: Sequence[EnvironmentCheck] = (
    EnvironmentCheck("python_version", "python3 --version", _version_at_least_3_11),
    EnvironmentCheck(
        "ffmpeg_libraries",
        "ffmpeg -version",
        _ffmpeg_has_required_libraries,
    ),
    EnvironmentCheck("ffprobe_available", "ffprobe -version", _exit_zero),
    EnvironmentCheck(
        "soundfile_import",
        'python3 -c "import soundfile"',
        _exit_zero,
    ),
    EnvironmentCheck(
        "fonts_available",
        'fc-list | grep -ci "inter|roboto|noto"',
        _integer_at_least(1),
    ),
    EnvironmentCheck(
        "nvidia_gpu",
        "nvidia-smi --query-gpu=name,memory.total --format=csv",
        _exit_zero,
    ),
    EnvironmentCheck(
        "disk_available_gib",
        "df -B1G --output=avail . | tail -1",
        _integer_at_least(20),
    ),
    EnvironmentCheck("git_available", "git --version", _exit_zero),
)

INSTALLABLE_CHECKS: Dict[str, str] = {
    "soundfile_import": "python3-soundfile",
    "fonts_available": "fonts-noto-core",
}


def _run_one(
    check: EnvironmentCheck,
    *,
    attempt: int,
    audit: bool,
    agent: str,
) -> Dict[str, Any]:
    proc = run_cmd(
        check.cmd,
        stage="env",
        agent=agent,
        attempt=attempt,
        audit=audit,
    )
    return {
        "check_id": check.check_id,
        "cmd": check.cmd,
        "stdout": proc.stdout,
        "exit_code": proc.returncode,
        "pass": check.predicate(proc.returncode, proc.stdout),
    }


def _validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"run_t1_[A-Za-z0-9_-]+", run_id):
        raise ValueError("T1 run_id must match run_t1_[A-Za-z0-9_-]+")


@audited(stage="env", agent="worker_t1")
def _execute_environment_phase(
    run_id: str,
    *,
    install_missing: bool = False,
    agent: str = "worker_t1",
) -> Dict[str, Any]:
    """Execute checks after the public entry point reserves a fresh run."""
    run_dir = pathlib.Path("runs") / run_id
    first_attempt = [
        _run_one(check, attempt=1, audit=True, agent=agent)
        for check in ENVIRONMENT_CHECKS
    ]
    failed_ids = {
        result["check_id"] for result in first_attempt if not result["pass"]
    }
    history: List[Dict[str, Any]] = [
        {**result, "attempt": 1} for result in first_attempt
    ]
    final_by_id = {result["check_id"]: result for result in first_attempt}

    packages = sorted(
        {
            INSTALLABLE_CHECKS[check_id]
            for check_id in failed_ids
            if check_id in INSTALLABLE_CHECKS
        }
    )
    if install_missing and packages:
        run_cmd(
            ["sudo", "-n", "apt-get", "update"],
            stage="env",
            agent=agent,
            attempt=1,
        )
        run_cmd(
            ["sudo", "-n", "apt-get", "install", "--yes", *packages],
            stage="env",
            agent=agent,
            attempt=1,
        )

    if failed_ids:
        for check in ENVIRONMENT_CHECKS:
            if check.check_id not in failed_ids:
                continue
            second = _run_one(check, attempt=2, audit=True, agent=agent)
            history.append({**second, "attempt": 2})
            final_by_id[check.check_id] = second

    final_checks = [
        final_by_id[check.check_id] for check in ENVIRONMENT_CHECKS
    ]
    result = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "overall_passed": all(item["pass"] for item in final_checks),
        "checks": final_checks,
        "attempt_history": history,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "env_check.json"
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"result": result, "evidence_paths": [str(output_path)]}


def run_environment_phase(
    run_id: str,
    *,
    install_missing: bool = False,
    agent: str = "worker_t1",
) -> Dict[str, Any]:
    """Reserve a fresh immutable run and execute the audited T1 phase."""
    _validate_run_id(run_id)
    run_dir = pathlib.Path("runs") / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Refusing to modify existing run: {run_dir}")
    set_run_id(run_id)
    return _execute_environment_phase(
        run_id,
        install_missing=install_missing,
        agent=agent,
    )


def verify_environment_run(
    run_dir: pathlib.Path | str,
    *,
    agent: str = "auditor_t1",
) -> Dict[str, Any]:
    """Re-run all literal checks without mutating the supplied run."""
    run_path = pathlib.Path(run_dir).resolve()
    env_file = run_path / "env_check.json"
    declared: Dict[str, Any] = {}
    if env_file.exists():
        declared = json.loads(env_file.read_text(encoding="utf-8"))
    declared_by_id = {
        item.get("check_id"): item for item in declared.get("checks", [])
    }

    checks: List[Dict[str, Any]] = []
    for specification in ENVIRONMENT_CHECKS:
        measured = _run_one(
            specification,
            attempt=1,
            audit=False,
            agent=agent,
        )
        declared_item = declared_by_id.get(specification.check_id)
        declared_consistent = bool(
            declared_item
            and declared_item.get("cmd") == specification.cmd
            and declared_item.get("pass") is True
            and specification.predicate(
                declared_item.get("exit_code", -1),
                declared_item.get("stdout", ""),
            )
        )
        passed = bool(measured["pass"] and declared_consistent)
        checks.append(
            {
                "check_id": specification.check_id,
                "passed": passed,
                "measured": measured["stdout"].strip(),
                "expected": (
                    "literal command passes and env_check.json declares the same command"
                ),
                "evidence_path": "env_check.json",
            }
        )

    passed_count = sum(1 for check in checks if check["passed"])
    return {
        "schema_version": "1.0.0",
        "run_id": run_path.name,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "overall_passed": passed_count == len(checks),
        "total_checks": len(checks),
        "passed_checks": passed_count,
        "failed_checks": len(checks) - passed_count,
        "checks": checks,
    }


def summarize_environment_run(run_dir: pathlib.Path | str) -> Dict[str, Any]:
    """Convert the final recorded attempts into a deterministic blocked verdict."""
    run_path = pathlib.Path(run_dir).resolve()
    env_file = run_path / "env_check.json"
    declared = json.loads(env_file.read_text(encoding="utf-8"))
    events_file = run_path / "events.jsonl"
    event_rows = (
        [
            json.loads(line)
            for line in events_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if events_file.exists()
        else []
    )
    declared_by_id = {
        item.get("check_id"): item for item in declared.get("checks", [])
    }
    checks: List[Dict[str, Any]] = []
    for specification in ENVIRONMENT_CHECKS:
        item = declared_by_id.get(specification.check_id, {})
        passed = bool(
            item.get("cmd") == specification.cmd
            and specification.predicate(
                item.get("exit_code", -1),
                item.get("stdout", ""),
            )
            and item.get("pass") is True
        )
        checks.append(
            {
                "check_id": specification.check_id,
                "passed": passed,
                "measured": item.get("stdout", "").strip() or "(empty stdout)",
                "expected": "recorded final attempt satisfies the T1 criterion",
                "evidence_path": "env_check.json",
            }
        )

    passed_count = sum(1 for check in checks if check["passed"])
    return {
        "schema_version": "1.0.0",
        "run_id": run_path.name,
        "verified_at": (
            max(
                event_rows,
                key=lambda item: datetime.fromisoformat(
                    item["ts"].replace("Z", "+00:00")
                ),
            )["ts"]
            if event_rows
            else "N/A"
        ),
        "overall_passed": passed_count == len(checks),
        "total_checks": len(checks),
        "passed_checks": passed_count,
        "failed_checks": len(checks) - passed_count,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute or verify Phase T1")
    parser.add_argument("--run-id")
    parser.add_argument("--install-missing", action="store_true")
    parser.add_argument("--verify", type=pathlib.Path)
    parser.add_argument("--summarize", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    if args.verify or args.summarize:
        source = args.verify or args.summarize
        result = (
            verify_environment_run(source)
            if args.verify
            else summarize_environment_run(source)
        )
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        raise SystemExit(0 if result["overall_passed"] else 1)

    if not args.run_id:
        parser.error("--run-id is required for phase execution")
    phase = run_environment_phase(
        args.run_id,
        install_missing=args.install_missing,
    )
    print(json.dumps(phase["result"], indent=2, ensure_ascii=False))
    raise SystemExit(0 if phase["result"]["overall_passed"] else 1)


if __name__ == "__main__":
    main()
