"""Editorial transformation helpers shared by the T3 pipeline and verifier."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any, Dict, List, Sequence

from youtube_clipper.exceptions import ProcessingError


_VARIANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


def validate_template_variant(template_variant: str, *, allow_default: bool = False) -> str:
    """Validate and normalize a stable template variant identifier."""
    variant = str(template_variant or "").strip().lower()
    if not _VARIANT_RE.fullmatch(variant):
        raise ProcessingError(
            "template_variant must contain 3-64 lowercase letters, numbers, '_' or '-'"
        )
    if not allow_default and variant == "variant_default":
        raise ProcessingError(
            "T3 editorial renders require an explicit non-default template_variant"
        )
    return variant


def build_clip_id(selection_bytes: bytes, template_variant: str) -> str:
    """Bind the selected interval and template variant into the clip identifier."""
    variant = validate_template_variant(template_variant, allow_default=True)
    digest = hashlib.sha256(selection_bytes + b"\0" + variant.encode("utf-8")).hexdigest()
    return f"clip_{digest[:12]}"


def recent_template_records(
    runs_root: pathlib.Path,
    *,
    current_run_dir: pathlib.Path,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return the newest prior render metadata records under a runs directory."""
    current_root = current_run_dir.resolve()
    candidates = []
    seen_metadata_targets = set()
    if runs_root.exists():
        for metadata_path in runs_root.glob("*/artifacts/*/render_metadata.json"):
            resolved_metadata = metadata_path.resolve()
            if resolved_metadata in seen_metadata_targets:
                continue
            seen_metadata_targets.add(resolved_metadata)
            try:
                resolved_metadata.relative_to(current_root)
            except ValueError:
                pass
            else:
                continue
            candidates.append(metadata_path)

    records: List[Dict[str, Any]] = []
    for metadata_path in sorted(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, str(path)),
        reverse=True,
    ):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        variant = str(metadata.get("template_variant") or "").strip().lower()
        if not variant:
            continue
        records.append(
            {
                "run_id": metadata_path.parents[2].name,
                "clip_id": metadata.get("clip_id"),
                "template_variant": variant,
            }
        )
        if len(records) >= limit:
            break
    return records


def assert_variant_not_recent(
    template_variant: str,
    recent_records: Sequence[Dict[str, Any]],
) -> None:
    """Reject a template variant that appears in the previous five renders."""
    variant = validate_template_variant(template_variant)
    recent_variants = [
        str(record.get("template_variant") or "").strip().lower()
        for record in recent_records[:5]
    ]
    if variant in recent_variants:
        raise ProcessingError(
            f"template_variant '{variant}' was used in one of the previous five renders"
        )


def parse_loudnorm_measurement(stderr: str) -> Dict[str, str]:
    """Extract the final FFmpeg loudnorm JSON measurement block."""
    matches = re.findall(r"\{[\s\S]*?\"input_i\"[\s\S]*?\}", stderr or "")
    if not matches:
        raise ProcessingError("FFmpeg loudnorm preflight did not return measurement JSON")
    try:
        parsed = json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        raise ProcessingError("Invalid loudnorm measurement JSON") from exc
    return {str(key): str(value) for key, value in parsed.items()}
