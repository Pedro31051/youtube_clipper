"""Compare like-for-like encoder benchmarks and emit an auditable result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path, key: str | None) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value["benchmark"][key] if key else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-key")
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--max-regression-percent", type=float, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = _load(args.baseline, args.baseline_key)
    current = _load(args.current, None)
    if baseline["encoder"] != current["encoder"]:
        raise SystemExit("encoder mismatch; refusing an invalid comparison")
    delta = (
        float(current["median_processing_ratio"])
        / float(baseline["median_processing_ratio"])
        - 1
    ) * 100
    result = {
        "schema_version": "1.0.0",
        "source_sha": args.source_sha,
        "encoder": current["encoder"],
        "hardware": current["hardware"],
        "baseline_hardware": baseline["hardware"],
        "processing_ratio_delta_percent": round(delta, 3),
        "max_regression_percent": args.max_regression_percent,
        "passed": delta <= args.max_regression_percent,
        "baseline": baseline,
        "current": current,
    }
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
