"""
Web Dashboard Server for YouTube Clipper & AI Analyzer with Google Drive Integration.
Provides a modern glassmorphism web panel interface for analyzing YouTube videos,
previewing AI recommended viral clips, generating vertical Shorts (9:16), and saving directly to Google Drive.
"""

import os
import json
import urllib.parse
import hmac
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from youtube_clipper.analyzer import extract_transcript_and_analyze
from youtube_clipper.pipeline import run_pipeline
from youtube_clipper.gdrive_uploader import upload_clip_to_gdrive
from youtube_clipper.exceptions import ClipperError, ValidationError, DownloadError
from youtube_clipper.validator import is_youtube_url, validate_input_source


MAX_JSON_BODY_BYTES = 64 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024


class DashboardBusyError(RuntimeError):
    """Raised when all bounded media-processing slots are in use."""


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube AI Clipper & Google Drive Storage</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
            --card-bg: rgba(30, 41, 59, 0.75);
            --card-border: rgba(255, 255, 255, 0.12);
            --accent-purple: #8b5cf6;
            --accent-pink: #ec4899;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Outfit', sans-serif;
        }

        body {
            background: var(--bg-gradient);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem 1rem;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .container {
            max-width: 1100px;
            width: 100%;
        }

        header {
            text-align: center;
            margin-bottom: 2.5rem;
        }

        header h1 {
            font-size: 2.8rem;
            font-weight: 700;
            background: linear-gradient(to right, #a855f7, #ec4899, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        header p {
            color: var(--text-muted);
            font-size: 1.1rem;
        }

        .search-card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 1.75rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
            margin-bottom: 2rem;
        }

        .input-group {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }

        input[type="text"] {
            flex: 2;
            min-width: 280px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 0.75rem;
            padding: 0.85rem 1.25rem;
            color: #fff;
            font-size: 1rem;
            outline: none;
        }

        input[type="text"]:focus {
            border-color: var(--accent-purple);
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.3);
        }

        select.format-selector {
            flex: 1;
            min-width: 220px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 0.75rem;
            padding: 0.85rem 1rem;
            color: #fff;
            font-size: 0.95rem;
            outline: none;
            cursor: pointer;
        }

        button.btn-primary {
            background: linear-gradient(135deg, var(--accent-purple), var(--accent-pink));
            color: white;
            border: none;
            border-radius: 0.75rem;
            padding: 0.85rem 1.75rem;
            font-weight: 600;
            font-size: 1rem;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        button.btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px -5px rgba(236, 72, 153, 0.4);
        }

        /* Loading Container */
        .loading-container {
            display: none;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 2rem;
            text-align: center;
            margin-bottom: 2rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
        }

        .spinner {
            width: 48px;
            height: 48px;
            border: 4px solid rgba(255, 255, 255, 0.1);
            border-left-color: var(--accent-pink);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 1.25rem;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .step-indicators {
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            margin-top: 1rem;
            font-size: 0.9rem;
            color: var(--text-muted);
        }

        .step-indicator {
            padding: 0.4rem 0.8rem;
            border-radius: 2rem;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .step-indicator.active {
            background: rgba(139, 92, 246, 0.2);
            border-color: var(--accent-purple);
            color: #c084fc;
        }

        /* Preview Dual Player Container */
        .preview-container {
            display: none;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
        }

        .preview-header {
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .preview-players {
            display: flex;
            gap: 1.5rem;
            flex-wrap: wrap;
            justify-content: center;
            align-items: flex-start;
        }

        .player-box {
            flex: 1;
            min-width: 300px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .player-box h4 {
            font-size: 0.95rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .youtube-embed {
            width: 100%;
            height: 240px;
            border-radius: 0.75rem;
            border: 1px solid var(--card-border);
        }

        .vertical-player {
            width: 220px;
            height: 390px;
            border-radius: 1rem;
            border: 2px solid var(--accent-purple);
            background: #000;
            object-fit: cover;
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.5);
        }

        /* Clips Grid */
        .clips-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
            gap: 1.5rem;
        }

        .clip-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            padding: 1.35rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: transform 0.2s, border-color 0.2s;
        }

        .clip-card:hover {
            transform: translateY(-4px);
            border-color: rgba(139, 92, 246, 0.4);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.75rem;
        }

        .badge-score {
            background: rgba(236, 72, 153, 0.2);
            color: #f472b6;
            border: 1px solid rgba(236, 72, 153, 0.3);
            padding: 0.25rem 0.65rem;
            border-radius: 2rem;
            font-size: 0.85rem;
            font-weight: 600;
        }

        .badge-rank {
            background: rgba(139, 92, 246, 0.2);
            color: #c084fc;
            border: 1px solid rgba(139, 92, 246, 0.3);
            padding: 0.25rem 0.65rem;
            border-radius: 2rem;
            font-size: 0.85rem;
            font-weight: 600;
        }

        .card-title {
            font-size: 1.15rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            line-height: 1.3;
        }

        .card-time {
            font-size: 0.9rem;
            color: var(--accent-cyan);
            margin-bottom: 0.75rem;
            font-weight: 500;
        }

        .card-transcript {
            font-size: 0.88rem;
            color: var(--text-muted);
            line-height: 1.45;
            margin-bottom: 1rem;
            background: rgba(15, 23, 42, 0.6);
            padding: 0.85rem;
            border-radius: 0.6rem;
            border-left: 3px solid var(--accent-purple);
            max-height: 110px;
            overflow-y: auto;
        }

        .hashtags-container {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-bottom: 1.25rem;
        }

        .chip {
            background: rgba(6, 182, 212, 0.15);
            color: var(--accent-cyan);
            border: 1px solid rgba(6, 182, 212, 0.3);
            padding: 0.2rem 0.55rem;
            border-radius: 2rem;
            font-size: 0.78rem;
            font-weight: 500;
        }

        .btn-group {
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }

        .btn-action {
            width: 100%;
            color: white;
            border: none;
            border-radius: 0.6rem;
            padding: 0.7rem;
            font-weight: 600;
            font-size: 0.92rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            transition: opacity 0.2s, transform 0.1s;
        }

        .btn-action:hover {
            opacity: 0.9;
        }

        .btn-clip {
            background: linear-gradient(135deg, #3b82f6, var(--accent-purple));
        }

        .btn-gdrive {
            background: linear-gradient(135deg, var(--accent-green), #059669);
        }

        .btn-download {
            background: linear-gradient(135deg, #0284c7, #0369a1);
            text-decoration: none;
        }

        .drive-link-badge {
            display: inline-block;
            margin-top: 0.5rem;
            padding: 0.5rem 0.8rem;
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.4);
            border-radius: 0.5rem;
            font-size: 0.85rem;
            font-weight: 500;
            text-decoration: none;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ YouTube AI Clipper & Google Drive</h1>
            <p>Cortes Automáticos Verticais (9:16) integrados ao Google Drive MCP</p>
        </header>

        <div class="search-card">
            <div class="input-group">
                <input type="text" id="youtubeUrl" placeholder="Cole a URL do vídeo do YouTube" value="https://www.youtube.com/watch?v=3Vpf3EaE1mc">
                <input type="text" id="gdriveFolderId" placeholder="ID da Pasta Google Drive" value="1mYLUnTMhdflzmYhee804Nj52jBQuOI8H" style="flex: 1; min-width: 240px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 0.75rem; padding: 0.85rem 1.25rem; color: #fff; font-size: 1rem; outline: none;">
                <select id="formatSelector" class="format-selector">
                    <option value="blur_background">Fundo Desfocado (Split Blur 9:16)</option>
                    <option value="crop_center">Corte Centralizado (Crop Center 9:16)</option>
                </select>
                <button class="btn-primary" id="analyzeButton" type="button">
                    <span>🔍 Analisar Vídeo</span>
                </button>
            </div>
        </div>

        <!-- Glassmorphism Loading / Progress Status Container -->
        <div class="loading-container" id="loadingSpinner">
            <div class="spinner"></div>
            <p id="statusMessage">Analisando transcrição e descobrindo melhores momentos com IA...</p>
            <div class="step-indicators">
                <div class="step-indicator active" id="step1">1. Legendas VTT</div>
                <div class="step-indicator" id="step2">2. Ganchos Virais</div>
                <div class="step-indicator" id="step3">3. Renderização 9:16</div>
            </div>
        </div>

        <!-- Dual Interactive Preview Player Container -->
        <div class="preview-container" id="previewContainer">
            <div class="preview-header">
                <span>🎬 Player de Preview Interativo</span>
            </div>
            <div class="preview-players">
                <div class="player-box">
                    <h4>Vídeo Original YouTube</h4>
                    <iframe id="youtubeEmbed" class="youtube-embed" src="" frameborder="0" allowfullscreen></iframe>
                </div>
                <div class="player-box" id="verticalPlayerBox" style="display: none;">
                    <h4>Clipe Vertical (9:16)</h4>
                    <video id="clipPreviewPlayer" class="vertical-player" controls></video>
                </div>
            </div>
        </div>

        <!-- Ranked Engagement Clips Cards Grid -->
        <div class="clips-grid" id="clipsGrid"></div>
    </div>

    <script>
        function textElement(tagName, className, value) {
            const element = document.createElement(tagName);
            if (className) element.className = className;
            element.textContent = String(value ?? '');
            return element;
        }

        function safeLink(rawUrl, label, className, sameOrigin = false) {
            const parsed = new URL(String(rawUrl || ''), window.location.origin);
            if (!['http:', 'https:'].includes(parsed.protocol)) {
                throw new Error('URL de destino inválida');
            }
            if (sameOrigin && parsed.origin !== window.location.origin) {
                throw new Error('Download fora da origem local');
            }
            const link = textElement('a', className, label);
            link.href = parsed.href;
            link.rel = 'noopener noreferrer';
            return link;
        }

        function getYouTubeVideoId(url) {
            const match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})/);
            return match ? match[1] : null;
        }

        async function analyzeVideo() {
            const url = document.getElementById('youtubeUrl').value.trim();
            if (!url) return alert('Informe a URL do vídeo do YouTube!');

            const spinner = document.getElementById('loadingSpinner');
            const grid = document.getElementById('clipsGrid');
            const previewContainer = document.getElementById('previewContainer');
            const youtubeEmbed = document.getElementById('youtubeEmbed');
            const statusMsg = document.getElementById('statusMessage');

            spinner.style.display = 'block';
            grid.innerHTML = '';
            previewContainer.style.display = 'none';
            document.getElementById('verticalPlayerBox').style.display = 'none';
            statusMsg.innerText = 'Analisando legendas VTT e calculando engajamento de ganchos virais...';

            const videoId = getYouTubeVideoId(url);
            if (videoId) {
                youtubeEmbed.src = `https://www.youtube.com/embed/${videoId}`;
                previewContainer.style.display = 'block';
            }

            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });

                const data = await response.json();
                spinner.style.display = 'none';

                if (!response.ok || !data.success) {
                    return alert('Erro na análise: ' + (data.error || 'Falha ao processar vídeo'));
                }

                renderClips(data.clips, url);
            } catch (err) {
                spinner.style.display = 'none';
                alert('Erro na requisição: ' + err.message);
            }
        }

        function renderClips(clips, videoUrl) {
            const grid = document.getElementById('clipsGrid');
            grid.innerHTML = '';

            if (!clips || clips.length === 0) {
                const empty = textElement('p', '', 'Nenhum corte encontrado.');
                empty.style.color = 'var(--text-muted)';
                empty.style.textAlign = 'center';
                empty.style.gridColumn = '1/-1';
                grid.appendChild(empty);
                return;
            }

            clips.forEach(clip => {
                const rank = Number.isFinite(Number(clip.rank))
                    ? Number(clip.rank)
                    : 0;
                const card = document.createElement('div');
                card.className = 'clip-card';
                card.id = `card-${rank}`;

                const content = document.createElement('div');
                const header = document.createElement('div');
                header.className = 'card-header';
                header.appendChild(
                    textElement('span', 'badge-rank', `Corte #${rank}`)
                );
                header.appendChild(
                    textElement(
                        'span',
                        'badge-score',
                        `🔥 Score: ${Number(clip.score) || 0}/100`
                    )
                );
                content.appendChild(header);
                content.appendChild(
                    textElement('div', 'card-title', clip.title || 'Corte sugerido')
                );
                content.appendChild(
                    textElement(
                        'div',
                        'card-time',
                        `⏱ ${clip.start_timestamp || ''} ➔ ${clip.end_timestamp || ''} (${Number(clip.duration) || 0}s)`
                    )
                );
                const transcript = String(clip.transcript || '').substring(0, 150);
                content.appendChild(
                    textElement('div', 'card-transcript', `"${transcript}..."`)
                );
                const hashtags = document.createElement('div');
                hashtags.className = 'hashtags-container';
                (clip.hashtags || ['#shorts', '#viral']).forEach(tag => {
                    hashtags.appendChild(textElement('span', 'chip', tag));
                });
                content.appendChild(hashtags);
                card.appendChild(content);

                const btnGroup = document.createElement('div');
                btnGroup.className = 'btn-group';
                btnGroup.id = `btnGroup-${rank}`;
                const generateButton = textElement(
                    'button',
                    'btn-action btn-clip',
                    '🎬 Gerar Corte Vertical (9:16)'
                );
                generateButton.type = 'button';
                generateButton.addEventListener('click', () => {
                    generateClip(
                        videoUrl,
                        clip.start_timestamp,
                        clip.end_timestamp,
                        false,
                        rank
                    );
                });
                const driveButton = textElement(
                    'button',
                    'btn-action btn-gdrive',
                    '☁️ 1-Click GDrive Upload'
                );
                driveButton.type = 'button';
                driveButton.addEventListener('click', () => {
                    generateClip(
                        videoUrl,
                        clip.start_timestamp,
                        clip.end_timestamp,
                        true,
                        rank
                    );
                });
                btnGroup.append(generateButton, driveButton);
                card.appendChild(btnGroup);
                grid.appendChild(card);
            });
        }

        async function generateClip(videoUrl, start, end, uploadGDrive, rank) {
            const format = document.getElementById('formatSelector').value;
            const folderIdEl = document.getElementById('gdriveFolderId');
            const folderId = folderIdEl ? folderIdEl.value.trim() : '1mYLUnTMhdflzmYhee804Nj52jBQuOI8H';
            const spinner = document.getElementById('loadingSpinner');
            const statusMsg = document.getElementById('statusMessage');
            const btnGroup = document.getElementById(`btnGroup-${rank}`);

            spinner.style.display = 'block';
            statusMsg.innerText = uploadGDrive
                ? 'Renderizando clipe 9:16 e enviando para o Google Drive MCP...'
                : 'Renderizando clipe vertical 9:16 com FFmpeg...';

            try {
                const res = await fetch('/api/generate-clip', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: videoUrl,
                        start: start,
                        end: end,
                        format: format,
                        gdrive: uploadGDrive,
                        folder_id: folderId
                    })
                });

                const data = await res.json();
                spinner.style.display = 'none';

                if (data.success) {
                    // Update preview player
                    if (data.download_url) {
                        const verticalPlayer = document.getElementById('clipPreviewPlayer');
                        const verticalBox = document.getElementById('verticalPlayerBox');
                        verticalPlayer.src = data.download_url;
                        verticalBox.style.display = 'flex';
                        document.getElementById('previewContainer').style.display = 'block';
                        verticalPlayer.play().catch(() => {});
                    }

                    if (btnGroup) {
                        btnGroup.replaceChildren();
                        const downloadLink = safeLink(
                            data.download_url,
                            '⬇️ Baixar Clipe MP4',
                            'btn-action btn-download',
                            true
                        );
                        downloadLink.download = '';
                        btnGroup.appendChild(downloadLink);
                        if (data.gdrive_link) {
                            const driveLink = safeLink(
                                data.gdrive_link,
                                '🔗 Abrir no Google Drive',
                                'drive-link-badge'
                            );
                            driveLink.target = '_blank';
                            btnGroup.appendChild(driveLink);
                        } else {
                            const uploadButton = textElement(
                                'button',
                                'btn-action btn-gdrive',
                                '⬆️ Enviar ao GDrive MCP'
                            );
                            uploadButton.type = 'button';
                            const outputPath = String(
                                data.output_path || data.clip_path || ''
                            );
                            uploadButton.addEventListener('click', () => {
                                uploadExistingToDrive(outputPath, rank);
                            });
                            btnGroup.appendChild(uploadButton);
                        }
                    }

                } else {
                    alert('Erro ao gerar corte: ' + (data.error || 'Erro desconhecido'));
                }
            } catch (err) {
                spinner.style.display = 'none';
                alert('Erro na requisição: ' + err.message);
            }
        }

        async function uploadExistingToDrive(filePath, rank) {
            const folderIdEl = document.getElementById('gdriveFolderId');
            const folderId = folderIdEl ? folderIdEl.value.trim() : '1mYLUnTMhdflzmYhee804Nj52jBQuOI8H';
            const spinner = document.getElementById('loadingSpinner');
            const statusMsg = document.getElementById('statusMessage');
            const btnGroup = document.getElementById(`btnGroup-${rank}`);

            spinner.style.display = 'block';
            statusMsg.innerText = 'Enviando arquivo para o Google Drive...';

            try {
                const res = await fetch('/api/gdrive-upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: filePath,
                        folder_id: folderId
                    })
                });

                const data = await res.json();
                spinner.style.display = 'none';

                if (data.status === 'success' || data.success) {
                    const link = data.web_view_link || data.link;
                    alert('✅ Upload concluído no Google Drive!\nLink: ' + link);
                    if (btnGroup) {
                        const driveLink = safeLink(
                            link,
                            '🔗 Abrir no Google Drive',
                            'drive-link-badge'
                        );
                        driveLink.target = '_blank';
                        btnGroup.appendChild(driveLink);
                    }
                } else {
                    alert('Erro no upload: ' + (data.error || 'Falha ao enviar'));
                }
            } catch (err) {
                spinner.style.display = 'none';
                alert('Erro: ' + err.message);
            }
        }

        document
            .getElementById('analyzeButton')
            .addEventListener('click', analyzeVideo);
    </script>
