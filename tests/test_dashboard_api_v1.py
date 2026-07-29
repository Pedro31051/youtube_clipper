"""HTTP contracts for the persistent dashboard API introduced in UI-1."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

import youtube_clipper.web_dashboard as web_dashboard


YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _analysis_result() -> dict[str, Any]:
    return {
        "success": True,
        "total_segments": 3,
        "clips": [
            {
                "rank": 1,
                "start_time": 0.0,
                "end_time": 3.0,
                "duration": 3.0,
                "score": 92,
                "title": "Primeiro",
                "summary": "Vermelho",
                "transcript": "primeiro corte",
                "hashtags": ["#primeiro"],
                "start_timestamp": "00:00",
                "end_timestamp": "00:03",
            },
            {
                "rank": 2,
                "start_time": 3.0,
                "end_time": 6.0,
                "duration": 3.0,
                "score": 83,
                "title": "Segundo",
                "summary": "Verde",
                "transcript": "segundo corte",
                "hashtags": ["#segundo"],
                "start_timestamp": "00:03",
                "end_timestamp": "00:06",
            },
        ],
    }


def test_project_crud_and_analysis_job_persist_stable_clip_ids(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_dashboard,
        "extract_transcript_and_analyze",
        lambda *args, **kwargs: _analysis_result(),
    )

    status, created = _request(
        dashboard_server,
        "/api/v1/projects",
        method="POST",
        payload={
            "name": "Projeto persistente",
            "source": {"kind": "youtube", "uri": YOUTUBE_URL},
        },
    )
    assert status == 201
    project = created["project"]
    assert project["project_id"].startswith("prj_")
    assert project["sources"][0]["source_id"].startswith("src_")

    status, analyzed = _request(
        dashboard_server,
        f"/api/v1/projects/{project['project_id']}/analysis-jobs",
        method="POST",
        payload={},
    )
    assert status == 201
    assert analyzed["analysis_id"].startswith("anl_")
    assert analyzed["job"]["job_id"].startswith("job_")
    assert analyzed["job"]["state"] == "completed"
    clip_ids = [clip["clip_id"] for clip in analyzed["clips"]]
    assert len(clip_ids) == len(set(clip_ids)) == 2

    _, listed = _request(
        dashboard_server,
        f"/api/v1/projects/{project['project_id']}/clips",
    )
    assert [clip["clip_id"] for clip in listed["clips"]] == clip_ids

    _, fetched = _request(
        dashboard_server,
        f"/api/v1/clips/{clip_ids[0]}",
    )
    assert fetched["clip"]["rank"] == 1
    assert fetched["clip"]["plan_version"] == 1


def test_patch_clip_versions_plan_and_rejects_impossible_state(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_dashboard,
        "extract_transcript_and_analyze",
        lambda *args, **kwargs: _analysis_result(),
    )
    _, created = _request(
        dashboard_server,
        "/api/v1/projects",
        method="POST",
        payload={
            "name": "Projeto edição",
            "source": {"kind": "youtube", "uri": YOUTUBE_URL},
        },
    )
    project_id = created["project"]["project_id"]
    _, analyzed = _request(
        dashboard_server,
        f"/api/v1/projects/{project_id}/analysis-jobs",
        method="POST",
        payload={},
    )
    clip_id = analyzed["clips"][0]["clip_id"]

    status, changed = _request(
        dashboard_server,
        f"/api/v1/clips/{clip_id}",
        method="PATCH",
        payload={"start_ms": 200, "end_ms": 2800},
    )
    assert status == 200
    assert changed["clip"]["plan_version"] == 2
    assert changed["clip"]["duration_ms"] == 2600

    with pytest.raises(urllib.error.HTTPError) as error:
        _request(
            dashboard_server,
            f"/api/v1/clips/{clip_id}",
            method="PATCH",
            payload={"status": "exported"},
        )
    assert error.value.code == 409


def test_legacy_analyze_returns_persistent_identity(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_dashboard,
        "extract_transcript_and_analyze",
        lambda *args, **kwargs: _analysis_result(),
    )

    status, analyzed = _request(
        dashboard_server,
        "/api/analyze",
        method="POST",
        payload={"url": YOUTUBE_URL},
    )

    assert status == 200
    assert analyzed["project_id"].startswith("prj_")
    assert analyzed["source_id"].startswith("src_")
    assert analyzed["analysis_id"].startswith("anl_")
    assert all(clip["clip_id"].startswith("clp_") for clip in analyzed["clips"])
    assert all(clip["project_id"] == analyzed["project_id"] for clip in analyzed["clips"])

    _, persisted = _request(
        dashboard_server,
        f"/api/v1/projects/{analyzed['project_id']}/clips",
    )
    assert [clip["clip_id"] for clip in persisted["clips"]] == [
        clip["clip_id"] for clip in analyzed["clips"]
    ]
