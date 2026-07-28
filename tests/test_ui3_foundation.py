"""Static gates for the UI-3 React/FastAPI boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_python_dashboard_contains_no_embedded_ui_document() -> None:
    source = (ROOT / "src/youtube_clipper/web_dashboard.py").read_text(
        encoding="utf-8"
    )

    assert "<!DOCTYPE html>" not in source
    assert "<script>" not in source
    assert 'read_text(encoding="utf-8")' in source
    assert (ROOT / "src/youtube_clipper/templates/legacy_dashboard.html").is_file()
    assert (ROOT / "src/youtube_clipper/templates/legacy_technical.html").is_file()


def test_frontend_build_is_openapi_first_and_ci_enforced() -> None:
    package = (ROOT / "web/package.json").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    generated = (ROOT / "web/src/api/schema.d.ts").read_text(encoding="utf-8")

    assert "export_openapi.py" in package
    assert "openapi-typescript" in package
    assert "npm run generate:api" in workflow
    assert "npx tsc --noEmit" in workflow
    assert "npm test" in workflow
    assert "npx vite build" in workflow
    assert "npm run test:e2e" in workflow
    assert "YouTube Clipper API" not in generated
    assert "ProjectsResponse" in generated


def test_react_shell_uses_server_state_and_real_event_source() -> None:
    app = (ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    events = (ROOT / "web/src/hooks/useJobEvents.ts").read_text(
        encoding="utf-8"
    )

    assert "useQuery" in app
    assert "EventSource(" in events
    assert "/events" in events
    assert "localStorage" not in app
    assert "setInterval" not in events
