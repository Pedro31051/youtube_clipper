"""Static and mathematical gates for the UI-6 design system."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "web/src/design-tokens.css"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _luminance(hex_color: str) -> float:
    channels = []
    for value in _rgb(hex_color):
        normalized = value / 255
        channels.append(
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(first: str, second: str) -> float:
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_graphite_cobalt_tokens_match_the_ui6_contract() -> None:
    source = TOKENS.read_text(encoding="utf-8").lower()
    required = {
        "--background": "#090b10",
        "--surface-1": "#11151d",
        "--surface-2": "#171c26",
        "--surface-3": "#202735",
        "--border": "#293244",
        "--text": "#f5f7fa",
        "--muted": "#98a2b3",
        "--primary": "#5b8cff",
        "--primary-hover": "#79a2ff",
        "--success": "#32d583",
        "--warning": "#f5b942",
        "--danger": "#f97066",
    }
    for token, color in required.items():
        assert f"{token}: {color}" in source


def test_primary_text_combinations_meet_wcag_aa() -> None:
    assert _contrast("#f5f7fa", "#090b10") >= 4.5
    assert _contrast("#98a2b3", "#11151d") >= 4.5
    assert _contrast("#07101f", "#5b8cff") >= 4.5


def test_ui6_has_semantic_states_keyboard_dialog_and_compact_mode() -> None:
    app = (ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    editor = (ROOT / "web/src/ClipEditor.tsx").read_text(encoding="utf-8")
    ui = (ROOT / "web/src/ui.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "web/src/styles.css").read_text(encoding="utf-8")

    assert 'className="skip-link"' in app
    assert 'role="dialog"' in editor and 'aria-modal="true"' in editor
    assert "ArrowLeft" in editor and "ArrowRight" in editor
    assert 'event.key === "Escape"' in editor
    assert 'data-ui-state="loading"' in ui
    assert 'data-ui-state="empty"' in ui
    assert "@media (max-width: 1180px)" in styles
    assert ".editor-candidates { display: none; }" in styles
    assert "backdrop-filter" not in styles


def test_ui6_review_artifacts_are_present_and_honest() -> None:
    phase = ROOT / "review/UI-6"
    decisions = (phase / "DECISOES.md").read_text(encoding="utf-8")
    limitations = (phase / "LIMITACOES.md").read_text(encoding="utf-8")
    system = (phase / "DESIGN_SYSTEM.md").read_text(encoding="utf-8")

    assert "Alternativa descartada" in decisions
    assert "snapshot" in limitations.lower()
    assert "agente não aprova" in system.lower()
