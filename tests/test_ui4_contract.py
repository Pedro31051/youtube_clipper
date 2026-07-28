"""Static scope and identity gates for the UI-4 review surface."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_review_surface_is_clip_id_based_and_does_not_leak_ui5_tools() -> None:
    app = (ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    client = (ROOT / "web/src/api/client.ts").read_text(encoding="utf-8")
    package = (ROOT / "web/package.json").read_text(encoding="utf-8")

    assert "key={clip.clip_id}" in app
    assert "clipIds: [clip.clip_id]" in app
    assert "poster_url" in app
    assert "preview_url" in app
    assert "/api/v1/clips/review" in client
    assert "wavesurfer" not in package
    assert "rank}" not in client


def test_ui4_phase_documents_decisions_and_nonempty_limitations() -> None:
    phase = ROOT / "review/UI-4"
    decisions = (phase / "DECISOES.md").read_text(encoding="utf-8")
    limitations = (phase / "LIMITACOES.md").read_text(encoding="utf-8")
    contract = (phase / "CONTRATO_REVISAO.md").read_text(encoding="utf-8")

    assert "Alternativa descartada" in decisions
    assert len(limitations.splitlines()) > 8
    assert "não constitui" in contract
