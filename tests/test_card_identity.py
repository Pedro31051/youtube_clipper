"""Static contract that cards propagate persistent identity independently of rank."""

from youtube_clipper.web_dashboard import HTML_TEMPLATE


def _section(start: str, end: str) -> str:
    start_at = HTML_TEMPLATE.index(start)
    end_at = HTML_TEMPLATE.index(end, start_at)
    return HTML_TEMPLATE[start_at:end_at]


def test_rendered_cards_store_persistent_domain_ids() -> None:
    render_clips = _section(
        "function renderClips(clips, videoUrl)",
        "function toggleGeminiChat",
    )

    assert "const clipId = String(clip.clip_id" in render_clips
    assert "card.dataset.clipId = clipId" in render_clips
    assert "card.dataset.projectId = projectId" in render_clips
    assert "card.dataset.analysisId = analysisId" in render_clips
    assert "clip_id: clipId" in render_clips


def test_generate_clip_reads_identity_from_the_selected_card() -> None:
    generate = _section(
        "async function generateClip(videoUrl, rank, button)",
        "async function uploadExistingToDrive",
    )

    assert "const card = document.getElementById(`card-${rank}`)" in generate
    assert "clip_id: card?.dataset.clipId || null" in generate
    assert "project_id: card?.dataset.projectId || null" in generate
    assert "analysis_id: card?.dataset.analysisId || null" in generate