</body>
</html>
"""


class ClipperDashboardHandler(BaseHTTPRequestHandler):
    """Multi-threaded HTTP Request Handler for YouTube Clipper Dashboard & REST API."""

    GET_ROUTES = {"/", "/index.html"}
    POST_ROUTES = {"/api/analyze", "/api/generate-clip", "/api/gdrive-upload"}

    def _output_dir(self) -> Path:
        configured = vars(self.server).get("output_dir", Path.cwd() / "output")
        return Path(configured).resolve()

    def _is_authorized(self) -> bool:
        expected = vars(self.server).get("api_token", None)
        server_address = self.server.server_address
        bound_host = (
            str(server_address[0])
            if isinstance(server_address, tuple)
            else str(server_address)
        )
        loopback = bound_host in {"127.0.0.1", "::1", "localhost"}
        if not expected:
            return loopback
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        return supplied.startswith(prefix) and hmac.compare_digest(
            supplied[len(prefix):], str(expected)
        )

    def _require_authorization(self) -> bool:
        if self._is_authorized():
            return True
        self.send_json(401, {"success": False, "error": "Unauthorized"})
        return False

    def _resolve_output_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser().resolve()
        candidate.relative_to(self._output_dir())
        return candidate

    def _run_bounded_job(self, operation, *args, **kwargs):
        semaphore = vars(self.server).get("job_semaphore", None)
        if semaphore is None:
            return operation(*args, **kwargs)
        if not semaphore.acquire(blocking=False):
            raise DashboardBusyError(
                "Dashboard is at its media-processing concurrency limit"
            )
        try:
            return operation(*args, **kwargs)
        finally:
            semaphore.release()

    def log_message(self, format, *args):
        pass

    def send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._require_authorization():
            return
        if self.path in self.GET_ROUTES:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path.startswith("/api/download/"):
            raw_param = urllib.parse.unquote(self.path[len("/api/download/"):])

            if ".." in raw_param or raw_param.startswith("/") or "\\" in raw_param:
                self.send_json(400, {"success": False, "error": "Invalid filename or path traversal detected"})
                return

            filename = os.path.basename(raw_param)
            if not filename or filename != raw_param or ".." in filename or "/" in filename or "\\" in filename:
                self.send_json(400, {"success": False, "error": "Invalid filename"})
                return

            base_dir = self._output_dir()
            candidate = (base_dir / filename).resolve()
            target_path = None
            try:
                candidate.relative_to(base_dir)
                if candidate.exists() and candidate.is_file():
                    target_path = candidate
            except ValueError:
                target_path = None

            if target_path and target_path.exists():
                file_size = target_path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(file_size))
                self.end_headers()
                with open(target_path, "rb") as f:
                    while chunk := f.read(DOWNLOAD_CHUNK_BYTES):
                        self.wfile.write(chunk)
            else:
                self.send_json(404, {"success": False, "error": "File not found"})
        elif self.path in self.POST_ROUTES:
            self.send_error(405, "Method Not Allowed")
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        if not self._require_authorization():
            return
        if self.path in self.GET_ROUTES or self.path.startswith("/api/download/"):
            self.send_error(405, "Method Not Allowed")
            return
        elif self.path not in self.POST_ROUTES:
            self.send_error(404, "Endpoint not found")
            return

        raw_content_length = self.headers.get("Content-Length")
        if raw_content_length is None:
            self.send_json(411, {"success": False, "error": "Content-Length required"})
            return
        try:
            content_length = int(raw_content_length)
        except (TypeError, ValueError):
            self.send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return
        max_body = int(vars(self.server).get("max_json_body_bytes", MAX_JSON_BODY_BYTES))
        if content_length <= 0:
            self.send_json(400, {"success": False, "error": "Missing request body"})
            return
        if content_length > max_body:
            self.send_json(413, {"success": False, "error": "JSON request body too large"})
            return
        post_data = self.rfile.read(content_length)

        if not post_data:
            self.send_json(400, {"success": False, "error": "Missing request body"})
            return

        try:
            payload = json.loads(post_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, AttributeError, TypeError):
            self.send_json(400, {"success": False, "error": "Invalid JSON format"})
            return

        if not isinstance(payload, dict):
            self.send_json(400, {"success": False, "error": "JSON payload must be an object"})
            return

        if self.path == "/api/analyze":
            url = payload.get("url", "")
            cookies = payload.get("cookies", None)
            if not url or not isinstance(url, str) or not url.strip():
                self.send_json(400, {"success": False, "error": "URL parameter required"})
                return
            try:
                clean_url = validate_input_source(url)
                if not is_youtube_url(clean_url):
                    raise ValidationError("Dashboard analysis accepts only YouTube URLs")
                analysis_result = self._run_bounded_job(
                    extract_transcript_and_analyze,
                    clean_url,
                    cookies_file=cookies,
                )
                if isinstance(analysis_result, dict):
                    clips = analysis_result.get("clips", [])
                    all_transcripts = " ".join(c.get("transcript", "") for c in clips)
                    all_tags = list({tag for c in clips for tag in c.get("hashtags", [])})
                    analysis_result.setdefault("transcript", all_transcripts)
                    analysis_result.setdefault("hashtags", all_tags)
                self.send_json(200, analysis_result)
            except DashboardBusyError as e:
                self.send_json(503, {"success": False, "error": str(e)})
            except (ValidationError, ValueError) as e:
                self.send_json(400, {"success": False, "error": str(e)})
            except FileNotFoundError as e:
                self.send_json(404, {"success": False, "error": str(e)})
            except ClipperError as e:
                if isinstance(e, (ValidationError, DownloadError)):
                    self.send_json(400, {"success": False, "error": str(e)})
                else:
                    self.send_json(500, {"success": False, "error": str(e)})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})

        elif self.path == "/api/generate-clip":
            url = payload.get("url", "")
            if not url or not isinstance(url, str) or not url.strip():
                self.send_json(400, {"success": False, "error": "URL parameter required"})
                return
            start = payload.get("start", "0")
            end = payload.get("end", "10")
            fmt_mode = payload.get("format", payload.get("mode", "blur_background"))
            upload_gdrive = payload.get("gdrive", False)
            folder_id = payload.get("folder_id", None)
            cookies = payload.get("cookies", None)

            valid_modes = {"blur_background", "split_blur", "crop_center"}
            if fmt_mode not in valid_modes:
                self.send_json(400, {"success": False, "error": f"Invalid format mode: {fmt_mode}. Must be one of {sorted(list(valid_modes))}"})
                return

            try:
                clean_url = validate_input_source(url)
                if not is_youtube_url(clean_url):
                    raise ValidationError("Dashboard generation accepts only YouTube URLs")
                output_dir = self._output_dir()
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = self._run_bounded_job(
                    run_pipeline,
                    input_source=clean_url,
                    start=start,
                    end=end,
                    output=str(output_dir) + os.sep,
                    vertical=True,
                    mode=fmt_mode,
                    cookies=cookies,
                )

                gdrive_link = None
                if upload_gdrive:
                    res = upload_clip_to_gdrive(output_path, folder_id=folder_id)
                    if res.get("success"):
                        gdrive_link = res.get("web_view_link")
                    else:
                        self.send_json(
                            502,
                            {
                                "success": False,
                                "error": (
                                    "Clip generated, but Google Drive upload failed: "
                                    f"{res.get('error') or 'unknown upload error'}"
                                ),
                                "output_path": output_path,
                                "clip_path": output_path,
                            },
                        )
                        return

                filename = os.path.basename(output_path)
                resp_data = {
                    "success": True,
                    "output_path": output_path,
                    "clip_path": output_path,
                    "download_url": f"/api/download/{filename}",
                    "gdrive_link": gdrive_link,
                }
                self.send_json(200, resp_data)
            except DashboardBusyError as e:
                self.send_json(503, {"success": False, "error": str(e)})
            except (ValidationError, ValueError) as e:
                self.send_json(400, {"success": False, "error": str(e)})
            except FileNotFoundError as e:
                self.send_json(404, {"success": False, "error": str(e)})
            except ClipperError as e:
                if isinstance(e, (ValidationError, DownloadError)):
                    self.send_json(400, {"success": False, "error": str(e)})
                else:
                    self.send_json(500, {"success": False, "error": str(e)})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})

        elif self.path == "/api/gdrive-upload":
            file_path = payload.get("file_path", "")
            folder_id = payload.get("folder_id", None)
            if not file_path or not isinstance(file_path, str) or not file_path.strip():
                self.send_json(400, {"success": False, "error": "file_path parameter required"})
                return

            try:
                allowed_file = self._resolve_output_file(file_path)
            except (ValueError, OSError):
                self.send_json(
                    403,
                    {
                        "status": "error",
                        "success": False,
                        "error": "file_path must be inside the dashboard output directory",
                    },
                )
                return

            if not allowed_file.exists() or not allowed_file.is_file():
                self.send_json(404, {"status": "error", "success": False, "error": f"File not found: {file_path}"})
                return

            try:
                res = upload_clip_to_gdrive(str(allowed_file), folder_id=folder_id)
                if res.get("success"):
                    res["status"] = "success"
                    res["link"] = res.get("web_view_link")
                    self.send_json(200, res)
                else:
                    res["status"] = "error"
                    err_msg = str(res.get("error", ""))
                    if "not found" in err_msg.lower():
                        self.send_json(404, res)
                    else:
                        self.send_json(500, res)
            except FileNotFoundError as e:
                self.send_json(404, {"status": "error", "success": False, "error": str(e)})
            except Exception as e:
                self.send_json(500, {"status": "error", "success": False, "error": str(e)})

    def do_PUT(self):
        self._handle_unsupported_method()

    def do_DELETE(self):
        self._handle_unsupported_method()

    def do_PATCH(self):
        self._handle_unsupported_method()

    def do_HEAD(self):
        self._handle_unsupported_method()

    def do_OPTIONS(self):
        self._handle_unsupported_method()

    def _handle_unsupported_method(self):
        if not self._require_authorization():
            return
        all_routes = self.GET_ROUTES | self.POST_ROUTES
        if self.path in all_routes or self.path.startswith("/api/download/"):
            self.send_error(405, "Method Not Allowed")
        else:
            self.send_error(404, "Not Found")


def start_dashboard_server(
    port: int = 8080,
    host: str = "127.0.0.1",
    api_token: str | None = None,
    output_dir: str | Path | None = None,
    max_concurrent_jobs: int = 1,
    max_json_body_bytes: int = MAX_JSON_BODY_BYTES,
):
    """Start the dashboard with explicit exposure and a dedicated output root."""
    normalized_host = host.strip() or "127.0.0.1"
    if normalized_host not in {"127.0.0.1", "::1", "localhost"} and not api_token:
        raise ValueError("A bearer API token is required when binding beyond loopback")
    if max_concurrent_jobs < 1:
        raise ValueError("max_concurrent_jobs must be at least 1")
    if max_json_body_bytes < 1:
        raise ValueError("max_json_body_bytes must be at least 1")
    server_address = (normalized_host, port)
    httpd = ThreadingHTTPServer(server_address, ClipperDashboardHandler)
    server_state = vars(httpd)
    server_state["api_token"] = api_token
    server_state["job_semaphore"] = threading.BoundedSemaphore(
        max_concurrent_jobs
    )
    server_state["max_json_body_bytes"] = max_json_body_bytes
    output_root = Path(output_dir or (Path.cwd() / "output")).resolve()
    server_state["output_dir"] = output_root
    output_root.mkdir(parents=True, exist_ok=True)
    print(
        "🚀 Dashboard Server do YouTube Clipper rodando em: "
        f"http://{normalized_host}:{port}"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor finalizado.")


if __name__ == "__main__":
    start_dashboard_server(8080)
