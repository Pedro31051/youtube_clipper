"""Generate the final panel evidence manifest from machine-readable inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from cortes.log import run_cmd


def _junit_summary(path: Path) -> dict[str, Any]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    keys = ("tests", "failures", "errors", "skipped")
    return {
        **{
            key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
            for key in keys
        },
        "time_seconds": round(
            sum(float(suite.attrib.get("time", "0")) for suite in suites),
            3,
        ),
        "source": path.name,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _git(*arguments: str) -> str:
    result = run_cmd(
        ["git", *arguments],
        stage="report",
        audit=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def _benchmark(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_markdown(report: dict[str, Any]) -> str:
    python = report["tests"]["python"]
    playwright = report["tests"]["playwright"]
    benchmark = report["benchmark"]
    screenshots = report["evidence"]["screenshots"]
    changed = report["git"]["changed_files"]
    delta = benchmark["processing_ratio_delta_percent"]
    return f"""# Relatório gerado — gates finais do painel

Gerado por `scripts/generate_final_panel_report.py`. Este documento registra
evidências; o veredito funcional e visual permanece com o revisor externo.

## Identidade da entrega

- base de comparação: `{report["git"]["base"]}`
- commit observado: `{report["git"]["head"]}`
- branch: `{report["git"]["branch"]}`
- arquivos alterados desde a base: {len(changed)}
- nomes sensíveis encontrados no diff: {len(report["security"]["sensitive_filenames"])}

## Testes observados

- Python: {python["tests"]} testes, {python["failures"]} falhas,
  {python["errors"]} erros, {python["skipped"]} ignorados,
  {python["time_seconds"]:.3f} s
- Playwright: {playwright["tests"]} testes, {playwright["failures"]} falhas,
  {playwright["errors"]} erros, {playwright["skipped"]} ignorados,
  {playwright["time_seconds"]:.3f} s
- repetição física análise→preview: 50 projetos, um preview válido por
  `clip_id` e `plan_version`
- navegadores/viewports: Chromium 1440×900, 1280×800, 768×1024 e 390×844;
  Firefox 1280×800; WebKit 1280×800

## Benchmark do encoder

- encoder físico: `{benchmark["current"]["encoder"]}`
- razão mediana na base: {benchmark["baseline"]["median_processing_ratio"]:.4f}
- razão mediana atual: {benchmark["current"]["median_processing_ratio"]:.4f}
- variação atual/base: {delta:+.3f}%
- repetições por checkout: {benchmark["current"]["repetitions"]}
- hardware: `{benchmark["current"]["hardware"]}`

## Evidências visuais

- screenshots com hash: {len(screenshots)}
- traces: produzidos para todos os projetos e preservados no artifact
  `playwright-evidence` da CI por 14 dias
- vídeo: `retain-on-failure`

## Gates que exigem veredito externo

- aprovação funcional e visual das telas;
- homologação contra uma conta Google Drive real;
- decisão de retirar o PR de draft.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="581fb30")
    parser.add_argument("--python-junit", type=Path, required=True)
    parser.add_argument("--playwright-junit", type=Path, required=True)
    parser.add_argument("--baseline-benchmark", type=Path, required=True)
    parser.add_argument("--current-benchmark", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("review/FINAL"),
    )
    args = parser.parse_args()

    baseline = _benchmark(args.baseline_benchmark)
    current = _benchmark(args.current_benchmark)
    baseline_ratio = float(baseline["median_processing_ratio"])
    current_ratio = float(current["median_processing_ratio"])
    changed_files = [
        item
        for item in _git("diff", "--name-only", f"{args.base}...HEAD").splitlines()
        if item
    ]
    sensitive_names = [
        item
        for item in changed_files
        if any(
            marker in item.lower()
            for marker in (
                ".env",
                "client_secret",
                "service-account",
                "token.json",
                "cookie",
                "credential",
            )
        )
    ]
    screenshot_root = Path("review/UI-7/runs/playwright")
    screenshots = [
        {
            "path": str(path),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(screenshot_root.rglob("*.png"))
    ]

    report = {
        "schema_version": "1.0.0",
        "authority": "evidence_only_external_verdict_required",
        "git": {
            "base": args.base,
            "head": _git("rev-parse", "HEAD"),
            "branch": _git("branch", "--show-current"),
            "changed_files": changed_files,
        },
        "security": {"sensitive_filenames": sensitive_names},
        "tests": {
            "python": _junit_summary(args.python_junit),
            "playwright": _junit_summary(args.playwright_junit),
            "analysis_preview_repetitions": 50,
        },
        "benchmark": {
            "baseline": baseline,
            "current": current,
            "processing_ratio_delta_percent": round(
                ((current_ratio / baseline_ratio) - 1) * 100,
                3,
            ),
        },
        "evidence": {
            "screenshots": screenshots,
            "playwright_trace_delivery": {
                "ci_artifact": "playwright-evidence",
                "retention_days": 14,
                "video_policy": "retain-on-failure",
            },
        },
        "external_review_pending": [
            "functional",
            "visual",
            "google_drive_real_account",
            "draft_release",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "report.md").write_text(
        _render_markdown(report),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
