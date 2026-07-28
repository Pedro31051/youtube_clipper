"""Static UI-7 scope gates."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ui7_exposes_operational_routes_and_persistent_events() -> None:
    api = (ROOT / "src/youtube_clipper/api.py").read_text(encoding="utf-8")
    store = (ROOT / "src/youtube_clipper/project_store.py").read_text(
        encoding="utf-8"
    )

    for route in (
        "/api/v1/jobs/{job_id}/cancel",
        "/api/v1/jobs/{job_id}/retry",
        "/api/v1/jobs/{job_id}/report",
        "/api/v1/clips/{clip_id}/export/download",
        "/api/v1/clips/{clip_id}/drive-jobs",
    ):
        assert route in api
    assert "CREATE TABLE IF NOT EXISTS job_events" in store
    assert "Content-Disposition" in api
    assert "_stream_file" in api


def test_ui7_screen_contains_jobs_logs_timing_and_safe_export_dialog() -> None:
    screen = (ROOT / "web/src/JobsExportPanel.tsx").read_text(encoding="utf-8")

    for label in (
        "Jobs e exportações",
        "Tempo",
        "Estimativa",
        "Tentar novamente",
        "Cancelar",
        "Baixar MP4",
        "Enviar ao Drive",
        "Relatório",
    ):
        assert label in screen
    assert 'role="dialog"' in screen
    assert "alert(" not in screen


def test_ui7_phase_has_required_homologation_artifacts() -> None:
    phase = ROOT / "review/UI-7"
    decisions = (phase / "DECISOES.md").read_text(encoding="utf-8")
    limitations = (phase / "LIMITACOES.md").read_text(encoding="utf-8")
    contract = (phase / "CONTRATO_OPERACIONAL.md").read_text(encoding="utf-8")

    assert "Alternativa descartada" in decisions
    assert "Google Drive" in limitations
    assert "agente não aprova" in contract
