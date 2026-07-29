"""Static UI contract for the self-contained preview in every cut card.

These tests deliberately do not start a browser or contact YouTube.  They make
the dashboard template keep the important per-card wiring explicit: a private
YouTube source iframe, a private MP4 player, safe embed URL construction, and
refreshing the card preview when its interval changes.
"""

from __future__ import annotations

from youtube_clipper.web_dashboard import HTML_TEMPLATE


def _template_section(start: str, end: str) -> str:
    """Return the stable template section bounded by two unique function names."""
    start_at = HTML_TEMPLATE.index(start)
    end_at = HTML_TEMPLATE.index(end, start_at)
    return HTML_TEMPLATE[start_at:end_at]


def test_each_rendered_cut_card_owns_source_and_output_preview_elements() -> None:
    """A card must be independently playable before and after rendering its MP4."""
    render_clips = _template_section(
        "function renderClips(clips, videoUrl)",
        "function toggleGeminiChat",
    )

    assert '<section class="card-preview" aria-label="Prévia do corte ${rank}">' in render_clips
    assert 'id="clipSuggestionPlaceholder-${rank}"' in render_clips
    assert 'id="clipSourcePreview-${rank}"' in render_clips
    assert 'title="Prévia da sugestão ${rank}"' in render_clips
    assert 'id="clipOutputPreview-${rank}"' in render_clips
    assert 'Sugestão #${rank} pronta' in render_clips
    assert '▶ Reproduzir sugestão #${rank}' in render_clips
    assert 'data-action="play-card-preview"' in render_clips
    assert 'loading="lazy"' in render_clips
    assert 'referrerpolicy="strict-origin-when-cross-origin"' in render_clips
    assert "setCardSourcePreview(rank);" in render_clips
    assert "playCardPreview(rank);" in render_clips


def test_card_source_preview_uses_validated_nocookie_embed_and_interval() -> None:
    """The card iframe must never receive an arbitrary submitted URL as its src."""
    url_builder = _template_section(
        "function buildCardPreviewUrl(videoId, start, end, autoplay = false)",
        "function setCardSourcePreview(rank",
    )
    preview_helper = _template_section(
        "function setCardSourcePreview(rank",
        "function previewSelectedRange(rank)",
    )

    assert 'getYouTubeVideoId(card.dataset.videoUrl || "")' in preview_helper
    assert "buildCardPreviewUrl(videoId, config.start, config.end, autoplay)" in preview_helper
    assert "source.dataset.previewUrl = previewUrl" in preview_helper
    assert 'source.removeAttribute("src")' in preview_helper
    assert "source.src" in preview_helper
    assert "source.src = card.dataset.videoUrl" not in preview_helper
    assert "${card.dataset.videoUrl}" not in preview_helper

    assert "https://www.youtube-nocookie.com/embed/${encodeURIComponent(videoId)}" in url_builder
    assert "new URLSearchParams" in url_builder
    assert "Math.floor(start)" in url_builder
    assert "Math.ceil(end)" in url_builder
    assert "rel: '0'" in url_builder
    assert "playsinline: '1'" in url_builder


def test_only_the_selected_suggestion_mounts_a_youtube_player() -> None:
    """Idle cards show distinct suggestion slates and only one source iframe stays active."""
    preview_control = _template_section(
        "function stopOtherCardPreviews(activeRank)",
        "function scheduleCardSourcePreview(rank)",
    )

    assert "stopOtherCardPreviews(rank);" in preview_control
    assert 'source.removeAttribute("src")' in preview_control
    assert "source.hidden = true" in preview_control
    assert "placeholder.hidden = false" in preview_control
    assert "if (!autoplay)" in preview_control
    assert "source.src = previewUrl" in preview_control
    assert "Reproduzindo sugestão #${rank}" in preview_control
    assert "somente este intervalo" in preview_control


def test_interval_edits_refresh_the_preview_inside_the_same_card() -> None:
    """Gemini/manual timing changes must update only that card's source player."""
    editor_change = _template_section(
        "function editorFieldChanged(rank, field)",
        "function nudgeEditorTime(rank, field, delta)",
    )

    assert "editorField === 'start'" in editor_change
    assert "editorField === 'end'" in editor_change
    assert "scheduleCardSourcePreview(rank);" in editor_change

    refresh = _template_section(
        "function scheduleCardSourcePreview(rank)",
        "function setCardRenderedPreview(rank, downloadUrl)",
    )
    assert "window.clearTimeout(card.previewRefreshTimer)" in refresh
    assert "window.setTimeout" in refresh
    assert "setCardSourcePreview(rank);" in refresh

    selected_range = _template_section(
        "function previewSelectedRange(rank)",
        "function renderReceipt(data, rank)",
    )
    assert "setCardSourcePreview(rank, { autoplay: true, force: true })" in selected_range
    assert "document.getElementById('youtubeEmbed')" not in selected_range
    assert "document.getElementById('previewContainer')" not in selected_range


def test_generated_mp4_is_attached_to_its_card_not_only_the_global_player() -> None:
    """A rendered clip replaces the source preview in the matching card."""
    generate_clip = _template_section(
        "async function generateClip(videoUrl, rank, button)",
        "async function uploadExistingToDrive(filePath, rank, button)",
    )

    assert "setCardRenderedPreview(rank, data.download_url)" in generate_clip
    assert "document.getElementById('clipPreviewPlayer')" not in generate_clip
    assert "document.getElementById('verticalPlayerBox')" not in generate_clip
    assert "document.getElementById('previewContainer')" not in generate_clip

    rendered_preview = _template_section(
        "function setCardRenderedPreview(rank, downloadUrl)",
        "function playCardPreview(rank)",
    )
    assert "document.getElementById(`clipOutputPreview-${rank}`)" in rendered_preview
    assert "output.src = downloadUrl" in rendered_preview
    assert "showCardRenderedPreview(rank);" in rendered_preview

    rendered_visibility = _template_section(
        "function showCardRenderedPreview(rank, { autoplay = false } = {})",
        "function setCardRenderedPreview(rank, downloadUrl)",
    )
    assert "source.hidden = true" in rendered_visibility
    assert "output.hidden = false" in rendered_visibility
