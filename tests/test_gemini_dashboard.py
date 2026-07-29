"""Offline endpoint coverage for the Gemini-assisted clip editor."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAusB9Y9ZkXcAAAAASUVORK5CYII="
)
VALID_MP3 = b"ID3" + b"\x04\x00\x00" + b"\x00" * 32
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _post_json(
    dashboard_server: str, path: str, payload: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{dashboard_server}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _asset_payload(
    *,
    kind: str = "intro_image",
    file_name: str = "intro.png",
    mime_type: str = "image/png",
    content: bytes = VALID_PNG,
    rights_confirmed: bool = True,
) -> dict[str, Any]:
    encoded = base64.b64encode(content).decode("ascii")
    return {
        "kind": kind,
        "file_name": file_name,
        "mime_type": mime_type,
        "data_base64": f"data:{mime_type};base64,{encoded}",
        "rights_confirmed": rights_confirmed,
    }


def _upload_asset(
    dashboard_server: str, **overrides: Any
) -> dict[str, Any]:
    payload = _asset_payload(**overrides)
    status, response = _post_json(
        dashboard_server, "/api/editor-assets", payload
    )
    assert status == 201, response
    assert response["success"] is True
    return response


def _generate_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": YOUTUBE_URL,
        "start": 10.0,
        "end": 20.0,
        "format": "blur_background",
        "include_audio": True,
        "overlay_text": "Contexto essencial confirmado",
        "confirmed_configuration": True,
    }
    payload.update(overrides)
    return payload


def test_dashboard_html_contains_gemini_chat_and_model(
    dashboard_server: str,
) -> None:
    with urllib.request.urlopen(f"{dashboard_server}/") as response:
        assert response.status == 200
        html = response.read().decode("utf-8")

    assert 'class="gemini-chat"' in html
    assert 'data-action="gemini-send"' in html
    assert "/api/editor-chat" in html
    assert "Gemini 3.6 Flash" in html


def test_editor_chat_success_uses_server_boundary(
    dashboard_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_request_gemini_edit(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "reply": "Ajustei o enquadramento e pedi uma trilha.",
            "patch": {"format": "crop_center", "crop_focus": "right"},
            "needs_asset": ["music"],
            "model": "gemini-3.6-flash",
        }

    monkeypatch.setattr(
        "youtube_clipper.web_dashboard.request_gemini_edit",
        fake_request_gemini_edit,
    )
    payload = {
        "message": "Use crop à direita e uma trilha discreta.",
        "clip": {"start": 10.0, "end": 20.0, "transcript": "Trecho"},
        "config": {"format": "blur_background", "include_audio": True},
        "history": [{"role": "user", "content": "Deixe mais dinâmico."}],
    }

    status, response = _post_json(
        dashboard_server, "/api/editor-chat", payload
    )

    assert status == 200
    assert response["success"] is True
    assert response["patch"] == {
        "format": "crop_center",
        "crop_focus": "right",
    }
    assert response["needs_asset"] == ["music"]
    assert captured == {
        "message": payload["message"],
        "clip": payload["clip"],
        "config": payload["config"],
        "history": payload["history"],
    }


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({"Content-Type": "text/plain"}, 415),
        (
            {
                "Content-Type": "application/json",
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
            403,
        ),
    ],
)
def test_post_rejects_non_json_and_cross_origin_requests(
    dashboard_server: str,
    headers: dict[str, str],
    expected_status: int,
) -> None:
    request = urllib.request.Request(
        f"{dashboard_server}/api/editor-chat",
        data=json.dumps(
            {
                "message": "Dispare uma chamada paga.",
                "clip": {},
                "config": {},
                "history": [],
            }
        ).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(request)

    assert exc_info.value.code == expected_status
    response = json.loads(exc_info.value.read().decode("utf-8"))
    assert response["success"] is False


def test_editor_chat_without_api_key_is_offline_503(
    dashboard_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    status, response = _post_json(
        dashboard_server,
        "/api/editor-chat",
        {
            "message": "Deixe o corte mais rápido.",
            "clip": {},
            "config": {},
            "history": [],
        },
    )

    assert status == 503
    assert response["success"] is False
    assert "GEMINI_API_KEY" in response["error"]


def test_valid_png_upload_returns_opaque_id_without_leaking_content(
    dashboard_server: str,
) -> None:
    response = _upload_asset(dashboard_server)

    asset_id = response["asset_id"]
    assert re.fullmatch(r"asset_[a-f0-9]{32}\.png", asset_id)
    assert response["file_name"] == "intro.png"
    assert response["mime_type"] == "image/png"
    assert response["size_bytes"] == len(VALID_PNG)
    serialized = json.dumps(response)
    assert "data_base64" not in serialized
    assert "asset_path" not in serialized
    assert str(Path.cwd()) not in serialized

    stored = (
        Path.cwd() / "media_workspace" / "_editor_assets" / asset_id
    ).resolve()
    assert stored.is_file()
    assert stored.read_bytes() == VALID_PNG


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (_asset_payload(rights_confirmed=False), "rights_confirmed"),
        (
            {
                **_asset_payload(),
                "data_base64": "data:image/png;base64,%%%",
            },
            "data_base64",
        ),
        (
            _asset_payload(content=b"GIF89a-not-a-png"),
            "data_base64",
        ),
    ],
)
def test_asset_upload_rejects_rights_base64_and_signature(
    dashboard_server: str, payload: dict[str, Any], field: str
) -> None:
    status, response = _post_json(
        dashboard_server, "/api/editor-assets", payload
    )

    assert status == 400
    assert response["success"] is False
    assert response["field"] == field


def test_asset_upload_respects_persistent_storage_quota(
    dashboard_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "youtube_clipper.web_dashboard.ClipperDashboardHandler.MAX_EDITOR_ASSET_FILES",
        0,
    )

    status, response = _post_json(
        dashboard_server, "/api/editor-assets", _asset_payload()
    )

    assert status == 400
    assert response["field"] == "data_base64"
    assert "quota" in response["error"].lower()


def test_generate_resolves_asset_ids_and_passes_composition_options(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    music = _upload_asset(
        dashboard_server,
        kind="music",
        file_name="track.mp3",
        mime_type="audio/mpeg",
        content=VALID_MP3,
    )
    intro = _upload_asset(dashboard_server)
    captured: dict[str, Any] = {}

    def fake_run_pipeline(**kwargs: Any) -> str:
        captured.update(kwargs)
        output = Path(kwargs["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mock-mp4" * 256)
        return str(output)

    monkeypatch.setattr(
        "youtube_clipper.web_dashboard.run_pipeline", fake_run_pipeline
    )
    monkeypatch.setattr(
        "youtube_clipper.web_dashboard.probe_video_metadata",
        lambda _path: {
            "duration": 12.5,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "video_codec": "h264",
            "audio_codec": "aac",
            "audio_channels": 2,
            "file_size": 2048,
            "sha256": "sha256:test",
        },
    )

    status, response = _post_json(
        dashboard_server,
        "/api/generate-clip",
        _generate_payload(
            background_music_asset_id=music["asset_id"],
            background_music_volume=0.35,
            intro_image_asset_id=intro["asset_id"],
            intro_duration=2.5,
        ),
    )

    assert status == 200, response
    asset_dir = (
        Path.cwd() / "media_workspace" / "_editor_assets"
    ).resolve()
    assert captured["background_music_path"] == (
        asset_dir / music["asset_id"]
    ).resolve()
    assert captured["background_music_volume"] == 0.35
    assert captured["intro_image_path"] == (
        asset_dir / intro["asset_id"]
    ).resolve()
    assert captured["intro_duration"] == 2.5
    assert captured["include_audio"] is True
    assert captured["vertical"] is True

    settings = response["render_receipt"]["applied_settings"]
    assert settings["background_music"] == {
        "included": True,
        "asset_id": music["asset_id"],
        "volume": 0.35,
    }
    assert settings["intro_image"] == {
        "included": True,
        "asset_id": intro["asset_id"],
        "duration_seconds": 2.5,
    }
    assert settings["final_duration_seconds"] == 12.5


def test_generate_rejects_clip_plus_intro_over_59_9_seconds(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intro = _upload_asset(dashboard_server)
    called = False

    def fail_if_called(**_kwargs: Any) -> str:
        nonlocal called
        called = True
        raise AssertionError("run_pipeline must not run for an invalid duration")

    monkeypatch.setattr(
        "youtube_clipper.web_dashboard.run_pipeline", fail_if_called
    )

    status, response = _post_json(
        dashboard_server,
        "/api/generate-clip",
        _generate_payload(
            start=0.0,
            end=58.0,
            intro_image_asset_id=intro["asset_id"],
            intro_duration=2.0,
        ),
    )

    assert status == 400
    assert response["success"] is False
    assert "59.9" in response["error"]
    assert called is False
