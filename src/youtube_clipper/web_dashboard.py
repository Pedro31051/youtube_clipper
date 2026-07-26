"""
Web Dashboard Server for YouTube Clipper & AI Analyzer with Google Drive Integration.
Provides a modern glassmorphism web panel interface for analyzing YouTube videos,
previewing AI recommended viral clips, generating vertical Shorts (9:16), and saving directly to Google Drive.
"""

import os
import json
import tempfile
import subprocess
import urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from youtube_clipper.analyzer import extract_transcript_and_analyze
from youtube_clipper.pipeline import run_pipeline
from youtube_clipper.gdrive_uploader import upload_clip_to_gdrive
from youtube_clipper.exceptions import ClipperError, ValidationError, DownloadError, ProcessingError


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
                <button class="btn-primary" onclick="analyzeVideo()">
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
                grid.innerHTML = '<p style="color: var(--text-muted); text-align: center; grid-column: 1/-1;">Nenhum corte encontrado.</p>';
                return;
            }

            clips.forEach(clip => {
                const card = document.createElement('div');
                card.className = 'clip-card';
                card.id = `card-${clip.rank}`;

                const hashtagsHtml = (clip.hashtags || ['#shorts', '#viral'])
                    .map(tag => `<span class="chip">${tag}</span>`)
                    .join('');

                card.innerHTML = `
                    <div>
                        <div class="card-header">
                            <span class="badge-rank">Corte #${clip.rank}</span>
                            <span class="badge-score">🔥 Score: ${clip.score}/100</span>
                        </div>
                        <div class="card-title">${clip.title}</div>
                        <div class="card-time">⏱ ${clip.start_timestamp} ➔ ${clip.end_timestamp} (${clip.duration}s)</div>
                        <div class="card-transcript">"${clip.transcript ? clip.transcript.substring(0, 150) : ''}..."</div>
                        <div class="hashtags-container">${hashtagsHtml}</div>
                    </div>
                    <div class="btn-group" id="btnGroup-${clip.rank}">
                        <button class="btn-action btn-clip" onclick="generateClip('${videoUrl}', '${clip.start_timestamp}', '${clip.end_timestamp}', false, ${clip.rank})">
                            🎬 Gerar Corte Vertical (9:16)
                        </button>
                        <button class="btn-action btn-gdrive" onclick="generateClip('${videoUrl}', '${clip.start_timestamp}', '${clip.end_timestamp}', true, ${clip.rank})">
                            ☁️ 1-Click GDrive Upload
                        </button>
                    </div>
                `;
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

                    let actionHtml = `<a href="${data.download_url}" download class="btn-action btn-download">⬇️ Baixar Clipe MP4</a>`;
                    if (data.gdrive_link) {
                        actionHtml += `<a href="${data.gdrive_link}" target="_blank" class="drive-link-badge">🔗 Abrir no Google Drive</a>`;
                    } else {
                        actionHtml += `<button class="btn-action btn-gdrive" onclick="uploadExistingToDrive('${data.output_path || data.clip_path}', ${rank})">⬆️ Enviar ao GDrive MCP</button>`;
                    }
                    if (btnGroup) btnGroup.innerHTML = actionHtml;

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
                        btnGroup.innerHTML += `<a href="${link}" target="_blank" class="drive-link-badge">🔗 Abrir no Google Drive</a>`;
                    }
                } else {
                    alert('Erro no upload: ' + (data.error || 'Falha ao enviar'));
                }
            } catch (err) {
                spinner.style.display = 'none';
                alert('Erro: ' + err.message);
            }
        }
    </script>
</body>
</html>
"""


class ClipperDashboardHandler(BaseHTTPRequestHandler):
    """Multi-threaded HTTP Request Handler for YouTube Clipper Dashboard & REST API."""

    GET_ROUTES = {"/", "/index.html"}
    POST_ROUTES = {"/api/analyze", "/api/generate-clip", "/api/gdrive-upload"}

    def log_message(self, format, *args):
        pass

    def send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
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

            allowed_base_dirs = [
                (Path.cwd() / "output").resolve(),
                Path.cwd().resolve(),
                (Path.cwd() / "media_workspace").resolve(),
                Path(tempfile.gettempdir()).resolve(),
            ]

            target_path = None
            for base_dir in allowed_base_dirs:
                candidate = (base_dir / filename).resolve()
                if candidate.exists() and candidate.is_file():
                    try:
                        candidate.relative_to(base_dir)
                        target_path = candidate
                        break
                    except ValueError:
                        continue

            if target_path and target_path.exists():
                file_size = target_path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(file_size))
                self.end_headers()
                with open(target_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_json(404, {"success": False, "error": "File not found"})
        elif self.path in self.POST_ROUTES:
            self.send_error(405, "Method Not Allowed")
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        if self.path in self.GET_ROUTES or self.path.startswith("/api/download/"):
            self.send_error(405, "Method Not Allowed")
            return
        elif self.path not in self.POST_ROUTES:
            self.send_error(404, "Endpoint not found")
            return

        content_length = int(self.headers.get("Content-Length", 0))
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
                if cookies:
                    os.environ["YOUTUBE_COOKIES_FILE"] = str(cookies)
                analysis_result = extract_transcript_and_analyze(url, cookies_file=cookies)
                if isinstance(analysis_result, dict):
                    clips = analysis_result.get("clips", [])
                    all_transcripts = " ".join(c.get("transcript", "") for c in clips)
                    all_tags = list({tag for c in clips for tag in c.get("hashtags", [])})
                    analysis_result.setdefault("transcript", all_transcripts)
                    analysis_result.setdefault("hashtags", all_tags)
                self.send_json(200, analysis_result)
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
                if cookies:
                    os.environ["YOUTUBE_COOKIES_FILE"] = str(cookies)
                output_path = run_pipeline(
                    input_source=url,
                    start=start,
                    end=end,
                    vertical=True,
                    mode=fmt_mode,
                    cookies=cookies,
                )

                gdrive_link = None
                if upload_gdrive:
                    res = upload_clip_to_gdrive(output_path, folder_id=folder_id)
                    if res.get("success"):
                        gdrive_link = res.get("web_view_link")

                filename = os.path.basename(output_path)
                resp_data = {
                    "success": True,
                    "output_path": output_path,
                    "clip_path": output_path,
                    "download_url": f"/api/download/{filename}",
                    "gdrive_link": gdrive_link,
                }
                self.send_json(200, resp_data)
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

            if not os.path.exists(file_path):
                self.send_json(404, {"status": "error", "success": False, "error": f"File not found: {file_path}"})
                return

            try:
                res = upload_clip_to_gdrive(file_path, folder_id=folder_id)
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
        all_routes = self.GET_ROUTES | self.POST_ROUTES
        if self.path in all_routes or self.path.startswith("/api/download/"):
            self.send_error(405, "Method Not Allowed")
        else:
            self.send_error(404, "Not Found")


def start_dashboard_server(port: int = 8080):
    """Starts the multi-threaded HTTP dashboard server on specified port."""
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, ClipperDashboardHandler)
    print(f"🚀 Dashboard Server do YouTube Clipper rodando em: http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor finalizado.")


if __name__ == "__main__":
    start_dashboard_server(8080)
