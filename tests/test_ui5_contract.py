"""Static UI-5 scope gates."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_editor_has_real_plan_waveform_history_and_job_boundaries() -> None:
    editor = (ROOT / "web/src/ClipEditor.tsx").read_text(encoding="utf-8")
    store = (ROOT / "web/src/editorStore.ts").read_text(encoding="utf-8")
    client = (ROOT / "web/src/api/client.ts").read_text(encoding="utf-8")
    package = (ROOT / "web/package.json").read_text(encoding="utf-8")

    for tab in ("Corte", "Layout", "Legendas", "Áudio", "Editorial", "Saída"):
        assert f'"{tab}"' in editor
    assert "expectedPlanVersion" in client
    assert "/edit-plan" in client
    assert "/render-jobs" in client
    assert "past:" in store and "future:" in store
    assert "wavesurfer.js" in package
    assert "zustand" in package


def test_ui5_has_required_decisions_and_honest_limitations() -> None:
    phase = ROOT / "review/UI-5"
    decisions = (phase / "DECISOES.md").read_text(encoding="utf-8")
    limitations = (phase / "LIMITACOES.md").read_text(encoding="utf-8")
    contract = (phase / "CONTRATO_EDITOR.md").read_text(encoding="utf-8")

    assert "Alternativa descartada" in decisions
    assert "não aceita" in limitations
    assert "agente não aprova" in contract
