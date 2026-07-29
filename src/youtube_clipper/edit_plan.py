"""Typed, honest compilation boundary for dashboard edit plans."""

from __future__ import annotations

import math
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class EditPlanError(ValueError):
    """An edit plan cannot be represented by the supported physical renderer."""


class TimelinePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=1)
    duration_ms: int = Field(ge=1, le=59_900)

    @model_validator(mode="after")
    def validate_interval(self) -> "TimelinePlan":
        if self.end_ms <= self.start_ms:
            raise ValueError("timeline.end_ms must be greater than timeline.start_ms")
        if self.end_ms - self.start_ms != self.duration_ms:
            raise ValueError("timeline.duration_ms does not match the selected interval")
        return self


class LayoutPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["blur_background", "crop_center"] = "blur_background"
    crop_focus: Literal["left", "center", "right"] = "center"
    blur_sigma: float = 12.0
    overlay_position: Literal["top", "bottom"] = "top"

    @model_validator(mode="after")
    def validate_blur(self) -> "LayoutPlan":
        if not math.isfinite(self.blur_sigma) or not 0.0 <= self.blur_sigma <= 50.0:
            raise ValueError("layout.blur_sigma must be between 0 and 50")
        return self


class CaptionsPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    theme: Literal["classic", "solid", "highlight"] = "classic"
    position: Literal["bottom", "center", "top"] = "bottom"

    @model_validator(mode="after")
    def reject_unsupported_captions(self) -> "CaptionsPlan":
        if self.enabled:
            raise ValueError(
                "captions.enabled is not supported by the dashboard renderer"
            )
        return self


class AudioPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_source: bool = True
    normalize: bool = True
    narration_type: Literal["none", "external"] = "none"
    narration_path: Optional[str] = None

    @model_validator(mode="after")
    def reject_unsupported_narration(self) -> "AudioPlan":
        if self.narration_type != "none" or self.narration_path is not None:
            raise ValueError("dashboard narration is not supported")
        return self


class EditorialPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overlay_enabled: bool = False
    overlay_text: Optional[str] = Field(default=None, max_length=240)
    template_variant: Literal["variant_default"] = "variant_default"

    @model_validator(mode="after")
    def validate_overlay(self) -> "EditorialPlan":
        clean_text = self.overlay_text.strip() if self.overlay_text else None
        if self.overlay_enabled and not clean_text:
            raise ValueError(
                "editorial.overlay_text is required when overlay is enabled"
            )
        if not self.overlay_enabled and clean_text:
            raise ValueError(
                "editorial.overlay_text requires editorial.overlay_enabled=true"
            )
        self.overlay_text = clean_text
        return self


OUTPUT_DIMENSIONS: dict[str, tuple[str, tuple[int, int], tuple[int, int]]] = {
    "9:16": ("1080x1920", (360, 640), (1080, 1920)),
    "1:1": ("1080x1080", (480, 480), (1080, 1080)),
    "16:9": ("1920x1080", (640, 360), (1920, 1080)),
}
VALID_RESOLUTIONS: dict[str, dict[str, tuple[int, int]]] = {
    "9:16": {
        "720x1280": (720, 1280),
        "1080x1920": (1080, 1920),
    },
    "1:1": {"1080x1080": (1080, 1080)},
    "16:9": {"1920x1080": (1920, 1080)},
}


class OutputPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    resolution: str = "1080x1920"

    @model_validator(mode="after")
    def validate_resolution_for_aspect(self) -> "OutputPlan":
        valid = VALID_RESOLUTIONS[self.aspect_ratio]
        if self.resolution not in valid:
            choices = ", ".join(sorted(valid))
            raise ValueError(
                f"output.resolution {self.resolution!r} is incompatible with "
                f"aspect_ratio {self.aspect_ratio}; expected one of: {choices}"
            )
        return self


class EditPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    plan_version: int = Field(ge=1)
    clip_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    timeline: TimelinePlan
    layout: LayoutPlan = Field(default_factory=LayoutPlan)
    captions: CaptionsPlan = Field(default_factory=CaptionsPlan)
    audio: AudioPlan = Field(default_factory=AudioPlan)
    editorial: EditorialPlan = Field(default_factory=EditorialPlan)
    output: OutputPlan = Field(default_factory=OutputPlan)


class RenderRequest(BaseModel):
    """Fully resolved physical request; only encoding quality varies by profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: Literal["preview", "final"]
    plan_version: int = Field(ge=1)
    clip_id: str
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=1)
    duration_ms: int = Field(ge=1, le=59_900)
    layout_mode: Literal["blur_background", "crop_center"]
    crop_focus: Literal["left", "center", "right"]
    blur_sigma: float
    overlay_position: Literal["top", "bottom"]
    overlay_text: Optional[str]
    include_source_audio: bool
    normalize_audio: bool
    aspect_ratio: Literal["9:16", "1:1", "16:9"]
    requested_resolution: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    video_preset: str
    video_crf: int
    audio_bitrate: str
    applied_features: dict[str, Any]


def validate_edit_plan(
    raw_plan: dict[str, Any],
    *,
    clip_id: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> EditPlan:
    try:
        plan = EditPlan.model_validate(raw_plan)
    except ValidationError as exc:
        raise EditPlanError(str(exc)) from exc
    if clip_id is not None and plan.clip_id != clip_id:
        raise EditPlanError("edit plan clip_id does not match the persisted clip")
    if start_ms is not None and plan.timeline.start_ms != int(start_ms):
        raise EditPlanError("edit plan start_ms does not match the persisted clip")
    if end_ms is not None and plan.timeline.end_ms != int(end_ms):
        raise EditPlanError("edit plan end_ms does not match the persisted clip")
    return plan


def compile_edit_plan(
    raw_plan: dict[str, Any],
    *,
    profile: Literal["preview", "final"],
    clip_id: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> RenderRequest:
    """Validate and resolve one immutable edit-plan snapshot for rendering."""
    plan = validate_edit_plan(
        raw_plan,
        clip_id=clip_id,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    if profile == "preview":
        width, height = OUTPUT_DIMENSIONS[plan.output.aspect_ratio][1]
        preset, crf, audio_bitrate = "veryfast", 27, "96k"
    else:
        width, height = VALID_RESOLUTIONS[plan.output.aspect_ratio][
            plan.output.resolution
        ]
        preset, crf, audio_bitrate = "medium", 23, "192k"

    audio_mode = (
        "muted"
        if not plan.audio.include_source
        else "normalized_source"
        if plan.audio.normalize
        else "source"
    )
    applied_features: dict[str, Any] = {
        "timeline": True,
        "layout": plan.layout.mode,
        "audio": audio_mode,
        "overlay": bool(plan.editorial.overlay_enabled),
        "aspect_ratio": plan.output.aspect_ratio,
        "captions": False,
        "narration": False,
        "template": "variant_default",
    }
    return RenderRequest(
        profile=profile,
        plan_version=plan.plan_version,
        clip_id=plan.clip_id,
        source_id=plan.source_id,
        start_ms=plan.timeline.start_ms,
        end_ms=plan.timeline.end_ms,
        duration_ms=plan.timeline.duration_ms,
        layout_mode=plan.layout.mode,
        crop_focus=plan.layout.crop_focus,
        blur_sigma=plan.layout.blur_sigma,
        overlay_position=plan.layout.overlay_position,
        overlay_text=plan.editorial.overlay_text,
        include_source_audio=plan.audio.include_source,
        normalize_audio=plan.audio.normalize and plan.audio.include_source,
        aspect_ratio=plan.output.aspect_ratio,
        requested_resolution=plan.output.resolution,
        width=width,
        height=height,
        video_preset=preset,
        video_crf=crf,
        audio_bitrate=audio_bitrate,
        applied_features=applied_features,
    )
