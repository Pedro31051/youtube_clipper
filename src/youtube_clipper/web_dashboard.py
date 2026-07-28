"""
Web Dashboard Server for YouTube Clipper & AI Analyzer with Google Drive Integration.
Provides a modern glassmorphism web panel interface for analyzing YouTube videos,
previewing AI recommended viral clips, generating vertical Shorts (9:16), and saving directly to Google Drive.
"""

import functools
import base64
import binascii
import hashlib
import os
import json
import math
import re
import shutil
import sys
import threading
import urllib.parse
import hmac
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from youtube_clipper.analyzer import extract_transcript_and_analyze
from cortes.dashboard_pipeline import run_dashboard_clip_pipeline as run_pipeline
from youtube_clipper.gdrive_uploader import upload_clip_to_gdrive
from youtube_clipper.exceptions import ClipperError, ValidationError, DownloadError
from youtube_clipper.validator import is_youtube_url, validate_input_source, validate_time_range
from youtube_clipper.gemini_editor import (
    GeminiConfigurationError,
    GeminiEditorError,
    GeminiInputError,
    request_gemini_edit,
)
from youtube_clipper.project_store import (
    DomainConflictError,
    DomainNotFoundError,
    DomainValidationError,
    ProjectStore,
)
from cortes.log import action_span, audited, run_context
from cortes.ingest import probe_video_metadata
from cortes.pipeline import run_full_pipeline
from cortes.preview import generate_clip_preview
from cortes.verify import verify_run


def observed_http_request(func):
    """Create an isolated and sealed audit run for each HTTP request."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        request_id = self._normalize_request_id(
            self.headers.get("X-Request-ID")
        )
        route = urllib.parse.urlsplit(self.path).path
        if route.startswith(self.STATUS_ROUTE_PREFIX):
            self._audit_request_id = request_id
            self._audit_run_id = None
            self._audit_response_status = None
            self._audit_authorized = None
            return func(self, *args, **kwargs)
        action = f"http.{self.command.lower()}.{route}"
        with run_context(
            request_id=request_id,
            actions=[{"action": action, "stage": "env"}],
            component="youtube_clipper.dashboard",
        ) as run_id:
            self._audit_request_id = request_id
            self._audit_run_id = run_id
            if not route.startswith(self.STATUS_ROUTE_PREFIX):
                self._register_request_run(request_id, run_id)
            with action_span(
                "env",
                action,
                component="youtube_clipper.dashboard",
                input_data={
                    "method": self.command,
                    "path": route,
                    "content_length": self.headers.get("Content-Length", "0"),
                    "remote_address": self.client_address[0] if self.client_address else None,
                },
            ) as span:
                self._audit_response_status = None
                self._audit_authorized = None
                result = func(self, *args, **kwargs)
                span.decision = {
                    "http_status": self._audit_response_status,
                    "authorized": self._audit_authorized,
                }
                if self._audit_response_status is not None and self._audit_response_status >= 400:
                    span.mark_failed(
                        f"HTTP request returned {self._audit_response_status}",
                        category="http",
                        retryable=self._audit_response_status >= 500,
                    )
                return result
    return wrapper


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="data:,">
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

        .card-preview {
            margin: 1rem 0 0.2rem;
            border: 1px solid rgba(139, 92, 246, 0.35);
            border-radius: 0.85rem;
            overflow: hidden;
            background: rgba(15, 23, 42, 0.78);
        }

        .card-preview-header,
        .card-preview-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            padding: 0.55rem 0.7rem;
        }

        .card-preview-header {
            color: #e2e8f0;
            font-size: 0.78rem;
            font-weight: 700;
        }

        .card-preview-state {
            color: var(--text-muted);
            font-size: 0.7rem;
            font-weight: 500;
            text-align: right;
        }

        .card-preview-screen {
            position: relative;
            aspect-ratio: 16 / 9;
            background: #020617;
        }

        .card-preview-screen iframe,
        .card-preview-screen video {
            display: block;
            width: 100%;
            height: 100%;
            border: 0;
            background: #000;
            object-fit: cover;
        }

        .card-preview-placeholder {
            display: grid;
            width: 100%;
            height: 100%;
            place-content: center;
            gap: 0.5rem;
            padding: 1.1rem;
            text-align: center;
            background:
                radial-gradient(circle at 20% 15%, rgba(59, 130, 246, 0.28), transparent 35%),
                radial-gradient(circle at 80% 85%, rgba(236, 72, 153, 0.24), transparent 38%),
                #071026;
        }

        .card-preview-placeholder[hidden] { display: none; }

        .card-preview-placeholder span {
            color: #a5b4fc;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .card-preview-placeholder strong {
            color: #f8fafc;
            font-size: 0.95rem;
            line-height: 1.35;
        }

        .card-preview-placeholder time {
            color: #67e8f9;
            font-variant-numeric: tabular-nums;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .card-preview-screen[data-preview-mode="rendered"] {
            width: min(100%, 230px);
            aspect-ratio: 9 / 16;
            margin: 0 auto;
            border-inline: 1px solid rgba(139, 92, 246, 0.22);
        }

        .card-preview-footer {
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }

        .card-preview-button {
            padding: 0.38rem 0.55rem;
            border: 1px solid rgba(96, 165, 250, 0.45);
            border-radius: 0.48rem;
            background: rgba(37, 99, 235, 0.18);
            color: #dbeafe;
            font: inherit;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
        }

        .card-preview-button:hover { background: rgba(59, 130, 246, 0.34); }

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

        .operation-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            text-align: left;
        }

        .operation-copy {
            flex: 1;
            min-width: 0;
        }

        .operation-copy h3 {
            font-size: 1.05rem;
            margin-bottom: 0.25rem;
        }

        .operation-status-badge {
            border-radius: 999px;
            padding: 0.35rem 0.7rem;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            background: rgba(139, 92, 246, 0.2);
            color: #c4b5fd;
            border: 1px solid rgba(139, 92, 246, 0.45);
            white-space: nowrap;
        }

        .loading-container[data-state="success"] .spinner,
        .loading-container[data-state="warning"] .spinner,
        .loading-container[data-state="error"] .spinner {
            display: none;
        }

        .loading-container[data-state="success"] .operation-status-badge {
            color: #6ee7b7;
            border-color: rgba(16, 185, 129, 0.55);
            background: rgba(16, 185, 129, 0.18);
        }

        .loading-container[data-state="warning"] .operation-status-badge {
            color: #fcd34d;
            border-color: rgba(245, 158, 11, 0.55);
            background: rgba(245, 158, 11, 0.18);
        }

        .loading-container[data-state="error"] .operation-status-badge {
            color: #fca5a5;
            border-color: rgba(239, 68, 68, 0.55);
            background: rgba(239, 68, 68, 0.18);
        }

        .step-indicator[data-state="running"] {
            background: rgba(139, 92, 246, 0.2);
            border-color: var(--accent-purple);
            color: #c084fc;
        }

        .step-indicator[data-state="success"] {
            background: rgba(16, 185, 129, 0.18);
            border-color: rgba(16, 185, 129, 0.55);
            color: #6ee7b7;
        }

        .step-indicator[data-state="warning"] {
            background: rgba(245, 158, 11, 0.18);
            border-color: rgba(245, 158, 11, 0.55);
            color: #fcd34d;
        }

        .step-indicator[data-state="error"] {
            background: rgba(239, 68, 68, 0.18);
            border-color: rgba(239, 68, 68, 0.55);
            color: #fca5a5;
        }

        .activity-shell {
            margin-top: 1.25rem;
            background: rgba(2, 6, 23, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 0.75rem;
            overflow: hidden;
            text-align: left;
        }

        .activity-header {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.7rem 0.9rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            color: var(--text-muted);
            font-size: 0.8rem;
        }

        .request-reference {
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            color: #c4b5fd;
        }

        .activity-log {
            list-style: none;
            max-height: 220px;
            overflow-y: auto;
            padding: 0.5rem 0.75rem;
        }

        .activity-log li {
            display: grid;
            grid-template-columns: auto auto 1fr;
            gap: 0.55rem;
            align-items: start;
            padding: 0.42rem 0;
            color: #cbd5e1;
            font-size: 0.82rem;
            line-height: 1.35;
        }

        .activity-log time {
            color: #64748b;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }

        .log-dot {
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 50%;
            background: #64748b;
            margin-top: 0.25rem;
        }

        li[data-state="running"] .log-dot { background: #a78bfa; }
        li[data-state="success"] .log-dot { background: #34d399; }
        li[data-state="warning"] .log-dot { background: #fbbf24; }
        li[data-state="error"] .log-dot { background: #f87171; }
        li[data-state="skipped"] .log-dot { background: #94a3b8; }

        .clip-card.editor-open {
            grid-column: 1 / -1;
            transform: none;
        }

        .metadata-label {
            color: var(--text-muted);
            font-size: 0.76rem;
            margin-bottom: 0.45rem;
        }

        .clip-editor {
            margin-top: 0.9rem;
            padding: 1rem;
            border-radius: 0.8rem;
            border: 1px solid rgba(139, 92, 246, 0.35);
            background: rgba(2, 6, 23, 0.48);
        }

        .clip-editor[hidden], .render-receipt[hidden], .result-actions[hidden] {
            display: none;
        }

        .editor-header, .receipt-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.9rem;
        }

        .editor-state {
            color: #c4b5fd;
            border: 1px solid rgba(139, 92, 246, 0.45);
            background: rgba(139, 92, 246, 0.14);
            border-radius: 999px;
            padding: 0.25rem 0.55rem;
            font-size: 0.75rem;
            white-space: nowrap;
        }

        .control-section {
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }

        .control-section h4 {
            font-size: 0.82rem;
            color: #cbd5e1;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 0.7rem;
        }

        .control-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
        }

        .control-field {
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
            min-width: 0;
            color: #cbd5e1;
            font-size: 0.82rem;
        }

        .control-field input[type="number"],
        .control-field input[type="text"],
        .control-field select {
            width: 100%;
            min-width: 0;
            flex: none;
            padding: 0.65rem 0.7rem;
            border-radius: 0.55rem;
            border: 1px solid rgba(255, 255, 255, 0.15);
            background: rgba(15, 23, 42, 0.9);
            color: #fff;
            font: inherit;
        }

        .control-field input:focus, .control-field select:focus {
            outline: none;
            border-color: var(--accent-purple);
            box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.22);
        }

        .nudge-controls {
            display: flex;
            gap: 0.35rem;
            margin-top: 0.35rem;
        }

        .btn-small {
            min-height: 36px;
            padding: 0.45rem 0.65rem;
            border-radius: 0.5rem;
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(51, 65, 85, 0.75);
            color: #e2e8f0;
            cursor: pointer;
        }

        .toggle-row {
            display: flex;
            align-items: flex-start;
            gap: 0.65rem;
            color: #e2e8f0;
            font-size: 0.86rem;
            line-height: 1.35;
            margin-top: 0.7rem;
        }

        .toggle-row input {
            width: 1.05rem;
            height: 1.05rem;
            margin-top: 0.08rem;
            accent-color: var(--accent-purple);
            flex: 0 0 auto;
        }

        .range-row {
            display: grid;
            grid-template-columns: 1fr auto;
            align-items: center;
            gap: 0.7rem;
        }

        .range-row output {
            min-width: 2.5rem;
            text-align: right;
            color: #c4b5fd;
        }

        .inclusion-summary {
            margin-top: 1rem;
            padding: 0.85rem;
            border-radius: 0.65rem;
            border: 1px solid rgba(6, 182, 212, 0.28);
            background: rgba(8, 47, 73, 0.24);
            font-size: 0.84rem;
            line-height: 1.5;
        }

        .summary-title {
            font-weight: 700;
            color: #e0f2fe;
            margin-bottom: 0.35rem;
        }

        .included-line { color: #6ee7b7; }
        .excluded-line { color: #fcd34d; }

        .editor-validation {
            min-height: 1.25rem;
            margin: 0.55rem 0;
            color: #fca5a5;
            font-size: 0.8rem;
        }

        .confirmation-row {
            padding: 0.8rem;
            border: 1px solid rgba(245, 158, 11, 0.38);
            border-radius: 0.65rem;
            background: rgba(120, 53, 15, 0.16);
        }

        .confirmation-row strong { color: #fde68a; }

        .render-receipt {
            margin-top: 1rem;
            padding: 1rem;
            border-radius: 0.8rem;
            border: 1px solid rgba(16, 185, 129, 0.45);
            background: rgba(6, 78, 59, 0.18);
        }

        .receipt-id {
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            color: #a7f3d0;
            font-size: 0.73rem;
            overflow-wrap: anywhere;
        }

        .receipt-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.45rem 1rem;
            font-size: 0.82rem;
            margin-bottom: 0.75rem;
        }

        .receipt-grid div {
            padding: 0.4rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.07);
        }

        .receipt-list {
            font-size: 0.82rem;
            line-height: 1.45;
            margin-top: 0.35rem;
        }

        .unsupported-note {
            color: var(--text-muted);
            font-size: 0.76rem;
            margin-top: 0.45rem;
        }

        .btn-review {
            background: linear-gradient(135deg, #7c3aed, #2563eb);
        }

        .btn-preview-range {
            background: rgba(6, 182, 212, 0.18);
            border: 1px solid rgba(6, 182, 212, 0.4);
        }

        .gemini-chat { margin: 0.9rem 0; border: 1px solid rgba(96, 165, 250, 0.32); border-radius: 0.85rem; overflow: hidden; background: radial-gradient(circle at 100% 0, rgba(236, 72, 153, 0.14), transparent 13rem), rgba(2, 6, 23, 0.58); }
        .gemini-chat-toggle { width: 100%; border: 0; padding: 0.8rem 0.9rem; color: #f8fafc; background: transparent; display: flex; align-items: center; justify-content: space-between; gap: 0.7rem; cursor: pointer; text-align: left; }
        .gemini-chat-toggle:hover { background: rgba(96, 165, 250, 0.08); }
        .gemini-identity { display: flex; align-items: center; gap: 0.65rem; min-width: 0; }
        .gemini-mark { width: 1.9rem; height: 1.9rem; flex: 0 0 auto; display: grid; place-items: center; border-radius: 0.65rem; background: linear-gradient(145deg, #60a5fa, #8b5cf6 55%, #ec4899); box-shadow: 0 0 22px rgba(139, 92, 246, 0.28); font-size: 1rem; }
        .gemini-identity strong { display: block; font-size: 0.88rem; }
        .gemini-identity small { display: block; color: var(--text-muted); font-size: 0.7rem; margin-top: 0.08rem; }
        .gemini-model-badge { flex: 0 0 auto; padding: 0.25rem 0.5rem; border: 1px solid rgba(96, 165, 250, 0.35); border-radius: 999px; color: #bfdbfe; background: rgba(37, 99, 235, 0.12); font-size: 0.67rem; font-weight: 700; white-space: nowrap; }
        .gemini-chat-body { padding: 0 0.85rem 0.85rem; border-top: 1px solid rgba(255, 255, 255, 0.07); }
        .gemini-chat-body[hidden] { display: none; }
        .gemini-messages { max-height: 210px; overflow-y: auto; padding: 0.75rem 0.1rem 0.35rem; display: flex; flex-direction: column; gap: 0.55rem; scrollbar-width: thin; }
        .gemini-message { max-width: 92%; padding: 0.58rem 0.68rem; border-radius: 0.7rem; font-size: 0.79rem; line-height: 1.42; white-space: pre-wrap; overflow-wrap: anywhere; }
        .gemini-message[data-role="assistant"] { align-self: flex-start; color: #dbeafe; background: rgba(30, 64, 175, 0.2); border: 1px solid rgba(96, 165, 250, 0.2); border-bottom-left-radius: 0.2rem; }
        .gemini-message[data-role="user"] { align-self: flex-end; color: #fce7f3; background: rgba(157, 23, 77, 0.22); border: 1px solid rgba(244, 114, 182, 0.2); border-bottom-right-radius: 0.2rem; }
        .gemini-message[data-state="error"] { color: #fecaca; background: rgba(127, 29, 29, 0.2); border-color: rgba(248, 113, 113, 0.3); }
        .gemini-quick-actions { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.35rem 0 0.55rem; }
        .gemini-chip { min-height: 32px; padding: 0.35rem 0.55rem; border-radius: 999px; border: 1px solid rgba(139, 92, 246, 0.35); color: #ddd6fe; background: rgba(124, 58, 237, 0.12); font-size: 0.71rem; cursor: pointer; }
        .gemini-composer { display: grid; grid-template-columns: 1fr auto; gap: 0.45rem; align-items: end; }
        .gemini-composer textarea { width: 100%; min-height: 62px; max-height: 130px; resize: vertical; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 0.65rem; padding: 0.62rem 0.7rem; color: #fff; background: rgba(15, 23, 42, 0.86); font: inherit; font-size: 0.8rem; }
        .gemini-composer textarea:focus { outline: none; border-color: #60a5fa; box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.16); }
        .gemini-send { min-width: 44px; min-height: 44px; border: 0; border-radius: 0.65rem; color: #fff; background: linear-gradient(145deg, #2563eb, #7c3aed, #db2777); cursor: pointer; font-size: 1rem; }
        .gemini-change-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.45rem; }
        .gemini-change { padding: 0.25rem 0.45rem; border-radius: 999px; border: 1px solid rgba(16, 185, 129, 0.35); color: #a7f3d0; background: rgba(6, 78, 59, 0.18); font-size: 0.68rem; }
        .asset-controls { margin-top: 0.85rem; padding: 0.8rem; border: 1px solid rgba(255, 255, 255, 0.09); border-radius: 0.65rem; background: rgba(15, 23, 42, 0.48); }
        .asset-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.65rem; margin-top: 0.65rem; }
        .asset-card { min-width: 0; padding: 0.7rem; border: 1px solid rgba(255, 255, 255, 0.09); border-radius: 0.6rem; background: rgba(2, 6, 23, 0.45); }
        .asset-card strong { display: block; font-size: 0.8rem; margin-bottom: 0.45rem; }
        .asset-file-label { display: block; min-height: 1.1rem; margin-top: 0.4rem; color: #93c5fd; font-size: 0.7rem; overflow-wrap: anywhere; }
        .asset-upload-button { width: 100%; min-height: 38px; padding: 0.5rem 0.65rem; border-radius: 0.55rem; border: 1px dashed rgba(96, 165, 250, 0.42); color: #dbeafe; background: rgba(30, 64, 175, 0.12); cursor: pointer; font-size: 0.75rem; }
        .rights-row { margin-top: 0; padding-bottom: 0.65rem; border-bottom: 1px solid rgba(255, 255, 255, 0.07); }

        .drive-progress {
            margin: 1rem 0;
            padding: 0.9rem;
            border: 1px solid rgba(139, 92, 246, 0.38);
            border-radius: 0.8rem;
            background: rgba(15, 23, 42, 0.72);
        }

        .drive-progress[hidden] { display: none; }

        .drive-progress-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.65rem;
        }

        .drive-progress-header span {
            color: #ddd6fe;
            font-variant-numeric: tabular-nums;
            font-weight: 700;
        }

        .drive-progress-track {
            height: 0.72rem;
            overflow: hidden;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.2);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
        }

        .drive-progress-fill {
            width: 0;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #8b5cf6, #ec4899);
            transition: width 0.25s ease;
        }

        .drive-progress[data-mode="indeterminate"] .drive-progress-fill {
            width: 40%;
            animation: drive-progress-slide 1.1s ease-in-out infinite;
        }

        @keyframes drive-progress-slide {
            0% { transform: translateX(-120%); }
            100% { transform: translateX(320%); }
        }

        .drive-progress-copy {
            min-height: 1.25rem;
            margin-top: 0.55rem;
            color: var(--text-muted);
            font-size: 0.8rem;
            line-height: 1.4;
        }

        .drive-progress-steps {
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
            margin-top: 0.65rem;
        }

        .drive-progress-steps span {
            padding: 0.28rem 0.55rem;
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 999px;
            color: #94a3b8;
            font-size: 0.72rem;
        }

        .drive-progress-steps span[data-state="active"] {
            border-color: rgba(139, 92, 246, 0.65);
            color: #ddd6fe;
            background: rgba(124, 58, 237, 0.16);
        }

        .drive-progress-steps span[data-state="complete"] {
            border-color: rgba(16, 185, 129, 0.55);
            color: #6ee7b7;
            background: rgba(6, 78, 59, 0.18);
        }

        .drive-progress-steps span[data-state="retrying"] {
            border-color: rgba(245, 158, 11, 0.58);
            color: #fcd34d;
            background: rgba(120, 53, 15, 0.16);
        }

        .drive-progress-steps span[data-state="error"] {
            border-color: rgba(239, 68, 68, 0.58);
            color: #fca5a5;
            background: rgba(127, 29, 29, 0.16);
        }

        .drive-progress[data-state="failed"],
        .drive-progress[data-state="link_warning"] {
            border-color: rgba(239, 68, 68, 0.52);
        }

        .drive-progress[data-state="retrying"] {
            border-color: rgba(245, 158, 11, 0.58);
        }

        .drive-progress[data-state="succeeded"] {
            border-color: rgba(16, 185, 129, 0.55);
        }

        .drive-progress-card {
            margin-top: 0;
            margin-bottom: 0.75rem;
        }

        .card-operation-status {
            display: none;
            border-radius: 0.55rem;
            padding: 0.55rem 0.7rem;
            margin-bottom: 0.65rem;
            font-size: 0.82rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: var(--text-muted);
            background: rgba(15, 23, 42, 0.65);
        }

        .card-operation-status[data-state="running"],
        .card-operation-status[data-state="success"],
        .card-operation-status[data-state="warning"],
        .card-operation-status[data-state="error"] {
            display: block;
        }

        .card-operation-status[data-state="running"] { color: #c4b5fd; border-color: rgba(139, 92, 246, 0.45); }
        .card-operation-status[data-state="success"] { color: #6ee7b7; border-color: rgba(16, 185, 129, 0.45); }
        .card-operation-status[data-state="warning"] { color: #fcd34d; border-color: rgba(245, 158, 11, 0.45); }
        .card-operation-status[data-state="error"] { color: #fca5a5; border-color: rgba(239, 68, 68, 0.45); }

        button:disabled {
            cursor: wait;
            opacity: 0.62;
            transform: none !important;
        }

        button:disabled:not([aria-busy="true"]) { cursor: not-allowed; }

        @media (max-width: 640px) {
            body { padding: 1rem 0.65rem; }
            header h1 { font-size: 2rem; }
            .search-card, .loading-container, .preview-container { padding: 1rem; }
            .clips-grid { grid-template-columns: 1fr; }
            .clip-card { padding: 1rem; }
            .clip-editor { padding: 0.8rem; }
            .control-grid, .receipt-grid { grid-template-columns: 1fr; }
            .btn-action, .btn-small { min-height: 44px; }
            .editor-header, .receipt-header { align-items: flex-start; flex-direction: column; }
            .operation-header { align-items: flex-start; flex-wrap: wrap; }
            .step-indicators { gap: 0.45rem; flex-wrap: wrap; }
            .step-indicator { font-size: 0.78rem; }
            .activity-header { flex-direction: column; gap: 0.25rem; }
            .drive-progress-header { align-items: flex-start; flex-direction: column; }
            .asset-grid { grid-template-columns: 1fr; }
            .gemini-model-badge { display: none; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ YouTube AI Clipper & Google Drive</h1>
            <p>Cortes Automáticos Verticais (9:16) integrados ao Google Drive MCP</p>
            <p><a href="/technical">Abrir Pipeline Técnico T2/T3 (arquivo local, Whisper e legendas queimadas)</a></p>
        </header>

        <div class="search-card">
            <div class="input-group">
                <input type="text" id="youtubeUrl" placeholder="Cole a URL do vídeo do YouTube" value="https://www.youtube.com/watch?v=3Vpf3EaE1mc">
                <input type="text" id="gdriveFolderId" placeholder="ID da Pasta Google Drive" value="1mYLUnTMhdflzmYhee804Nj52jBQuOI8H" style="flex: 1; min-width: 240px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 0.75rem; padding: 0.85rem 1.25rem; color: #fff; font-size: 1rem; outline: none;">
                <button class="btn-primary" id="analyzeButton" onclick="analyzeVideo(this)">
                    <span>🔍 Analisar Vídeo</span>
                </button>
            </div>
        </div>

        <!-- Persistent operation status and audited activity log -->
        <section class="loading-container" id="loadingSpinner" data-state="idle" aria-live="polite" aria-atomic="false">
            <div class="operation-header">
                <div class="spinner" id="operationSpinner" aria-hidden="true"></div>
                <div class="operation-copy">
                    <h3 id="operationTitle">Aguardando uma operação</h3>
                    <p id="statusMessage">Clique em uma ação para acompanhar cada etapa.</p>
                </div>
                <span class="operation-status-badge" id="operationBadge">AGUARDANDO</span>
            </div>
            <div class="step-indicators" aria-label="Etapas da operação">
                <div class="step-indicator" data-state="pending" id="step1">1. Solicitação</div>
                <div class="step-indicator" data-state="pending" id="step2">2. Processamento</div>
                <div class="step-indicator" data-state="pending" id="step3">3. Resultado</div>
            </div>
            <div class="drive-progress" id="driveProgressGlobal" hidden aria-live="polite" data-state="pending" data-mode="indeterminate">
                <div class="drive-progress-header">
                    <strong>☁️ Upload ao Google Drive</strong>
                    <span data-drive-percent>aguardando</span>
                </div>
                <div class="drive-progress-track" data-drive-track role="progressbar" aria-label="Progresso do upload ao Google Drive" aria-valuemin="0" aria-valuemax="100">
                    <div class="drive-progress-fill" data-drive-fill></div>
                </div>
                <div class="drive-progress-copy" data-drive-copy>Upload aguardando a conclusão do MP4.</div>
                <div class="drive-progress-steps" aria-label="Etapas do envio ao Drive">
                    <span data-drive-step="auth" data-state="pending">Autenticação</span>
                    <span data-drive-step="upload" data-state="pending">Envio</span>
                    <span data-drive-step="link" data-state="pending">Link</span>
                </div>
            </div>
            <div class="activity-shell">
                <div class="activity-header">
                    <strong>Logs da operação</strong>
                    <span class="request-reference" id="requestReference">sem operação ativa</span>
                </div>
                <ol class="activity-log" id="activityLog" role="log" aria-live="polite" aria-relevant="additions"></ol>
            </div>
        </section>

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
        const operationState = {
            stopPolling: null,
            seenEvents: new Set(),
            hadBackendFailure: false,
            activeRank: null,
            driveRequested: false
        };

        const eventStatusLabels = {
            planned: 'planejado',
            started: 'iniciado',
            retrying: 'nova tentativa',
            succeeded: 'concluído',
            skipped: 'ignorado',
            failed: 'falhou',
            cancelled: 'cancelado',
            interrupted: 'interrompido'
        };

        function createRequestId() {
            if (window.crypto && typeof window.crypto.randomUUID === 'function') {
                return window.crypto.randomUUID();
            }
            return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        }

        function getYouTubeVideoId(url) {
            const match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})/);
            return match ? match[1] : null;
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>'"]/g, char => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
            })[char]);
        }

        function friendlyAction(action) {
            const value = String(action || 'operação');
            if (value.includes('/api/analyze')) return 'Requisição de análise';
            if (value.includes('/api/generate-clip')) return 'Requisição de renderização';
            if (value.includes('/api/gdrive-upload')) return 'Requisição de upload';
            if (value === 'youtube.extract_transcript_and_analyze') return 'Extração e análise da transcrição';
            if (value === 'youtube.parse_vtt') return 'Leitura das legendas VTT';
            if (value === 'youtube.rank_clips') return 'Seleção dos melhores cortes';
            if (value.includes('command.yt-dlp')) return 'Download das legendas com yt-dlp';
            if (value === 'public.validate_input') return 'Validação do vídeo e dos tempos';
            if (value === 'public.resolve_output') return 'Preparação do arquivo de saída';
            if (value === 'public.download') return 'Download do trecho do vídeo';
            if (value === 'youtube.download_segment') return 'Captura do segmento selecionado';
            if (value === 'public.vertical_transform') return 'Conversão vertical 9:16';
            if (value.includes('media.convert_vertical')) return 'Renderização do vídeo com FFmpeg';
            if (value.includes('command.ffmpeg')) return 'Processamento FFmpeg';
            if (value === 'public.cleanup') return 'Limpeza dos arquivos temporários';
            if (value.includes('gdrive.auth')) return 'Autenticação no Google Drive';
            if (value === 'gdrive.build_client') return 'Conexão com o Google Drive';
            if (value === 'gdrive.resolve_folder') return 'Localização da pasta no Drive';
            if (value.startsWith('gdrive.upload.progress.')) return 'Progresso do upload ao Drive';
            if (value === 'gdrive.upload') return 'Envio do MP4 ao Google Drive';
            if (value === 'gdrive.set_permission') return 'Configuração do link do Drive';
            if (value === 'http.authorize') return 'Autorização da requisição';
            if (value === 'http.send_json') return 'Preparação da resposta';
            return value.replaceAll('.', ' · ');
        }

        function setMarker(id, state, text) {
            const marker = document.getElementById(id);
            if (!marker) return;
            marker.dataset.state = state;
            if (text) marker.textContent = text;
        }

        function setCardStatus(rank, state, message) {
            if (rank === undefined || rank === null) return;
            const status = document.getElementById(`cardStatus-${rank}`);
            if (!status) return;
            status.dataset.state = state;
            status.textContent = message;
        }

        function driveProgressTargets(rank = operationState.activeRank) {
            const targets = [document.getElementById("driveProgressGlobal")];
            if (rank !== undefined && rank !== null) {
                targets.push(document.getElementById(`driveProgress-${rank}`));
            }
            return targets.filter(Boolean);
        }

        function resetDriveProgress(rank, requested) {
            const targets = driveProgressTargets(rank);
            for (const container of targets) {
                const isGlobal = container.id === "driveProgressGlobal";
                if (!requested) {
                    if (isGlobal || container.id === `driveProgress-${rank}`) container.hidden = true;
                    continue;
                }
                container.hidden = false;
                container.dataset.state = "pending";
                container.dataset.mode = "indeterminate";
                delete container.dataset.percent;
                const fill = container.querySelector("[data-drive-fill]");
                const track = container.querySelector("[data-drive-track]");
                if (fill) fill.style.width = "40%";
                if (track) {
                    track.removeAttribute("aria-valuenow");
                    track.setAttribute("aria-valuetext", "Upload aguardando a conclusão do MP4");
                }
                const percentLabel = container.querySelector("[data-drive-percent]");
                const copy = container.querySelector("[data-drive-copy]");
                if (percentLabel) percentLabel.textContent = "aguardando";
                if (copy) copy.textContent = "Upload aguardando a conclusão do MP4.";
                container.querySelectorAll("[data-drive-step]").forEach(step => {
                    step.dataset.state = "pending";
                });
            }
        }

        function renderDriveProgress(status = {}, rank = operationState.activeRank) {
            const state = String(status.state || "pending");
            const finalPercentStates = new Set(["uploaded", "finalizing", "succeeded", "link_warning"]);
            const hasIncomingPercent = status.progress_percent !== null
                && status.progress_percent !== undefined
                && status.progress_percent !== "";
            const rawPercent = Number(status.progress_percent);
            const incomingPercent = hasIncomingPercent && Number.isFinite(rawPercent)
                ? Math.max(0, Math.min(100, rawPercent))
                : null;
            const uploadedBytes = Number(status.uploaded_bytes);
            const totalBytes = Number(status.total_bytes);
            const hasUploadedBytes = status.uploaded_bytes !== null
                && status.uploaded_bytes !== undefined
                && Number.isFinite(uploadedBytes)
                && uploadedBytes >= 0;
            const hasTotalBytes = status.total_bytes !== null
                && status.total_bytes !== undefined
                && Number.isFinite(totalBytes)
                && totalBytes >= 0;

            for (const container of driveProgressTargets(rank)) {
                container.hidden = false;
                container.dataset.state = state;
                const storedPercent = Number(container.dataset.percent);
                const hasStoredPercent = container.dataset.percent !== undefined && Number.isFinite(storedPercent);
                let percent = finalPercentStates.has(state) ? 100 : incomingPercent;
                if (hasStoredPercent && (percent === null || percent < storedPercent)) percent = storedPercent;
                const determinate = percent !== null && (
                    status.determinate === true || hasStoredPercent || finalPercentStates.has(state)
                );
                container.dataset.mode = determinate ? "determinate" : "indeterminate";

                const fill = container.querySelector("[data-drive-fill]");
                const track = container.querySelector("[data-drive-track]");
                const percentLabel = container.querySelector("[data-drive-percent]");
                const copy = container.querySelector("[data-drive-copy]");
                const displayPercent = determinate
                    ? Number(percent.toFixed(1)).toLocaleString("pt-BR")
                    : null;

                if (determinate) {
                    container.dataset.percent = String(percent);
                    if (fill) fill.style.width = `${percent}%`;
                    if (track) track.setAttribute("aria-valuenow", String(percent));
                } else {
                    if (fill) fill.style.width = "40%";
                    if (track) track.removeAttribute("aria-valuenow");
                }

                let label = determinate ? `${displayPercent}%` : "em andamento";
                let message = "Preparando o envio ao Google Drive…";
                if (state === "pending") {
                    label = "aguardando";
                    message = "Upload aguardando a conclusão do MP4.";
                } else if (state === "authenticating") {
                    message = "Autenticando no Google Drive…";
                } else if (state === "preparing") {
                    message = "Localizando a pasta de destino…";
                } else if (state === "uploading") {
                    message = determinate && hasUploadedBytes && hasTotalBytes
                        ? `${formatFileSize(uploadedBytes)} de ${formatFileSize(totalBytes)} confirmados pelo Drive.`
                        : "Enviando o arquivo; este transporte ainda não informou bytes confirmados.";
                } else if (state === "retrying") {
                    label = determinate ? `${displayPercent}% · nova tentativa` : "nova tentativa";
                    message = `Tentativa ${status.attempt || "adicional"}; o último progresso confirmado foi preservado.`;
                } else if (state === "uploaded") {
                    message = "Arquivo enviado; preparando o link de compartilhamento.";
                } else if (state === "finalizing") {
                    message = "100% enviado; configurando o link de compartilhamento.";
                } else if (state === "succeeded") {
                    message = "Upload concluído e link do Google Drive disponível.";
                } else if (state === "failed") {
                    label = determinate ? `falhou em ${displayPercent}%` : "falhou";
                    message = determinate
                        ? `Upload interrompido após ${displayPercent}% confirmados pelo Drive.`
                        : "O upload falhou antes de o Drive confirmar o progresso.";
                } else if (state === "link_warning") {
                    label = "100% · link pendente";
                    message = "Arquivo enviado, mas o link de compartilhamento não pôde ser configurado.";
                }

                if (percentLabel) percentLabel.textContent = label;
                if (copy) copy.textContent = message;
                if (track) track.setAttribute("aria-valuetext", `${label}. ${message}`);

                const authStep = container.querySelector("[data-drive-step=auth]");
                const uploadStep = container.querySelector("[data-drive-step=upload]");
                const linkStep = container.querySelector("[data-drive-step=link]");
                if (authStep) authStep.dataset.state = state === "authenticating" ? "active" : (state === "pending" ? "pending" : "complete");
                if (uploadStep) {
                    if (["preparing", "uploading", "retrying"].includes(state)) uploadStep.dataset.state = state === "retrying" ? "retrying" : "active";
                    else if (state === "failed") uploadStep.dataset.state = "error";
                    else if (["uploaded", "finalizing", "succeeded", "link_warning"].includes(state)) uploadStep.dataset.state = "complete";
                    else uploadStep.dataset.state = "pending";
                }
                if (linkStep) {
                    if (state === "finalizing") linkStep.dataset.state = "active";
                    else if (state === "succeeded") linkStep.dataset.state = "complete";
                    else if (state === "link_warning") linkStep.dataset.state = "error";
                    else linkStep.dataset.state = "pending";
                }
            }
        }

        function appendActivity(message, state = 'running', timestamp = null, eventId = null) {
            if (eventId && operationState.seenEvents.has(eventId)) return;
            if (eventId) operationState.seenEvents.add(eventId);

            const log = document.getElementById('activityLog');
            const item = document.createElement('li');
            item.dataset.state = state;
            const dot = document.createElement('span');
            dot.className = 'log-dot';
            dot.setAttribute('aria-hidden', 'true');
            const time = document.createElement('time');
            const parsed = timestamp ? new Date(timestamp) : new Date();
            time.dateTime = Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString();
            time.textContent = Number.isNaN(parsed.getTime())
                ? '--:--:--'
                : parsed.toLocaleTimeString('pt-BR', { hour12: false });
            const copy = document.createElement('span');
            copy.textContent = message;
            item.append(dot, time, copy);
            log.appendChild(item);
            while (log.children.length > 200) log.firstElementChild.remove();
            log.scrollTop = log.scrollHeight;
        }

        function setControlsBusy(busy, activeButton = null, busyLabel = '') {
            document.querySelectorAll('button').forEach(button => {
                if (busy) {
                    if (!button.disabled) button.dataset.operationEnabled = 'true';
                    button.disabled = true;
                } else if (button.dataset.operationEnabled === 'true') {
                    button.disabled = false;
                    delete button.dataset.operationEnabled;
                }
            });

            if (!activeButton) return;
            if (busy) {
                activeButton.dataset.originalContent = activeButton.innerHTML;
                activeButton.textContent = busyLabel || '⏳ Processando...';
                activeButton.setAttribute('aria-busy', 'true');
            } else {
                if (activeButton.dataset.originalContent && activeButton.isConnected) {
                    activeButton.innerHTML = activeButton.dataset.originalContent;
                }
                delete activeButton.dataset.originalContent;
                activeButton.removeAttribute('aria-busy');
            }
        }

        function beginOperation({ title, message, button, busyLabel, rank = null, driveRequested = false }) {
            if (operationState.stopPolling) operationState.stopPolling();
            operationState.seenEvents = new Set();
            operationState.hadBackendFailure = false;
            operationState.activeRank = rank;
            operationState.driveRequested = Boolean(driveRequested);
            resetDriveProgress(rank, operationState.driveRequested);
            const requestId = createRequestId();
            const panel = document.getElementById('loadingSpinner');
            panel.style.display = 'block';
            panel.dataset.state = 'running';
            document.getElementById('operationTitle').textContent = title;
            document.getElementById('statusMessage').textContent = message;
            document.getElementById('operationBadge').textContent = 'EM ANDAMENTO';
            document.getElementById('requestReference').textContent = `ID ${requestId}`;
            document.getElementById('activityLog').replaceChildren();
            setMarker('step1', 'running', '1. Enviando');
            setMarker('step2', 'pending', '2. Processando');
            setMarker('step3', 'pending', '3. Resultado');
            setControlsBusy(true, button, busyLabel);
            setCardStatus(rank, 'running', message);
            appendActivity('Ação iniciada no navegador.', 'running');
            const stopPolling = startStatusPolling(requestId);
            operationState.stopPolling = stopPolling;
            return { requestId, button, rank, stopPolling, driveRequested: operationState.driveRequested };
        }

        async function finishOperation(context, state, title, message) {
            if (context.stopPolling) await context.stopPolling();
            if (state === 'success' && operationState.hadBackendFailure) {
                state = 'warning';
                title = title + ' com alertas';
                message = message + ' Uma etapa interna falhou e foi recuperada; consulte o log.';
            }
            if (operationState.stopPolling === context.stopPolling) {
                operationState.stopPolling = null;
            }
            const panel = document.getElementById('loadingSpinner');
            panel.dataset.state = state;
            document.getElementById('operationTitle').textContent = title;
            document.getElementById('statusMessage').textContent = message;
            const badgeLabels = {
                success: 'CONCLUÍDO', warning: 'ATENÇÃO', error: 'ERRO'
            };
            document.getElementById('operationBadge').textContent = badgeLabels[state] || state.toUpperCase();
            setMarker('step1', 'success', '1. Enviado');
            setMarker('step2', state === 'error' ? 'error' : 'success', state === 'error' ? '2. Falhou' : '2. Processado');
            setMarker('step3', state, state === 'success' ? '3. Concluído' : (state === 'warning' ? '3. Parcial' : '3. Erro'));
            appendActivity(message, state);
            setCardStatus(context.rank, state, message);
            setControlsBusy(false, context.button);
        }

        function showImmediateError(title, message) {
            const panel = document.getElementById('loadingSpinner');
            panel.style.display = 'block';
            panel.dataset.state = 'error';
            document.getElementById('operationTitle').textContent = title;
            document.getElementById('statusMessage').textContent = message;
            document.getElementById('operationBadge').textContent = 'ERRO';
            document.getElementById('requestReference').textContent = 'validação local';
            document.getElementById('activityLog').replaceChildren();
            setMarker('step1', 'error', '1. Não enviado');
            setMarker('step2', 'pending', '2. Processamento');
            setMarker('step3', 'error', '3. Corrija os dados');
            appendActivity(message, 'error');
        }

        function renderBackendStatus(data) {
            const events = Array.isArray(data.events) ? data.events : [];
            for (const event of events) {
                const eventId = event.event_id || `${event.run_id}:${event.seq}:${event.status}`;
                if (event.status === 'planned') continue;
                const visualState = event.status === 'succeeded'
                    ? 'success'
                    : (event.status === 'failed' ? 'error' : event.status);
                const statusLabel = eventStatusLabels[event.status] || event.status || 'atualizado';
                let message = `${friendlyAction(event.action)} — ${statusLabel}`;
                if (event.error) message += `: ${event.error}`;
                appendActivity(message, visualState, event.ts, eventId);

                if (String(event.action || '').startsWith('http.') && event.status === 'started') {
                    setMarker('step1', 'success', '1. Recebido');
                    setMarker('step2', 'running', '2. Processando');
                } else if (!String(event.action || '').startsWith('http.') && event.status === 'started') {
                    setMarker('step2', 'running', '2. Processando');
                } else if (event.status === 'failed') {
                    operationState.hadBackendFailure = true;
                    setMarker('step2', 'error', '2. Falha detectada');
                }
            }
            if (data && data.drive_upload && operationState.driveRequested) {
                renderDriveProgress(data.drive_upload, operationState.activeRank);
            }
        }

        function startStatusPolling(requestId) {
            let stopped = false;
            let polling = false;
            let timer = null;

            const poll = async () => {
                if (stopped || polling) return;
                polling = true;
                try {
                    const response = await fetch(`/api/status/${encodeURIComponent(requestId)}`, {
                        cache: 'no-store'
                    });
                    if (response.ok) renderBackendStatus(await response.json());
                } catch (_) {
                    // The main request will report a definitive network error.
                } finally {
                    polling = false;
                }
            };

            timer = window.setInterval(poll, 750);
            poll();
            return async () => {
                if (stopped) return;
                window.clearInterval(timer);
                await new Promise(resolve => window.setTimeout(resolve, 100));
                stopped = false;
                await poll();
                stopped = true;
            };
        }

        async function trackedPost(endpoint, payload, operation) {
            const context = beginOperation(operation);
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Request-ID': context.requestId
                    },
                    body: JSON.stringify(payload)
                });
                let data;
                try {
                    data = await response.json();
                } catch (_) {
                    data = { success: false, error: `Resposta HTTP ${response.status} sem JSON válido.` };
                }
                await context.stopPolling();
                context.stopPolling = null;
                operationState.stopPolling = null;
                return { response, data, context };
            } catch (error) {
                if (context.driveRequested) renderDriveProgress({ state: "failed" }, context.rank);
                await finishOperation(
                    context,
                    'error',
                    'Falha de comunicação',
                    `Não foi possível concluir a requisição: ${error.message}`
                );
                return { response: null, data: null, context, error };
            }
        }

        async function analyzeVideo(button) {
            const url = document.getElementById('youtubeUrl').value.trim();
            if (!url) {
                showImmediateError('Análise não iniciada', 'Informe a URL do vídeo do YouTube.');
                return;
            }

            const videoId = getYouTubeVideoId(url);
            if (videoId) {
                document.getElementById('youtubeEmbed').src = `https://www.youtube.com/embed/${videoId}`;
                document.getElementById('previewContainer').style.display = 'block';
            }

            const result = await trackedPost('/api/analyze', { url }, {
                title: 'Analisando vídeo',
                message: 'Extraindo legendas e procurando os melhores momentos.',
                button,
                busyLabel: '⏳ Analisando vídeo...'
            });
            if (result.error) return;
            const { response, data, context } = result;
            if (!response.ok || !data.success) {
                await finishOperation(
                    context,
                    'error',
                    'Análise não concluída',
                    data.error || `Falha HTTP ${response.status}`
                );
                return;
            }

            renderClips(data.clips, url);
            const count = Array.isArray(data.clips) ? data.clips.length : 0;
            await finishOperation(
                context,
                'success',
                'Análise concluída',
                `${count} sugest${count === 1 ? 'ão' : 'ões'} de corte encontrada${count === 1 ? '' : 's'}.`
            );
        }

        function parseTimeValue(value) {
            if (typeof value === 'number') return Number.isFinite(value) ? value : NaN;
            const raw = String(value ?? '').trim();
            if (!raw) return NaN;
            const parts = raw.split(':').map(Number);
            if (parts.some(part => !Number.isFinite(part))) return NaN;
            if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
            if (parts.length === 2) return parts[0] * 60 + parts[1];
            if (parts.length === 1) return parts[0];
            return NaN;
        }

        function clipExactTime(clip, numericKey, timestampKey) {
            const exact = clip[numericKey];
            if (exact !== null && exact !== undefined && exact !== '') {
                const parsed = Number(exact);
                if (Number.isFinite(parsed)) return parsed;
            }
            return parseTimeValue(clip[timestampKey]);
        }

        function formatTimecode(seconds) {
            if (!Number.isFinite(seconds)) return '--:--.--';
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = (seconds % 60).toFixed(2).padStart(5, '0');
            return hours > 0
                ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${secs}`
                : `${String(minutes).padStart(2, '0')}:${secs}`;
        }

        function formatFileSize(bytes) {
            const value = Number(bytes);
            if (!Number.isFinite(value) || value < 0) return 'não informado';
            if (value < 1024) return `${value} B`;
            if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
            return `${(value / (1024 * 1024)).toFixed(1)} MB`;
        }

        function renderClips(clips, videoUrl) {
            const grid = document.getElementById('clipsGrid');
            grid.innerHTML = '';

            if (!clips || clips.length === 0) {
                const empty = document.createElement('p');
                empty.style.cssText = 'color: var(--text-muted); text-align: center; grid-column: 1/-1;';
                empty.textContent = 'Nenhum corte encontrado.';
                grid.appendChild(empty);
                return;
            }

            clips.forEach((clip, index) => {
                const rank = Number(clip.rank) || index + 1;
                const clipId = String(clip.clip_id || 'legacy-rank-' + rank);
                const projectId = String(clip.project_id || "");
                const analysisId = String(clip.analysis_id || "");
                const startSeconds = clipExactTime(clip, 'start_time', 'start_timestamp');
                const endSeconds = clipExactTime(clip, 'end_time', 'end_timestamp');
                const durationSeconds = endSeconds - startSeconds;
                const card = document.createElement('div');
                card.className = 'clip-card';
                card.id = `card-${rank}`;
                card.dataset.videoUrl = videoUrl;
                card.dataset.clipId = clipId;
                card.dataset.projectId = projectId;
                card.dataset.analysisId = analysisId;
                card.dataset.dirtyAfterRender = 'false';
                const hashtagsHtml = (clip.hashtags || ['#shorts', '#viral'])
                    .map(tag => `<span class="chip">${escapeHtml(tag)}</span>`)
                    .join('');
                const transcript = clip.transcript ? String(clip.transcript).substring(0, 150) : '';
                const overlayDefault = String(clip.title || `Corte ${rank}`).slice(0, 90);
                const startValue = Number.isFinite(startSeconds) ? Number(startSeconds.toFixed(3)) : 0;
                const endValue = Number.isFinite(endSeconds) ? Number(endSeconds.toFixed(3)) : 10;
                card.geminiHistory = [];
                card.geminiContext = {
                    rank,
                    clip_id: clipId,
                    project_id: projectId,
                    analysis_id: analysisId,
                    title: String(clip.title || `Corte ${rank}`).slice(0, 180),
                    score: Number(clip.score) || 0,
                    transcript: String(clip.transcript || '').slice(0, 6000),
                    hashtags: Array.isArray(clip.hashtags) ? clip.hashtags.slice(0, 12) : [],
                    start: startValue,
                    end: endValue
                };

                card.innerHTML = `
                    <div>
                        <div class="card-header">
                            <span class="badge-rank">Corte #${rank}</span>
                            <span class="badge-score">🔥 Score: ${escapeHtml(clip.score)}/100</span>
                        </div>
                        <div class="card-title">${escapeHtml(clip.title)}</div>
                        <div class="card-time" id="cardTime-${rank}">⏱ ${formatTimecode(startValue)} ➔ ${formatTimecode(endValue)} (${Number.isFinite(durationSeconds) ? durationSeconds.toFixed(2) : '?'}s)</div>
                        <section class="card-preview" aria-label="Prévia do corte ${rank}">
                            <div class="card-preview-header">
                                <span>🎬 Tela deste corte</span>
                                <span class="card-preview-state" id="cardPreviewState-${rank}" aria-live="polite">Sugestão #${rank} pronta</span>
                            </div>
                            <div class="card-preview-screen" id="cardPreviewScreen-${rank}" data-preview-mode="source">
                                <div class="card-preview-placeholder" id="clipSuggestionPlaceholder-${rank}">
                                    <span>Sugestão #${rank}</span>
                                    <strong>${escapeHtml(clip.title || `Corte #${rank}`)}</strong>
                                    <time>${formatTimecode(startValue)} → ${formatTimecode(endValue)}</time>
                                </div>
                                <iframe id="clipSourcePreview-${rank}" title="Prévia da sugestão ${rank}" loading="lazy" hidden referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
                                <video id="clipOutputPreview-${rank}" title="MP4 vertical do corte ${rank}" controls playsinline hidden></video>
                            </div>
                            <div class="card-preview-footer">
                                <span class="card-preview-state" id="cardPreviewDetail-${rank}">Trecho sugerido · carregado somente ao reproduzir</span>
                                <button type="button" class="card-preview-button" data-action="play-card-preview">▶ Reproduzir sugestão #${rank}</button>
                            </div>
                        </section>
                        <div class="card-transcript">"${escapeHtml(transcript)}..."</div>
                        <div class="metadata-label">Hashtags sugeridas — metadados; não entram na imagem do vídeo</div>
                        <div class="hashtags-container">${hashtagsHtml}</div>
                    </div>
                    <section class="gemini-chat" id="geminiChat-${rank}" aria-label="Chat de edição do corte ${rank}">
                        <button type="button" class="gemini-chat-toggle" data-action="toggle-gemini" aria-expanded="false" aria-controls="geminiBody-${rank}">
                            <span class="gemini-identity">
                                <span class="gemini-mark" aria-hidden="true">✦</span>
                                <span><strong>Editar com Gemini</strong><small>Converse para ajustar este corte</small></span>
                            </span>
                            <span class="gemini-model-badge" id="geminiModel-${rank}">Gemini 3.6 Flash</span>
                        </button>
                        <div class="gemini-chat-body" id="geminiBody-${rank}" hidden>
                            <div class="gemini-messages" id="geminiMessages-${rank}" role="log" aria-live="polite">
                                <div class="gemini-message" data-role="assistant">Posso mudar o trecho, enquadramento, selo, áudio, trilha sonora e imagem inicial. Descreva o resultado que você quer.</div>
                            </div>
                            <div class="gemini-quick-actions" aria-label="Sugestões rápidas">
                                <button type="button" class="gemini-chip" data-gemini-prompt="Deixe o gancho mais rápido, cortando silêncios do começo e do fim sem passar de 59 segundos.">Gancho mais rápido</button>
                                <button type="button" class="gemini-chip" data-gemini-prompt="Use fundo desfocado e melhore o texto editorial para ficar curto e forte.">Visual para Shorts</button>
                                <button type="button" class="gemini-chip" data-gemini-prompt="Quero uma trilha sonora discreta abaixo do áudio original.">Adicionar trilha</button>
                                <button type="button" class="gemini-chip" data-gemini-prompt="Quero uma imagem inicial por 2 segundos antes do corte.">Imagem inicial</button>
                            </div>
                            <div class="gemini-composer">
                                <textarea id="geminiInput-${rank}" maxlength="1200" aria-label="Pedido de edição para o Gemini" placeholder="Ex.: tire 1 segundo do começo, use crop à direita e coloque a trilha em 15%..."></textarea>
                                <button type="button" class="gemini-send" data-action="gemini-send" aria-label="Enviar pedido ao Gemini">➤</button>
                            </div>
                            <div class="gemini-change-list" id="geminiChanges-${rank}" aria-live="polite"></div>
                            <p class="unsupported-note">A IA aplica ajustes reversíveis à configuração. O MP4 só é criado depois da sua revisão e confirmação.</p>
                        </div>
                    </section>
                    <div class="card-operation-status" id="cardStatus-${rank}" data-state="idle" role="status"></div>
                    <div class="drive-progress drive-progress-card" id="driveProgress-${rank}" hidden aria-live="polite" data-state="pending" data-mode="indeterminate">
                        <div class="drive-progress-header">
                            <strong>☁️ Envio deste corte</strong>
                            <span data-drive-percent>aguardando</span>
                        </div>
                        <div class="drive-progress-track" data-drive-track role="progressbar" aria-label="Progresso do upload do corte ${rank} ao Google Drive" aria-valuemin="0" aria-valuemax="100">
                            <div class="drive-progress-fill" data-drive-fill></div>
                        </div>
                        <div class="drive-progress-copy" data-drive-copy>Upload aguardando a conclusão do MP4.</div>
                        <div class="drive-progress-steps" aria-label="Etapas do envio deste corte ao Drive">
                            <span data-drive-step="auth" data-state="pending">Autenticação</span>
                            <span data-drive-step="upload" data-state="pending">Envio</span>
                            <span data-drive-step="link" data-state="pending">Link</span>
                        </div>
                    </div>
                    <div class="btn-group" id="btnGroup-${rank}">
                        <button class="btn-action btn-review" data-action="review">⚙️ Revisar e configurar</button>
                    </div>
                    <section class="clip-editor" id="editor-${rank}" hidden aria-label="Editor do corte ${rank}">
                        <div class="editor-header">
                            <strong>Configuração do corte #${rank}</strong>
                            <span class="editor-state" id="editorState-${rank}">Aguardando revisão</span>
                        </div>

                        <div class="control-section">
                            <h4>1. Trecho contínuo</h4>
                            <div class="control-grid">
                                <label class="control-field">
                                    <span>Início exato (segundos)</span>
                                    <input type="number" min="0" step="0.1" value="${startValue}" data-editor-field="start" id="start-${rank}">
                                    <span class="nudge-controls">
                                        <button type="button" class="btn-small" data-nudge="start:-0.5">−0,5 s</button>
                                        <button type="button" class="btn-small" data-nudge="start:0.5">+0,5 s</button>
                                    </span>
                                </label>
                                <label class="control-field">
                                    <span>Fim exato (segundos)</span>
                                    <input type="number" min="0" step="0.1" value="${endValue}" data-editor-field="end" id="end-${rank}">
                                    <span class="nudge-controls">
                                        <button type="button" class="btn-small" data-nudge="end:-0.5">−0,5 s</button>
                                        <button type="button" class="btn-small" data-nudge="end:0.5">+0,5 s</button>
                                    </span>
                                </label>
                            </div>
                            <button type="button" class="btn-action btn-preview-range" data-action="preview-range">▶️ Reproduzir nesta tela</button>
                            <p class="unsupported-note">Este editor gera um único intervalo contínuo; seleção de frases ou cenas separadas ainda não está disponível.</p>
                        </div>

                        <div class="control-section">
                            <h4>2. Visual e áudio</h4>
                            <div class="control-grid">
                                <label class="control-field">
                                    <span>Enquadramento 9:16</span>
                                    <select data-editor-field="format" id="format-${rank}">
                                        <option value="blur_background">Fundo desfocado</option>
                                        <option value="split_blur">Fundo desfocado (split)</option>
                                        <option value="crop_center">Crop vertical</option>
                                    </select>
                                </label>
                                <label class="control-field">
                                    <span>Foco horizontal do crop</span>
                                    <select data-editor-field="crop_focus" id="cropFocus-${rank}" disabled>
                                        <option value="left">Esquerda</option>
                                        <option value="center" selected>Centro</option>
                                        <option value="right">Direita</option>
                                    </select>
                                </label>
                                <label class="control-field">
                                    <span>Intensidade do desfoque</span>
                                    <span class="range-row">
                                        <input type="range" min="0" max="50" step="1" value="12" data-editor-field="blur_sigma" id="blurSigma-${rank}">
                                        <output id="blurValue-${rank}">12</output>
                                    </span>
                                </label>
                                <label class="control-field">
                                    <span>Posição do selo editorial</span>
                                    <select data-editor-field="overlay_position" id="overlayPosition-${rank}">
                                        <option value="top">Topo</option>
                                        <option value="bottom">Rodapé</option>
                                    </select>
                                </label>
                            </div>
                            <label class="toggle-row">
                                <input type="checkbox" checked data-editor-field="include_audio" id="includeAudio-${rank}">
                                <span><strong>Incluir áudio no arquivo</strong><br><span class="unsupported-note">Mantém o áudio original e permite trilha. Desmarque para gerar um MP4 totalmente silencioso.</span></span>
                            </label>
                            <label class="control-field" style="margin-top: 0.8rem;">
                                <span>Selo editorial sobreposto (obrigatório neste fluxo)</span>
                                <input type="text" maxlength="90" required value="${escapeHtml(overlayDefault)}" data-editor-field="overlay_text" id="overlayText-${rank}">
                            </label>
                            <div class="asset-controls">
                                <label class="toggle-row rights-row">
                                    <input type="checkbox" id="assetRights-${rank}">
                                    <span><strong>Confirmo que tenho direito de usar os arquivos anexados.</strong><br><span class="unsupported-note">Use somente mídia própria, licenciada ou autorizada.</span></span>
                                </label>
                                <div class="asset-grid">
                                    <div class="asset-card">
                                        <strong>🎵 Trilha sonora</strong>
                                        <input type="file" id="musicFile-${rank}" accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/mpeg,audio/wav,audio/aac,audio/ogg,audio/flac" hidden>
                                        <input type="hidden" id="musicAssetId-${rank}" data-editor-field="background_music_asset_id" value="">
                                        <input type="hidden" id="musicAssetName-${rank}" value="">
                                        <button type="button" class="asset-upload-button" data-action="attach-music">Anexar áudio</button>
                                        <span class="asset-file-label" id="musicAssetLabel-${rank}">Nenhuma trilha anexada</span>
                                        <label class="toggle-row">
                                            <input type="checkbox" id="musicEnabled-${rank}" data-editor-field="music_enabled">
                                            <span>Usar no render</span>
                                        </label>
                                        <label class="control-field">
                                            <span>Volume da trilha</span>
                                            <span class="range-row">
                                                <input type="range" min="0" max="1" step="0.05" value="0.2" id="musicVolume-${rank}" data-editor-field="music_volume">
                                                <output id="musicVolumeValue-${rank}">20%</output>
                                            </span>
                                        </label>
                                    </div>
                                    <div class="asset-card">
                                        <strong>🖼️ Imagem inicial</strong>
                                        <input type="file" id="introFile-${rank}" accept="image/jpeg,image/png,image/webp" hidden>
                                        <input type="hidden" id="introAssetId-${rank}" data-editor-field="intro_image_asset_id" value="">
                                        <input type="hidden" id="introAssetName-${rank}" value="">
                                        <button type="button" class="asset-upload-button" data-action="attach-intro">Anexar imagem</button>
                                        <span class="asset-file-label" id="introAssetLabel-${rank}">Nenhuma imagem anexada</span>
                                        <label class="toggle-row">
                                            <input type="checkbox" id="introEnabled-${rank}" data-editor-field="intro_enabled">
                                            <span>Mostrar antes do vídeo</span>
                                        </label>
                                        <label class="control-field">
                                            <span>Duração da abertura</span>
                                            <input type="number" min="0.5" max="5" step="0.5" value="2" id="introDuration-${rank}" data-editor-field="intro_duration">
                                        </label>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="control-section">
                            <h4>3. Conteúdo incluído e entrega</h4>
                            <label class="toggle-row">
                                <input type="checkbox" disabled>
                                <span>Legendas queimadas — <strong>não incluídas</strong> neste render rápido</span>
                            </label>
                            <label class="toggle-row">
                                <input type="checkbox" disabled>
                                <span>Narração — <strong>não incluída</strong> neste render rápido</span>
                            </label>
                            <label class="toggle-row">
                                <input type="checkbox" data-editor-field="gdrive" id="gdrive-${rank}">
                                <span><strong>Enviar também ao Google Drive</strong><br><span class="unsupported-note">O arquivo local é sempre gerado. Upload é uma etapa separada e pode terminar parcialmente.</span></span>
                            </label>
                        </div>

                        <div class="inclusion-summary" id="configSummary-${rank}" aria-live="polite"></div>
                        <label class="toggle-row confirmation-row">
                            <input type="checkbox" data-editor-field="confirmed_configuration" id="confirm-${rank}">
                            <span><strong>Revisei o resumo acima e confirmo esta configuração.</strong><br>Qualquer alteração exige nova confirmação antes de renderizar.</span>
                        </label>
                        <div class="editor-validation" id="editorValidation-${rank}" role="alert"></div>
                        <button type="button" class="btn-action btn-clip btn-confirm" data-action="confirm-generate" disabled>Confirmar e gerar MP4</button>
                    </section>
                    <section class="render-receipt" id="receipt-${rank}" hidden aria-live="polite"></section>
                    <div class="btn-group result-actions" id="resultActions-${rank}" hidden></div>
                `;
                grid.appendChild(card);
                setCardSourcePreview(rank);

                card.querySelector('[data-action="review"]').addEventListener('click', () => {
                    setEditorOpen(rank, document.getElementById(`editor-${rank}`).hidden);
                });
                card.querySelector('[data-action="preview-range"]').addEventListener('click', () => {
                    previewSelectedRange(rank);
                });
                card.querySelector('[data-action="play-card-preview"]').addEventListener('click', () => {
                    playCardPreview(rank);
                });
                card.querySelector('[data-action="confirm-generate"]').addEventListener('click', event => {
                    generateClip(videoUrl, rank, event.currentTarget);
                });
                card.querySelector('[data-action="toggle-gemini"]').addEventListener('click', event => {
                    toggleGeminiChat(rank, event.currentTarget);
                });
                card.querySelector('[data-action="gemini-send"]').addEventListener('click', event => {
                    sendGeminiMessage(rank, event.currentTarget);
                });
                card.querySelector(`#geminiInput-${rank}`).addEventListener('keydown', event => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        sendGeminiMessage(rank, card.querySelector('[data-action="gemini-send"]'));
                    }
                });
                card.querySelectorAll('[data-gemini-prompt]').forEach(button => {
                    button.addEventListener('click', () => {
                        document.getElementById(`geminiInput-${rank}`).value = button.dataset.geminiPrompt;
                        sendGeminiMessage(rank, card.querySelector('[data-action="gemini-send"]'));
                    });
                });
                card.querySelector('[data-action="attach-music"]').addEventListener('click', () => document.getElementById(`musicFile-${rank}`).click());
                card.querySelector('[data-action="attach-intro"]').addEventListener('click', () => document.getElementById(`introFile-${rank}`).click());
                document.getElementById(`musicFile-${rank}`).addEventListener('change', event => {
                    if (event.target.files[0]) uploadEditorAsset(rank, 'music', event.target.files[0], event.target);
                });
                document.getElementById(`introFile-${rank}`).addEventListener('change', event => {
                    if (event.target.files[0]) uploadEditorAsset(rank, 'intro_image', event.target.files[0], event.target);
                });
                card.querySelectorAll('[data-nudge]').forEach(button => {
                    button.addEventListener('click', () => {
                        const [field, delta] = button.dataset.nudge.split(':');
                        nudgeEditorTime(rank, field, Number(delta));
                    });
                });
                card.querySelectorAll('[data-editor-field]').forEach(field => {
                    const eventName = field.type === 'range' || field.type === 'text' || field.type === 'number'
                        ? 'input'
                        : 'change';
                    field.addEventListener(eventName, () => editorFieldChanged(rank, field));
                });
                updateEditorSummary(rank);
            });
        }

        function toggleGeminiChat(rank, button) {
            const body = document.getElementById(`geminiBody-${rank}`);
            if (!body) return;
            const open = body.hidden;
            body.hidden = !open;
            button.setAttribute('aria-expanded', String(open));
            if (open) window.setTimeout(() => document.getElementById(`geminiInput-${rank}`)?.focus(), 0);
        }

        function appendGeminiMessage(rank, role, text, state = '') {
            const messages = document.getElementById(`geminiMessages-${rank}`);
            if (!messages) return null;
            const message = document.createElement('div');
            message.className = 'gemini-message';
            message.dataset.role = role;
            if (state) message.dataset.state = state;
            message.textContent = String(text || '');
            messages.appendChild(message);
            while (messages.children.length > 24) messages.firstElementChild.remove();
            messages.scrollTop = messages.scrollHeight;
            return message;
        }

        function showGeminiChanges(rank, patch) {
            const target = document.getElementById(`geminiChanges-${rank}`);
            if (!target) return;
            target.replaceChildren();
            const labels = {
                start: 'início', end: 'fim', format: 'enquadramento', crop_focus: 'foco',
                blur_sigma: 'desfoque', include_audio: 'áudio original', overlay_text: 'selo',
                overlay_position: 'posição do selo', music_enabled: 'trilha', music_volume: 'volume da trilha',
                intro_enabled: 'imagem inicial', intro_duration: 'duração da abertura'
            };
            Object.keys(patch || {}).forEach(key => {
                if (!labels[key]) return;
                const chip = document.createElement('span');
                chip.className = 'gemini-change';
                chip.textContent = `✓ ${labels[key]}`;
                target.appendChild(chip);
            });
        }

        function applyGeminiPatch(rank, patch) {
            if (!patch || typeof patch !== 'object') return;
            const mapping = {
                start: [`start-${rank}`, 'value'],
                end: [`end-${rank}`, 'value'],
                format: [`format-${rank}`, 'value'],
                crop_focus: [`cropFocus-${rank}`, 'value'],
                blur_sigma: [`blurSigma-${rank}`, 'value'],
                include_audio: [`includeAudio-${rank}`, 'checked'],
                overlay_text: [`overlayText-${rank}`, 'value'],
                overlay_position: [`overlayPosition-${rank}`, 'value'],
                music_enabled: [`musicEnabled-${rank}`, 'checked'],
                music_volume: [`musicVolume-${rank}`, 'value'],
                intro_enabled: [`introEnabled-${rank}`, 'checked'],
                intro_duration: [`introDuration-${rank}`, 'value']
            };
            Object.entries(patch).forEach(([key, value]) => {
                const spec = mapping[key];
                if (!spec) return;
                const element = document.getElementById(spec[0]);
                if (!element) return;
                if (spec[1] === 'checked') element.checked = Boolean(value);
                else element.value = String(value);
            });
            const confirmation = document.getElementById(`confirm-${rank}`);
            if (confirmation) confirmation.checked = false;
            const card = document.getElementById(`card-${rank}`);
            if (card && !document.getElementById(`receipt-${rank}`).hidden) card.dataset.dirtyAfterRender = 'true';
            updateEditorSummary(rank);
            if (Object.prototype.hasOwnProperty.call(patch, 'start') || Object.prototype.hasOwnProperty.call(patch, 'end')) {
                scheduleCardSourcePreview(rank);
            }
            showGeminiChanges(rank, patch);
        }

        async function sendGeminiMessage(rank, button) {
            const card = document.getElementById(`card-${rank}`);
            const input = document.getElementById(`geminiInput-${rank}`);
            const message = input?.value.trim();
            if (!card || !input || !message || button.disabled) return;
            const previousHistory = Array.isArray(card.geminiHistory) ? card.geminiHistory.slice(-10) : [];
            appendGeminiMessage(rank, 'user', message);
            input.value = '';
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            const oldLabel = button.textContent;
            button.textContent = '…';
            const typing = appendGeminiMessage(rank, 'assistant', 'Analisando este corte…');
            const controller = new AbortController();
            const timer = window.setTimeout(() => controller.abort(), 60000);
            try {
                const response = await fetch('/api/editor-chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Request-ID': createRequestId() },
                    body: JSON.stringify({
                        message,
                        clip: card.geminiContext || {},
                        config: editorConfig(rank),
                        history: previousHistory
                    }),
                    signal: controller.signal
                });
                let data;
                try { data = await response.json(); }
                catch (_) { data = { success: false, error: `Resposta HTTP ${response.status} inválida.` }; }
                if (typing) typing.remove();
                if (!response.ok || !data.success) {
                    const error = data.error || (response.status === 503
                        ? 'Configure GEMINI_API_KEY no servidor para ativar o chat.'
                        : `O Gemini não respondeu (HTTP ${response.status}).`);
                    appendGeminiMessage(rank, 'assistant', error, 'error');
                    return;
                }
                const modelBadge = document.getElementById(`geminiModel-${rank}`);
                if (modelBadge && typeof data.model === 'string' && data.model.trim()) {
                    modelBadge.textContent = data.model.trim();
                }
                const reply = data.reply || 'Ajustei a configuração deste corte.';
                const patch = data.patch && typeof data.patch === 'object' ? data.patch : {};
                appendGeminiMessage(rank, 'assistant', reply);
                applyGeminiPatch(rank, patch);
                card.geminiHistory = [...previousHistory,
                    { role: 'user', content: message },
                    { role: 'assistant', content: reply }].slice(-12);
                const needsAsset = Array.isArray(data.needs_asset) ? data.needs_asset : [];
                if (needsAsset.length) {
                    const labels = needsAsset.map(item => item === 'music' ? 'uma trilha sonora' : 'uma imagem inicial');
                    appendGeminiMessage(rank, 'assistant', `Para concluir, abra “Revisar e configurar” e anexe ${labels.join(' e ')} que você tenha direito de usar.`);
                }
                if (Object.keys(patch).length) setCardStatus(rank, 'warning', 'Ajustes do Gemini aplicados. Revise e confirme antes de renderizar.');
            } catch (error) {
                if (typing) typing.remove();
                appendGeminiMessage(rank, 'assistant', error.name === 'AbortError'
                    ? 'O Gemini demorou demais para responder. Tente novamente.'
                    : 'Não foi possível conversar com o Gemini agora.', 'error');
            } finally {
                window.clearTimeout(timer);
                button.disabled = false;
                button.removeAttribute('aria-busy');
                button.textContent = oldLabel;
            }
        }

        function readFileAsDataUrl(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || ''));
                reader.onerror = () => reject(new Error('Não foi possível ler o arquivo.'));
                reader.readAsDataURL(file);
            });
        }

        async function uploadEditorAsset(rank, kind, file, fileInput) {
            const rights = document.getElementById(`assetRights-${rank}`);
            const isMusic = kind === 'music';
            const maxBytes = isMusic ? 25 * 1024 * 1024 : 8 * 1024 * 1024;
            if (!rights.checked) {
                setCardStatus(rank, 'error', 'Confirme que você tem direito de usar o arquivo antes de anexá-lo.');
                fileInput.value = '';
                return;
            }
            if (!file.size || file.size > maxBytes) {
                setCardStatus(rank, 'error', `O arquivo deve ter no máximo ${isMusic ? 25 : 8} MB.`);
                fileInput.value = '';
                return;
            }
            const uploadButton = document.querySelector(`#card-${rank} [data-action="${isMusic ? 'attach-music' : 'attach-intro'}"]`);
            uploadButton.disabled = true;
            uploadButton.textContent = 'Enviando…';
            setCardStatus(rank, 'running', `Enviando ${isMusic ? 'trilha sonora' : 'imagem inicial'}…`);
            try {
                const dataUrl = await readFileAsDataUrl(file);
                const response = await fetch('/api/editor-assets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Request-ID': createRequestId() },
                    body: JSON.stringify({
                        kind,
                        file_name: file.name,
                        mime_type: file.type,
                        data_base64: dataUrl,
                        rights_confirmed: true
                    })
                });
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.error || `Falha HTTP ${response.status}`);
                const prefix = isMusic ? 'music' : 'intro';
                document.getElementById(`${prefix}AssetId-${rank}`).value = data.asset_id;
                document.getElementById(`${prefix}AssetName-${rank}`).value = data.file_name;
                document.getElementById(`${prefix}AssetLabel-${rank}`).textContent = `${data.file_name} · ${formatFileSize(data.size_bytes)}`;
                document.getElementById(`${isMusic ? 'musicEnabled' : 'introEnabled'}-${rank}`).checked = true;
                editorFieldChanged(rank, { dataset: { editorField: `${kind}_asset` } });
                setCardStatus(rank, 'success', `${isMusic ? 'Trilha' : 'Imagem inicial'} anexada e ativada.`);
            } catch (error) {
                setCardStatus(rank, 'error', `Falha ao anexar arquivo: ${error.message}`);
            } finally {
                uploadButton.disabled = false;
                uploadButton.textContent = isMusic ? 'Trocar áudio' : 'Trocar imagem';
                fileInput.value = '';
            }
        }

        function setEditorOpen(rank, open) {
            const card = document.getElementById(`card-${rank}`);
            const editor = document.getElementById(`editor-${rank}`);
            const review = card && card.querySelector('[data-action="review"]');
            if (!card || !editor) return;
            editor.hidden = !open;
            card.classList.toggle('editor-open', open);
            if (review) review.textContent = open ? 'Fechar configuração' : '⚙️ Revisar e configurar';
            if (open) {
                updateEditorSummary(rank);
                editor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }

        function editorConfig(rank) {
            return {
                start: document.getElementById(`start-${rank}`).valueAsNumber,
                end: document.getElementById(`end-${rank}`).valueAsNumber,
                format: document.getElementById(`format-${rank}`).value,
                crop_focus: document.getElementById(`cropFocus-${rank}`).value,
                blur_sigma: Number(document.getElementById(`blurSigma-${rank}`).value),
                include_audio: document.getElementById(`includeAudio-${rank}`).checked,
                overlay_text: document.getElementById(`overlayText-${rank}`).value.trim(),
                overlay_position: document.getElementById(`overlayPosition-${rank}`).value,
                music_enabled: document.getElementById(`musicEnabled-${rank}`).checked,
                music_volume: Number(document.getElementById(`musicVolume-${rank}`).value),
                background_music_asset_id: document.getElementById(`musicAssetId-${rank}`).value,
                background_music_asset_name: document.getElementById(`musicAssetName-${rank}`).value,
                intro_enabled: document.getElementById(`introEnabled-${rank}`).checked,
                intro_duration: Number(document.getElementById(`introDuration-${rank}`).value),
                intro_image_asset_id: document.getElementById(`introAssetId-${rank}`).value,
                intro_image_asset_name: document.getElementById(`introAssetName-${rank}`).value,
                gdrive: document.getElementById(`gdrive-${rank}`).checked,
                confirmed_configuration: document.getElementById(`confirm-${rank}`).checked
            };
        }

        function editorFieldChanged(rank, field) {
            const card = document.getElementById(`card-${rank}`);
            const confirmation = document.getElementById(`confirm-${rank}`);
            if (field.dataset.editorField !== 'confirmed_configuration') {
                confirmation.checked = false;
                if (card && !document.getElementById(`receipt-${rank}`).hidden) {
                    card.dataset.dirtyAfterRender = 'true';
                    setCardStatus(rank, 'warning', 'Alterações não renderizadas. Confirme para gerar uma nova versão.');
                }
            }
            updateEditorSummary(rank);
            if (field?.dataset?.editorField === 'start' || field?.dataset?.editorField === 'end') {
                scheduleCardSourcePreview(rank);
            }
        }

        function nudgeEditorTime(rank, field, delta) {
            const input = document.getElementById(`${field}-${rank}`);
            const current = Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : 0;
            input.value = Math.max(0, current + delta).toFixed(1);
            editorFieldChanged(rank, input);
        }

        function updateEditorSummary(rank) {
            const config = editorConfig(rank);
            const card = document.getElementById(`card-${rank}`);
            const duration = config.end - config.start;
            const totalDuration = duration + (config.intro_enabled ? config.intro_duration : 0);
            const errors = [];
            if (!Number.isFinite(config.start) || config.start < 0) errors.push('Início inválido.');
            if (!Number.isFinite(config.end) || config.end <= config.start) errors.push('O fim deve ser maior que o início.');
            if (Number.isFinite(totalDuration) && totalDuration > 59.9) errors.push('O corte final, incluindo a abertura, pode ter no máximo 59,9 segundos.');
            if (!config.overlay_text) errors.push('Informe o texto do selo editorial.');
            if (config.overlay_text.length > 90) errors.push('O selo editorial aceita no máximo 90 caracteres.');
            if (config.music_enabled && !config.background_music_asset_id) errors.push('Anexe a trilha sonora solicitada.');
            if (config.music_enabled && !config.include_audio) errors.push('Ative o áudio para usar a trilha sonora.');
            if (!Number.isFinite(config.music_volume) || config.music_volume < 0 || config.music_volume > 1) errors.push('Volume da trilha inválido.');
            if (config.intro_enabled && !config.intro_image_asset_id) errors.push('Anexe a imagem inicial solicitada.');
            if (!Number.isFinite(config.intro_duration) || config.intro_duration < 0.5 || config.intro_duration > 5) errors.push('A abertura deve durar de 0,5 a 5 segundos.');

            const isCrop = config.format === 'crop_center';
            document.getElementById(`cropFocus-${rank}`).disabled = !isCrop;
            document.getElementById(`blurSigma-${rank}`).disabled = isCrop;
            document.getElementById(`blurValue-${rank}`).value = String(config.blur_sigma);
            document.getElementById(`musicVolumeValue-${rank}`).value = `${Math.round(config.music_volume * 100)}%`;

            const focusLabels = { left: 'esquerda', center: 'centro', right: 'direita' };
            const formatLabel = isCrop
                ? `crop vertical, foco ${focusLabels[config.crop_focus]}`
                : `fundo desfocado, intensidade ${config.blur_sigma}`;
            const included = ['vídeo no intervalo', 'selo editorial', config.include_audio ? 'áudio original' : null,
                config.music_enabled && config.background_music_asset_id ? `trilha ${config.background_music_asset_name || 'anexada'} (${Math.round(config.music_volume * 100)}%)` : null,
                config.intro_enabled && config.intro_image_asset_id ? `imagem inicial (${config.intro_duration.toFixed(1)} s)` : null]
                .filter(Boolean);
            const excluded = ['legendas queimadas', 'narração', 'hashtags visuais', config.include_audio ? null : 'áudio original',
                config.music_enabled ? null : 'trilha sonora', config.intro_enabled ? null : 'imagem inicial']
                .filter(Boolean);
            const destination = config.gdrive ? 'arquivo local + Google Drive' : 'somente arquivo local';
            document.getElementById(`configSummary-${rank}`).innerHTML = `
                <div class="summary-title">Corte #${rank} · ${formatTimecode(config.start)}–${formatTimecode(config.end)} · ${Number.isFinite(totalDuration) ? totalDuration.toFixed(2) : '?'} s finais</div>
                <div>1080×1920 (9:16), ${escapeHtml(formatLabel)}</div>
                <div class="included-line">✓ Incluído: ${escapeHtml(included.join(', '))}</div>
                <div class="excluded-line">○ Não incluído: ${escapeHtml(excluded.join(', '))}</div>
                <div>Entrega: ${escapeHtml(destination)}</div>
            `;
            document.getElementById(`cardTime-${rank}`).textContent = `⏱ ${formatTimecode(config.start)} ➔ ${formatTimecode(config.end)} (${Number.isFinite(duration) ? duration.toFixed(2) : '?'}s)`;
            document.getElementById(`editorValidation-${rank}`).textContent = errors.join(' ');
            const generateButton = card.querySelector('[data-action="confirm-generate"]');
            generateButton.disabled = errors.length > 0 || !config.confirmed_configuration;
            generateButton.textContent = config.gdrive
                ? 'Confirmar, gerar MP4 e enviar ao Drive'
                : 'Confirmar e gerar MP4';

            const state = document.getElementById(`editorState-${rank}`);
            if (card.dataset.dirtyAfterRender === 'true') {
                state.textContent = 'Alterações não renderizadas';
            } else if (errors.length > 0) {
                state.textContent = 'Ajustes necessários';
            } else if (config.confirmed_configuration) {
                state.textContent = 'Configuração confirmada';
            } else {
                state.textContent = 'Aguardando confirmação';
            }
        }

        function buildCardPreviewUrl(videoId, start, end, autoplay = false) {
            const previewStart = Math.max(0, Math.floor(start));
            const previewEnd = Math.max(previewStart + 1, Math.ceil(end));
            const params = new URLSearchParams({
                start: String(previewStart),
                end: String(previewEnd),
                rel: '0',
                modestbranding: '1',
                playsinline: '1'
            });
            if (autoplay) params.set('autoplay', '1');
            return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(videoId)}?${params.toString()}`;
        }

        function stopOtherCardPreviews(activeRank) {
            document.querySelectorAll(`[id^="clipSourcePreview-"]`).forEach(source => {
                const otherRank = Number(source.id.replace("clipSourcePreview-", ""));
                if (!Number.isFinite(otherRank) || otherRank === Number(activeRank)) return;
                const output = document.getElementById(`clipOutputPreview-${otherRank}`);
                if (output && !output.hidden) output.pause();
                if (source.hidden) return;
                source.removeAttribute("src");
                delete source.dataset.previewSignature;
                source.hidden = true;
                const placeholder = document.getElementById(`clipSuggestionPlaceholder-${otherRank}`);
                const state = document.getElementById(`cardPreviewState-${otherRank}`);
                const card = document.getElementById(`card-${otherRank}`);
                const button = card?.querySelector(`[data-action="play-card-preview"]`);
                if (placeholder) placeholder.hidden = false;
                if (state) state.textContent = `Sugestão #${otherRank} pausada`;
                if (button) button.textContent = `▶ Reproduzir sugestão #${otherRank}`;
            });
        }

        function setCardSourcePreview(rank, { autoplay = false, force = false } = {}) {
            const card = document.getElementById(`card-${rank}`);
            const source = document.getElementById(`clipSourcePreview-${rank}`);
            const output = document.getElementById(`clipOutputPreview-${rank}`);
            const placeholder = document.getElementById(`clipSuggestionPlaceholder-${rank}`);
            const screen = document.getElementById(`cardPreviewScreen-${rank}`);
            const state = document.getElementById(`cardPreviewState-${rank}`);
            const detail = document.getElementById(`cardPreviewDetail-${rank}`);
            const button = card?.querySelector(`[data-action="play-card-preview"]`);
            if (!card || !source || !output || !placeholder || !screen || !state || !detail) return false;

            const config = editorConfig(rank);
            const videoId = getYouTubeVideoId(card.dataset.videoUrl || "");
            if (!videoId || !Number.isFinite(config.start) || !Number.isFinite(config.end) || config.end <= config.start) {
                state.textContent = "Ajuste o intervalo para pré-visualizar";
                detail.textContent = "Início e fim precisam formar um trecho válido";
                source.removeAttribute("src");
                source.hidden = true;
                placeholder.hidden = false;
                return false;
            }

            if (!force && !output.hidden) {
                state.textContent = "MP4 vertical desta versão";
                detail.textContent = "Clique para reproduzir a sugestão original deste card";
                return true;
            }

            const previewUrl = buildCardPreviewUrl(videoId, config.start, config.end, autoplay);
            const signature = `${videoId}:${Math.floor(config.start)}:${Math.ceil(config.end)}:${autoplay ? "play" : "idle"}`;
            source.dataset.previewUrl = previewUrl;

            if (!autoplay) {
                source.removeAttribute("src");
                delete source.dataset.previewSignature;
                source.hidden = true;
                placeholder.hidden = false;
                if (!output.hidden) output.pause();
                output.hidden = true;
                screen.dataset.previewMode = "source";
                state.textContent = `Sugestão #${rank} pronta`;
                detail.textContent = `Trecho ${formatTimecode(config.start)}–${formatTimecode(config.end)} · clique para reproduzir`;
                if (button) button.textContent = `▶ Reproduzir sugestão #${rank}`;
                return true;
            }

            stopOtherCardPreviews(rank);
            if (force || source.dataset.previewSignature !== signature || !source.getAttribute("src")) {
                source.src = previewUrl;
                source.dataset.previewSignature = signature;
            }
            if (!output.hidden) output.pause();
            output.hidden = true;
            placeholder.hidden = true;
            source.hidden = false;
            screen.dataset.previewMode = "source";
            state.textContent = `Reproduzindo sugestão #${rank}`;
            detail.textContent = `YouTube · ${formatTimecode(config.start)}–${formatTimecode(config.end)} · somente este intervalo`;
            if (button) {
                button.textContent = output.getAttribute("src")
                    ? "▶ Ver MP4 desta versão"
                    : `↻ Reiniciar sugestão #${rank}`;
            }
            return true;
        }

        function scheduleCardSourcePreview(rank) {
            const card = document.getElementById(`card-${rank}`);
            if (!card) return;
            window.clearTimeout(card.previewRefreshTimer);
            card.previewRefreshTimer = window.setTimeout(() => {
                const output = document.getElementById(`clipOutputPreview-${rank}`);
                if (output?.hidden) setCardSourcePreview(rank);
                else {
                    const detail = document.getElementById(`cardPreviewDetail-${rank}`);
                    if (detail) detail.textContent = 'Há ajustes novos: clique para revisar o trecho original.';
                }
            }, 450);
        }

        function showCardRenderedPreview(rank, { autoplay = false } = {}) {
            const source = document.getElementById(`clipSourcePreview-${rank}`);
            const output = document.getElementById(`clipOutputPreview-${rank}`);
            const placeholder = document.getElementById(`clipSuggestionPlaceholder-${rank}`);
            const screen = document.getElementById(`cardPreviewScreen-${rank}`);
            const state = document.getElementById(`cardPreviewState-${rank}`);
            const detail = document.getElementById(`cardPreviewDetail-${rank}`);
            const card = document.getElementById(`card-${rank}`);
            const button = card?.querySelector('[data-action="play-card-preview"]');
            if (!source || !output || !placeholder || !screen || !state || !detail || !output.getAttribute("src")) return false;
            source.hidden = true;
            placeholder.hidden = true;
            output.hidden = false;
            screen.dataset.previewMode = 'rendered';
            state.textContent = 'MP4 vertical desta versão';
            detail.textContent = 'Resultado renderizado deste corte';
            if (button) button.textContent = `↩ Reproduzir sugestão #${rank}`;
            if (autoplay) {
                output.play().catch(() => {
                    appendActivity(`Preview do MP4 do corte #${rank} pronto; reprodução automática bloqueada pelo navegador.`, 'warning');
                });
            }
            return true;
        }

        function setCardRenderedPreview(rank, downloadUrl) {
            const source = document.getElementById(`clipSourcePreview-${rank}`);
            const output = document.getElementById(`clipOutputPreview-${rank}`);
            const screen = document.getElementById(`cardPreviewScreen-${rank}`);
            const state = document.getElementById(`cardPreviewState-${rank}`);
            const detail = document.getElementById(`cardPreviewDetail-${rank}`);
            const card = document.getElementById(`card-${rank}`);
            const button = card?.querySelector('[data-action="play-card-preview"]');
            if (!source || !output || !screen || !state || !detail || !downloadUrl) return null;
            output.src = downloadUrl;
            output.onerror = () => {
                detail.textContent = 'Não foi possível carregar o MP4 desta versão.';
                setCardStatus(rank, 'error', 'Falha ao carregar o preview do MP4 deste corte.');
            };
            showCardRenderedPreview(rank);
            return output;
        }

        function playCardPreview(rank) {
            const source = document.getElementById(`clipSourcePreview-${rank}`);
            const output = document.getElementById(`clipOutputPreview-${rank}`);
            if (source && !source.hidden && output?.hidden && output.getAttribute("src")) {
                const rendered = showCardRenderedPreview(rank, { autoplay: true });
                if (rendered) {
                    document.getElementById(`cardPreviewScreen-${rank}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    return true;
                }
            }
            const refreshed = setCardSourcePreview(rank, { autoplay: true, force: true });
            if (!refreshed) {
                setCardStatus(rank, 'error', 'Não foi possível abrir o preview: revise o intervalo.');
                return false;
            }
            document.getElementById(`cardPreviewScreen-${rank}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            appendActivity(`Preview do intervalo do corte #${rank} aberto na própria tela do card.`, 'running');
            return true;
        }

        function previewSelectedRange(rank) {
            const refreshed = setCardSourcePreview(rank, { autoplay: true, force: true });
            if (!refreshed) {
                setCardStatus(rank, 'error', 'Não foi possível abrir o preview: revise o intervalo.');
                return;
            }
            document.getElementById(`cardPreviewScreen-${rank}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            appendActivity(`Preview do intervalo do corte #${rank} atualizado na própria tela do card.`, 'running');
        }

        function renderReceipt(data, rank) {
            const receiptElement = document.getElementById(`receipt-${rank}`);
            const receipt = data.render_receipt;
            if (!receipt || !receipt.applied_settings) {
                receiptElement.hidden = false;
                receiptElement.innerHTML = '<strong>O servidor não devolveu um recibo de configuração.</strong>';
                return;
            }
            const settings = receipt.applied_settings;
            const overlay = settings.editorial_overlay || {};
            const resolution = settings.resolution || {};
            const destination = settings.destination || {};
            const generatedAt = receipt.generated_at ? new Date(receipt.generated_at).toLocaleString('pt-BR') : 'não informado';
            const included = Array.isArray(receipt.included) ? receipt.included : [];
            const excluded = Array.isArray(receipt.not_included) ? receipt.not_included : [];
            const file = receipt.file || {};
            const measured = receipt.measured_media || {};
            const measuredOutput = measured.verified
                ? `${measured.width}×${measured.height} · ${measured.duration_seconds} s · ${measured.video_codec}`
                : `${resolution.width}×${resolution.height} ${resolution.aspect_ratio} (configuração aplicada; ffprobe indisponível)`;
            const measuredAudio = measured.verified
                ? (measured.audio_codec && measured.audio_codec !== 'none'
                    ? `${measured.audio_codec}, ${measured.audio_channels || '?'} canal(is)`
                    : 'sem faixa de áudio')
                : (settings.audio_included ? 'AAC solicitado' : 'sem faixa de áudio');
            const focusLabels = { left: 'esquerda', center: 'centro', right: 'direita' };
            const imageDetail = settings.format === 'crop_center'
                ? `foco ${focusLabels[settings.crop_focus] || settings.crop_focus}`
                : `desfoque ${settings.blur_sigma}`;
            const uploadText = destination.gdrive_requested
                ? (destination.gdrive_completed ? 'Drive concluído' : 'Drive solicitado, mas não concluído')
                : 'Drive não solicitado';
            receiptElement.hidden = false;
            receiptElement.innerHTML = `
                <div class="receipt-header">
                    <strong>✓ Recibo de renderização do corte #${rank}</strong>
                    <span>${data.overall_status === 'partial_success' ? 'Concluído parcialmente' : 'Pronto localmente'}</span>
                </div>
                <div class="receipt-id">Operação ${escapeHtml(receipt.request_id)} · ${escapeHtml(generatedAt)}</div>
                <div class="receipt-grid">
                    <div><strong>Intervalo aplicado</strong><br>${formatTimecode(Number(settings.start_seconds))}–${formatTimecode(Number(settings.end_seconds))} (${Number(settings.duration_seconds).toFixed(2)} s)</div>
                    <div><strong>Arquivo</strong><br>${escapeHtml(file.name)} · ${formatFileSize(file.size_bytes)}</div>
                    <div><strong>Imagem</strong><br>${escapeHtml(settings.format_label)} · ${escapeHtml(imageDetail)}</div>
                    <div><strong>Saída medida</strong><br>${escapeHtml(measuredOutput)}</div>
                    <div><strong>Áudio medido</strong><br>${escapeHtml(measuredAudio)}</div>
                    <div><strong>Entrega</strong><br>Arquivo local concluído · ${escapeHtml(uploadText)}</div>
                    <div><strong>Selo editorial</strong><br>${escapeHtml(overlay.text)} · ${overlay.position === 'bottom' ? 'rodapé' : 'topo'}</div>
                    <div><strong>Integridade</strong><br>${file.sha256 ? `${escapeHtml(String(file.sha256).slice(0, 23))}…` : `ID ${escapeHtml(receipt.request_id)}`}</div>
                </div>
                <div class="receipt-list included-line">✓ Incluído: ${escapeHtml(included.join(', '))}</div>
                <div class="receipt-list excluded-line">○ Não incluído: ${escapeHtml(excluded.join(', '))}</div>
            `;
        }

        function updateGeneratedActions(data, rank) {
            const group = document.getElementById(`resultActions-${rank}`);
            if (!group) return;
            group.hidden = false;
            group.replaceChildren();

            const download = document.createElement('a');
            download.href = data.download_url;
            download.download = '';
            download.className = 'btn-action btn-download';
            download.textContent = '⬇️ Baixar esta versão do MP4';
            download.addEventListener('click', () => {
                setCardStatus(rank, 'success', 'Download solicitado ao navegador.');
                appendActivity(`Download do corte #${rank} solicitado.`, 'success');
            });
            group.appendChild(download);

            if (data.gdrive_link) {
                const driveLink = document.createElement('a');
                driveLink.href = data.gdrive_link;
                driveLink.target = '_blank';
                driveLink.rel = 'noopener noreferrer';
                driveLink.className = 'drive-link-badge';
                driveLink.textContent = '🔗 Abrir esta versão no Google Drive';
                group.appendChild(driveLink);
            } else {
                const note = document.createElement('div');
                note.className = 'unsupported-note';
                note.textContent = 'Esta versão não foi enviada ao Drive. Marque o destino no editor e confirme para gerar uma nova versão.';
                group.appendChild(note);
            }

            const edit = document.createElement('button');
            edit.type = 'button';
            edit.className = 'btn-action btn-review';
            edit.textContent = '✏️ Editar e gerar nova versão';
            edit.addEventListener('click', () => setEditorOpen(rank, true));
            group.appendChild(edit);
        }

        async function generateClip(videoUrl, rank, button) {
            const config = editorConfig(rank);
            const card = document.getElementById(`card-${rank}`);
            if (!config.confirmed_configuration) {
                setCardStatus(rank, 'error', 'Revise e confirme a configuração antes de renderizar.');
                return;
            }
            const folderId = document.getElementById('gdriveFolderId').value.trim();
            const state = document.getElementById(`editorState-${rank}`);
            document.getElementById(`confirm-${rank}`).checked = false;
            updateEditorSummary(rank);
            state.textContent = 'Renderizando';
            const result = await trackedPost('/api/generate-clip', {
                url: videoUrl,
                clip_id: card?.dataset.clipId || null,
                project_id: card?.dataset.projectId || null,
                analysis_id: card?.dataset.analysisId || null,
                start: config.start,
                end: config.end,
                format: config.format,
                crop_focus: config.crop_focus,
                blur_sigma: config.blur_sigma,
                include_audio: config.include_audio,
                overlay_text: config.overlay_text,
                overlay_position: config.overlay_position,
                background_music_asset_id: config.music_enabled ? config.background_music_asset_id : null,
                background_music_volume: config.music_volume,
                intro_image_asset_id: config.intro_enabled ? config.intro_image_asset_id : null,
                intro_duration: config.intro_enabled ? config.intro_duration : 0,
                gdrive: config.gdrive,
                folder_id: folderId,
                confirmed_configuration: true
            }, {
                title: config.gdrive ? `Gerando e enviando corte #${rank}` : `Gerando corte #${rank}`,
                message: config.gdrive
                    ? 'Renderizando a configuração confirmada e, em seguida, enviando ao Google Drive.'
                    : 'Renderizando exatamente a configuração confirmada em formato vertical 9:16.',
                button,
                busyLabel: config.gdrive ? '⏳ Renderizando e enviando...' : '⏳ Renderizando corte...',
                rank,
                driveRequested: config.gdrive
            });
            if (result.error) {
                state.textContent = 'Falhou';
                return;
            }
            const { response, data, context } = result;
            if (!response.ok || !data.success) {
                state.textContent = 'Falhou';
                if (config.gdrive) renderDriveProgress({ state: "failed" }, rank);
                await finishOperation(
                    context,
                    'error',
                    `Corte #${rank} não gerado`,
                    data.error || `Falha HTTP ${response.status}`
                );
                return;
            }

            if (data.download_url) {
                const outputPreview = setCardRenderedPreview(rank, data.download_url);
                outputPreview?.play().catch(() => {
                    appendActivity(`Preview do MP4 do corte #${rank} pronto; reprodução automática bloqueada pelo navegador.`, 'warning');
                });
            }
            renderReceipt(data, rank);
            updateGeneratedActions(data, rank);
            document.getElementById(`card-${rank}`).dataset.dirtyAfterRender = 'false';
            updateEditorSummary(rank);

            const uploadFailed = config.gdrive && data.upload && data.upload.success === false;
            const linkWarning = config.gdrive && data.upload?.success === true
                && data.upload.permission_configured === false;
            state.textContent = uploadFailed || linkWarning ? "Concluído parcialmente" : "Pronto localmente";
            if (uploadFailed) {
                renderDriveProgress({ state: "failed" }, rank);
                await finishOperation(
                    context,
                    'warning',
                    `Corte #${rank} gerado; upload pendente`,
                    `O MP4 foi criado, mas o Google Drive falhou: ${data.upload.error || 'erro não informado'}`
                );
                return;
            }

            if (linkWarning) {
                renderDriveProgress({
                    state: "link_warning",
                    determinate: true,
                    progress_percent: data.upload?.progress_percent ?? 100,
                    uploaded_bytes: data.upload?.uploaded_bytes,
                    total_bytes: data.upload?.total_bytes
                }, rank);
                await finishOperation(
                    context,
                    "warning",
                    "Corte #" + rank + " enviado; link pendente",
                    "O arquivo chegou ao Drive, mas a permissão de compartilhamento não pôde ser configurada."
                );
                return;
            }

            if (config.gdrive) {
                renderDriveProgress({
                    state: "succeeded",
                    determinate: true,
                    progress_percent: data.upload?.progress_percent ?? 100,
                    uploaded_bytes: data.upload?.uploaded_bytes,
                    total_bytes: data.upload?.total_bytes
                }, rank);
            }

            await finishOperation(
                context,
                'success',
                config.gdrive ? `Corte #${rank} enviado` : `Corte #${rank} gerado`,
                config.gdrive
                    ? 'A configuração confirmada foi renderizada e enviada ao Google Drive.'
                    : 'A configuração confirmada foi renderizada; o recibo do servidor está no card.'
            );
        }

        async function uploadExistingToDrive(filePath, rank, button) {
            const folderId = document.getElementById('gdriveFolderId').value.trim();
            const result = await trackedPost('/api/gdrive-upload', {
                file_path: filePath,
                folder_id: folderId
            }, {
                title: `Enviando corte #${rank} ao Drive`,
                message: 'Autenticando e enviando o MP4 ao Google Drive.',
                button,
                busyLabel: '⏳ Enviando ao Drive...',
                rank,
                driveRequested: true
            });
            if (result.error) return;
            const { response, data, context } = result;
            if (!response.ok || !(data.status === 'success' || data.success)) {
                renderDriveProgress({ state: "failed" }, rank);
                await finishOperation(
                    context,
                    'error',
                    `Upload do corte #${rank} falhou`,
                    data.error || `Falha HTTP ${response.status}`
                );
                return;
            }

            const completedProgress = data.upload_progress || {};
            const linkWarning = data.permission_configured === false;
            renderDriveProgress({
                state: linkWarning ? "link_warning" : "succeeded",
                determinate: true,
                progress_percent: completedProgress.progress_percent ?? 100,
                uploaded_bytes: completedProgress.uploaded_bytes,
                total_bytes: completedProgress.total_bytes
            }, rank);
            const link = data.web_view_link || data.link;
            const group = document.getElementById(`btnGroup-${rank}`);
            if (group && link && !group.querySelector('.drive-link-badge')) {
                const driveLink = document.createElement('a');
                driveLink.href = link;
                driveLink.target = '_blank';
                driveLink.rel = 'noopener noreferrer';
                driveLink.className = 'drive-link-badge';
                driveLink.textContent = '🔗 Abrir no Google Drive';
                group.appendChild(driveLink);
            }
            await finishOperation(
                context,
                linkWarning ? "warning" : "success",
                linkWarning ? "Corte #" + rank + " enviado; link pendente" : "Corte #" + rank + " enviado",
                linkWarning
                    ? "O arquivo chegou ao Drive, mas a permissão de compartilhamento não pôde ser configurada."
                    : "Upload concluído e link do Google Drive disponível."
            );
        }
    </script>

</body>
</html>
"""


TECHNICAL_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="data:,">
    <title>Pipeline técnico de cortes · T2/T3</title>
    <style>
        :root {
            color-scheme: dark;
            --bg: #07111f;
            --panel: rgba(17, 30, 49, 0.92);
            --line: #29415f;
            --text: #edf6ff;
            --muted: #9db0c7;
            --accent: #55d6be;
            --running: #f5c451;
            --failed: #ff718b;
            --measured: #65b9ff;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            background:
                radial-gradient(circle at 12% 8%, #17345b 0, transparent 32rem),
                linear-gradient(145deg, #07111f, #0b1727 60%, #101a2d);
            color: var(--text);
            font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        main { width: min(1180px, calc(100% - 2rem)); margin: 0 auto; padding: 2rem 0 4rem; }
        a { color: var(--accent); }
        header { display: flex; justify-content: space-between; gap: 1rem; align-items: start; margin-bottom: 1.5rem; }
        h1 { margin: 0 0 .35rem; font-size: clamp(1.8rem, 4vw, 3rem); letter-spacing: -.04em; }
        h2 { margin: 0 0 1rem; font-size: 1.15rem; }
        p { margin: .2rem 0; color: var(--muted); }
        .eyebrow { color: var(--accent); font-weight: 700; letter-spacing: .12em; text-transform: uppercase; font-size: .75rem; }
        .panel {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 1.25rem;
            box-shadow: 0 22px 70px rgba(0, 0, 0, .28);
        }
        .layout { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(320px, .75fr); gap: 1rem; align-items: start; }
        .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .9rem; }
        .span-2 { grid-column: 1 / -1; }
        label { display: grid; gap: .35rem; color: #cfe0f2; font-weight: 650; font-size: .86rem; }
        .hint { color: var(--muted); font-size: .74rem; font-weight: 400; }
        input, select, textarea {
            width: 100%; border: 1px solid var(--line); border-radius: 10px; padding: .72rem .78rem;
            background: #091524; color: var(--text); font: inherit;
        }
        input:focus, select:focus, textarea:focus { outline: 2px solid rgba(85, 214, 190, .35); border-color: var(--accent); }
        input:disabled { opacity: .45; cursor: not-allowed; }
        .check-row { display: flex; align-items: center; gap: .6rem; min-height: 44px; }
        .check-row input { width: auto; }
        button {
            border: 0; border-radius: 11px; padding: .82rem 1.1rem; cursor: pointer;
            color: #041411; background: var(--accent); font: inherit; font-weight: 750;
        }
        button:disabled { opacity: .55; cursor: wait; }
        .notice { border-left: 3px solid var(--accent); padding: .7rem .9rem; background: rgba(85, 214, 190, .08); color: #cfe9e4; }
        .timeline { display: grid; gap: .55rem; margin: 0; padding: 0; list-style: none; }
        .stage { display: grid; grid-template-columns: 2rem 1fr auto; gap: .7rem; align-items: center; padding: .65rem; border: 1px solid var(--line); border-radius: 11px; }
        .stage-index { width: 2rem; height: 2rem; display: grid; place-items: center; border-radius: 50%; background: #16283e; font-weight: 750; }
        .stage-name { font-weight: 700; }
        .stage-state { color: var(--muted); font-size: .75rem; }
        .stage[data-state="running"] { border-color: var(--running); }
        .stage[data-state="running"] .stage-state { color: var(--running); }
        .stage[data-state="measured"] { border-color: var(--measured); }
        .stage[data-state="measured"] .stage-state { color: var(--measured); }
        .stage[data-state="failed"] { border-color: var(--failed); }
        .stage[data-state="failed"] .stage-state { color: var(--failed); }
        .log { margin-top: 1rem; max-height: 250px; overflow: auto; border: 1px solid var(--line); border-radius: 11px; background: #050d18; }
        .log-line { display: grid; grid-template-columns: 5.2rem 6rem 1fr; gap: .5rem; padding: .45rem .65rem; border-bottom: 1px solid rgba(41, 65, 95, .5); font: .76rem/1.35 ui-monospace, monospace; }
        .log-line:last-child { border-bottom: 0; }
        .log-line span:first-child, .log-line span:nth-child(2) { color: var(--muted); }
        .operation { margin-bottom: 1rem; padding: .8rem; border: 1px solid var(--line); border-radius: 11px; }
        .operation strong { display: block; }
        .request-id { color: var(--muted); font: .75rem ui-monospace, monospace; overflow-wrap: anywhere; }
        .receipt { margin-top: 1rem; }
        .receipt[hidden] { display: none; }
        .receipt-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .65rem; }
        .metric { padding: .7rem; border: 1px solid var(--line); border-radius: 10px; background: rgba(5, 13, 24, .55); }
        .metric small { display: block; color: var(--muted); }
        .download { display: inline-block; margin-top: .85rem; padding: .7rem .9rem; border-radius: 10px; background: var(--accent); color: #041411; font-weight: 750; text-decoration: none; }
        .error { color: #ff9aad; white-space: pre-wrap; }
        @media (max-width: 880px) { .layout { grid-template-columns: 1fr; } }
        @media (max-width: 620px) { header { display: block; } .form-grid, .receipt-grid { grid-template-columns: 1fr; } .span-2 { grid-column: auto; } }
    </style>
</head>
<body>
<main>
    <header>
        <div>
            <div class="eyebrow">Pipeline local · 9 estágios auditados</div>
            <h1>Cortes técnicos T2/T3</h1>
            <p>Whisper, detecção de cenas, legendas ASS e render vertical com libass.</p>
        </div>
        <a href="/">Ir para o corte rápido</a>
    </header>

    <div class="layout">
        <section class="panel">
            <h2>Configuração aplicada ao pipeline</h2>
            <p class="notice">Somente arquivos locais. T2 não exige camada editorial; T3 exige overlay analítico e/ou narração física.</p>
            <form id="technicalForm" class="form-grid">
                <label>
                    Fase
                    <select id="phase" name="phase" required>
                        <option value="t2">T2 · transcrição, cenas, legendas e render</option>
                        <option value="t3" selected>T3 · transformação editorial obrigatória</option>
                    </select>
                </label>
                <label>
                    Arquivo de vídeo local
                    <input id="inputPath" name="input_path" type="text" placeholder="/caminho/absoluto/video.mp4" required>
                </label>
                <label>
                    Modelo Whisper
                    <select id="whisperModel" name="whisper_model">
                        <option value="tiny">tiny</option>
                        <option value="base">base</option>
                        <option value="small" selected>small</option>
                        <option value="medium">medium</option>
                        <option value="large-v3">large-v3</option>
                        <option value="turbo">turbo</option>
                    </select>
                </label>
                <label>
                    Dispositivo
                    <select id="device" name="device"><option value="cpu" selected>CPU</option><option value="cuda">CUDA</option></select>
                </label>
                <label>
                    Idioma (opcional)
                    <input id="language" name="language" type="text" maxlength="5" placeholder="pt">
                </label>
                <label>
                    Limiar de cena
                    <input id="sceneThreshold" name="scene_threshold" type="number" min="0.1" max="100" step="0.1" value="27">
                </label>
                <label>
                    Cena mínima (s)
                    <input id="minSceneLen" name="min_scene_len" type="number" min="0.1" max="60" step="0.1" value="0.6">
                </label>
                <label>
                    Enquadramento vertical
                    <select id="verticalMode" name="vertical_mode">
                        <option value="blur_background" selected>Fundo desfocado</option>
                        <option value="split_blur">Fundo desfocado (split)</option>
                        <option value="crop_center">Corte central</option>
                    </select>
                </label>
                <label>
                    Intensidade do desfoque
                    <input id="blurSigma" name="blur_sigma" type="number" min="0" max="50" step="0.5" value="12">
                    <span class="hint">Desabilitado no corte central.</span>
                </label>
                <label>
                    Fonte da legenda
                    <input id="subtitleFontName" name="subtitle_font_name" type="text" maxlength="64" value="Roboto">
                </label>
                <label>
                    Tamanho da legenda
                    <input id="subtitleFontSize" name="subtitle_font_size" type="number" min="16" max="160" step="1" value="80">
                </label>
                <label>
                    Margem vertical da legenda
                    <input id="subtitleMarginV" name="subtitle_margin_v" type="number" min="0" max="1600" step="1" value="400">
                </label>
                <label class="span-2">
                    <span class="check-row"><input id="analyticalOverlay" name="analytical_overlay" type="checkbox" checked> Aplicar overlay analítico</span>
                </label>
                <label class="span-2">
                    Texto do overlay
                    <input id="overlayText" name="overlay_text" type="text" maxlength="120" value="ANÁLISE · ponto-chave do corte">
                </label>
                <label class="span-2">
                    Narração local (opcional)
                    <input id="narrationPath" name="narration_path" type="text" placeholder="/caminho/narracao.wav">
                    <span class="hint">Quando informada, precisa ser um arquivo de áudio local; o pipeline mede duração e mixagem.</span>
                </label>
                <label class="span-2">
                    Variante do template
                    <input id="templateVariant" name="template_variant" type="text" maxlength="64" required>
                    <span class="hint">T3 exige variante explícita e não repetida; T2 aceita variant_default.</span>
                </label>
                <button id="runButton" class="span-2" type="submit">Executar pipeline técnico</button>
            </form>
        </section>

        <aside class="panel">
            <h2>Status e logs após a análise</h2>
            <div class="operation" aria-live="polite">
                <strong id="operationState">Aguardando configuração</strong>
                <span id="requestReference" class="request-id">Nenhuma operação iniciada</span>
            </div>
            <ol class="timeline" id="stageTimeline">
                <li class="stage" data-stage="ingest" data-state="pending"><span class="stage-index">1</span><span class="stage-name">Ingest</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="transcribe" data-state="pending"><span class="stage-index">2</span><span class="stage-name">Whisper</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="scenes" data-state="pending"><span class="stage-index">3</span><span class="stage-name">Cenas</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="select" data-state="pending"><span class="stage-index">4</span><span class="stage-name">Seleção</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="cut" data-state="pending"><span class="stage-index">5</span><span class="stage-name">Corte</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="subtitles" data-state="pending"><span class="stage-index">6</span><span class="stage-name">Legendas ASS</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="audio" data-state="pending"><span class="stage-index">7</span><span class="stage-name">Áudio</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="render" data-state="pending"><span class="stage-index">8</span><span class="stage-name">Render 9:16</span><span class="stage-state">pendente</span></li>
                <li class="stage" data-stage="report" data-state="pending"><span class="stage-index">9</span><span class="stage-name">Snapshot do relatório</span><span class="stage-state">pendente</span></li>
            </ol>
            <div id="activityLog" class="log" role="log" aria-live="polite"><div class="log-line"><span>--:--:--</span><span>painel</span><span>Os eventos auditados aparecerão aqui.</span></div></div>
            <div id="technicalReceipt" class="receipt" hidden></div>
        </aside>
    </div>
</main>
<script>
(() => {
    const form = document.getElementById('technicalForm');
    const phase = document.getElementById('phase');
    const verticalMode = document.getElementById('verticalMode');
    const blurSigma = document.getElementById('blurSigma');
    const overlay = document.getElementById('analyticalOverlay');
    const overlayText = document.getElementById('overlayText');
    const templateVariant = document.getElementById('templateVariant');
    const runButton = document.getElementById('runButton');
    const operationState = document.getElementById('operationState');
    const requestReference = document.getElementById('requestReference');
    const activityLog = document.getElementById('activityLog');
    const receiptNode = document.getElementById('technicalReceipt');
    let pollTimer = null;

    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
    const newRequestId = () => `cortes-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

    function syncConditionalFields() {
        const crop = verticalMode.value === 'crop_center';
        blurSigma.disabled = crop;
        overlayText.disabled = !overlay.checked;
        if (phase.value === 't2' && (!templateVariant.value || templateVariant.dataset.generated === 'true')) {
            templateVariant.value = 'variant_default';
            templateVariant.dataset.generated = 'false';
        } else if (phase.value === 't3' && templateVariant.value === 'variant_default') {
            templateVariant.value = `variant_web_${Date.now().toString(36)}`;
            templateVariant.dataset.generated = 'true';
        }
    }

    function resetStatus() {
        document.querySelectorAll('.stage').forEach(node => {
            node.dataset.state = 'pending';
            node.querySelector('.stage-state').textContent = 'pendente';
        });
        activityLog.innerHTML = '<div class="log-line"><span>--:--:--</span><span>painel</span><span>Operação registrada; aguardando eventos.</span></div>';
        receiptNode.hidden = true;
        receiptNode.innerHTML = '';
    }

    function updateStatus(data) {
        const labels = {started: 'em execução', succeeded: 'medido', failed: 'falhou', skipped: 'não executado', planned: 'planejado'};
        const states = {started: 'running', succeeded: 'measured', failed: 'failed', skipped: 'skipped', planned: 'pending'};
        const pipelineEvents = (data.events || []).filter(event => String(event.action || '').startsWith('pipeline.'));
        for (const event of pipelineEvents) {
            const stageName = String(event.action).split('.')[1] || event.stage;
            const node = document.querySelector(`.stage[data-stage="${stageName}"]`);
            if (!node) continue;
            node.dataset.state = states[event.status] || node.dataset.state;
            node.querySelector('.stage-state').textContent = labels[event.status] || event.status;
        }
        const visibleEvents = (data.events || []).slice(-80);
        if (visibleEvents.length) {
            activityLog.innerHTML = visibleEvents.map(event => {
                const stamp = event.ts ? new Date(event.ts).toLocaleTimeString('pt-BR') : '--:--:--';
                const detail = `${event.action || event.component || 'evento'} · ${event.status || 'registrado'}${event.error ? ` · ${event.error}` : ''}`;
                return `<div class="log-line"><span>${escapeHtml(stamp)}</span><span>${escapeHtml(event.stage || 'env')}</span><span>${escapeHtml(detail)}</span></div>`;
            }).join('');
            activityLog.scrollTop = activityLog.scrollHeight;
        }
        if (data.state === 'failed') operationState.textContent = 'Execução encerrada com falha registrada';
        else if (data.completed) operationState.textContent = 'Execução encerrada; consulte a medição';
        else operationState.textContent = 'Pipeline em execução';
    }

    async function pollStatus(requestId) {
        try {
            const response = await fetch(`/api/status/${encodeURIComponent(requestId)}`, {cache: 'no-store'});
            if (response.status === 404) return;
            const data = await response.json();
            if (response.ok) updateStatus(data);
        } catch (_) {
            operationState.textContent = 'Aguardando atualização do status';
        }
    }

    function showReceipt(receipt, downloadUrl) {
        const verification = receipt.verification || {};
        const report = receipt.report_snapshot || {};
        receiptNode.innerHTML = `
            <h2>Medição pós-run</h2>
            <div class="receipt-grid">
                <div class="metric"><small>Run técnico</small>${escapeHtml(receipt.run_id)}</div>
                <div class="metric"><small>Arquivo exportado</small>${escapeHtml(receipt.file && receipt.file.name)}</div>
                <div class="metric"><small>Checks medidos</small>${escapeHtml(verification.passed_checks)} / ${escapeHtml(verification.total_checks)}</div>
                <div class="metric"><small>Checks com falha</small>${escapeHtml(verification.failed_checks)}</div>
                <div class="metric span-2"><small>Resultado da medição (não é declaração de fase)</small>${verification.overall_passed ? 'Todos os checks passaram' : 'Há checks que não passaram'}</div>
                <div class="metric span-2"><small>${escapeHtml(report.label || 'Snapshot não verificado')}</small>${escapeHtml(report.path || '')}</div>
            </div>
            <a class="download" href="${escapeHtml(downloadUrl)}" download>Baixar MP4 medido</a>`;
        receiptNode.hidden = false;
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const requestId = newRequestId();
        resetStatus();
        requestReference.textContent = requestId;
        operationState.textContent = 'Registrando pipeline técnico';
        runButton.disabled = true;
        const payload = {
            phase: phase.value,
            input_path: document.getElementById('inputPath').value.trim(),
            whisper_model: document.getElementById('whisperModel').value,
            device: document.getElementById('device').value,
            language: document.getElementById('language').value.trim() || null,
            scene_threshold: Number(document.getElementById('sceneThreshold').value),
            min_scene_len: Number(document.getElementById('minSceneLen').value),
            vertical_mode: verticalMode.value,
            blur_sigma: verticalMode.value === 'crop_center' ? null : Number(blurSigma.value),
            subtitle_font_name: document.getElementById('subtitleFontName').value.trim(),
            subtitle_font_size: Number(document.getElementById('subtitleFontSize').value),
            subtitle_margin_v: Number(document.getElementById('subtitleMarginV').value),
            analytical_overlay: overlay.checked,
            overlay_text: overlay.checked ? overlayText.value.trim() : null,
            narration_path: document.getElementById('narrationPath').value.trim() || null,
            template_variant: templateVariant.value.trim()
        };
        pollTimer = window.setInterval(() => pollStatus(requestId), 800);
        await pollStatus(requestId);
        try {
            const response = await fetch('/api/cortes/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Request-ID': requestId},
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            await pollStatus(requestId);
            if (!response.ok || data.success === false) throw new Error(data.error || `HTTP ${response.status}`);
            showReceipt(data.render_receipt, data.download_url);
        } catch (error) {
            operationState.textContent = 'Execução não produziu recibo';
            receiptNode.innerHTML = `<p class="error">${escapeHtml(error.message || error)}</p>`;
            receiptNode.hidden = false;
        } finally {
            window.clearInterval(pollTimer);
            pollTimer = null;
            runButton.disabled = false;
            await pollStatus(requestId);
        }
    });

    phase.addEventListener('change', syncConditionalFields);
    verticalMode.addEventListener('change', syncConditionalFields);
    overlay.addEventListener('change', syncConditionalFields);
    templateVariant.value = `variant_web_${Date.now().toString(36)}`;
    templateVariant.dataset.generated = 'true';
    syncConditionalFields();
})();
</script>
</body>
</html>
"""


TECHNICAL_VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
}
TECHNICAL_AUDIO_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}
TECHNICAL_WHISPER_MODELS = {
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v1",
    "large-v2",
    "large-v3",
    "distil-small.en",
    "distil-medium.en",
    "distil-large-v2",
    "distil-large-v3",
    "turbo",
}
TECHNICAL_PAYLOAD_FIELDS = {
    "phase",
    "input_path",
    "whisper_model",
    "device",
    "language",
    "scene_threshold",
    "min_scene_len",
    "vertical_mode",
    "blur_sigma",
    "subtitle_font_name",
    "subtitle_font_size",
    "subtitle_margin_v",
    "analytical_overlay",
    "overlay_text",
    "narration_path",
    "template_variant",
}
TECHNICAL_TEMPLATE_VARIANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


def _technical_number(
    payload: dict,
    field: str,
    default: int | float,
    minimum: int | float,
    maximum: int | float,
    *,
    integer: bool = False,
) -> int | float:
    raw_value = payload.get(field, default)
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        kind = "an integer" if integer else "a number"
        raise ValidationError(f"{field} must be {kind}", field=field)
    value = float(raw_value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValidationError(
            f"{field} must be between {minimum} and {maximum}", field=field
        )
    if integer:
        if not value.is_integer():
            raise ValidationError(f"{field} must be an integer", field=field)
        return int(value)
    return value


def _technical_local_file(
    raw_value: object,
    *,
    field: str,
    extensions: set[str],
    required: bool,
) -> Path | None:
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        if required:
            raise ValidationError(f"{field} is required", field=field)
        return None
    if not isinstance(raw_value, str):
        raise ValidationError(f"{field} must be a local file path", field=field)
    value = raw_value.strip()
    if len(value) > 4096 or "\x00" in value or "://" in value:
        raise ValidationError(f"{field} must be a local file path", field=field)
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc:
        raise ValidationError(f"{field} must be a local file path", field=field)
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() not in extensions:
        supported = ", ".join(sorted(extensions))
        raise ValidationError(
            f"{field} must use a supported media extension: {supported}", field=field
        )
    if not path.exists() or not path.is_file():
        raise ValidationError(f"Local file does not exist: {path}", field=field)
    return path


def validate_technical_payload(payload: dict) -> dict:
    """Validate and normalize the separate local T2/T3 dashboard contract."""
    unknown_fields = sorted(set(payload) - TECHNICAL_PAYLOAD_FIELDS)
    if unknown_fields:
        raise ValidationError(
            f"Unsupported field(s): {', '.join(unknown_fields)}",
            field=unknown_fields[0],
        )

    phase = payload.get("phase")
    if not isinstance(phase, str) or phase not in {"t2", "t3"}:
        raise ValidationError("phase must be t2 or t3", field="phase")

    input_path = _technical_local_file(
        payload.get("input_path"),
        field="input_path",
        extensions=TECHNICAL_VIDEO_EXTENSIONS,
        required=True,
    )

    whisper_model = payload.get("whisper_model", "small")
    if not isinstance(whisper_model, str) or whisper_model not in TECHNICAL_WHISPER_MODELS:
        raise ValidationError("whisper_model is not supported", field="whisper_model")

    device = payload.get("device", "cpu")
    if not isinstance(device, str) or device not in {"cpu", "cuda"}:
        raise ValidationError("device must be cpu or cuda", field="device")

    language = payload.get("language")
    if language is None or language == "":
        language = None
    elif not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,5}", language):
        raise ValidationError(
            "language must be a 2-5 letter language code or null", field="language"
        )
    else:
        language = language.lower()

    scene_threshold = _technical_number(
        payload, "scene_threshold", 27.0, 0.1, 100.0
    )
    min_scene_len = _technical_number(payload, "min_scene_len", 0.6, 0.1, 60.0)

    vertical_mode = payload.get("vertical_mode", "blur_background")
    if (
        not isinstance(vertical_mode, str)
        or vertical_mode not in {"blur_background", "split_blur", "crop_center"}
    ):
        raise ValidationError(
            "vertical_mode must be blur_background, split_blur, or crop_center",
            field="vertical_mode",
        )
    raw_blur_sigma = payload.get("blur_sigma", 12.0)
    if vertical_mode == "crop_center":
        if "blur_sigma" in payload and raw_blur_sigma is not None:
            raise ValidationError(
                "blur_sigma must be null when vertical_mode is crop_center",
                field="blur_sigma",
            )
        blur_sigma = 12.0
    else:
        if raw_blur_sigma is None:
            raise ValidationError(
                "blur_sigma is required for a blurred vertical mode",
                field="blur_sigma",
            )
        blur_sigma = _technical_number(payload, "blur_sigma", 12.0, 0.0, 50.0)

    subtitle_font_name = payload.get("subtitle_font_name", "Roboto")
    if (
        not isinstance(subtitle_font_name, str)
        or not re.fullmatch(r"[\w .-]{1,64}", subtitle_font_name.strip())
    ):
        raise ValidationError(
            "subtitle_font_name contains unsupported characters",
            field="subtitle_font_name",
        )
    subtitle_font_name = subtitle_font_name.strip()
    subtitle_font_size = _technical_number(
        payload, "subtitle_font_size", 80, 16, 160, integer=True
    )
    subtitle_margin_v = _technical_number(
        payload, "subtitle_margin_v", 400, 0, 1600, integer=True
    )

    analytical_overlay = payload.get("analytical_overlay", False)
    if not isinstance(analytical_overlay, bool):
        raise ValidationError(
            "analytical_overlay must be a boolean", field="analytical_overlay"
        )
    raw_overlay_text = payload.get("overlay_text")
    if analytical_overlay:
        if not isinstance(raw_overlay_text, str):
            raise ValidationError(
                "overlay_text is required when analytical_overlay is enabled",
                field="overlay_text",
            )
        overlay_text = raw_overlay_text.strip()
        if not overlay_text or len(overlay_text) > 120:
            raise ValidationError(
                "overlay_text must contain 1-120 characters", field="overlay_text"
            )
        if re.search(r"[\x00-\x1f\x7f\\'\[\];%]", overlay_text):
            raise ValidationError(
                "overlay_text contains characters unsupported by the renderer",
                field="overlay_text",
            )
    else:
        if raw_overlay_text is not None and raw_overlay_text != "":
            raise ValidationError(
                "overlay_text must be null when analytical_overlay is disabled",
                field="overlay_text",
            )
        overlay_text = None

    narration_path = _technical_local_file(
        payload.get("narration_path"),
        field="narration_path",
        extensions=TECHNICAL_AUDIO_EXTENSIONS,
        required=False,
    )

    template_variant = payload.get(
        "template_variant", "variant_default" if phase == "t2" else None
    )
    if not isinstance(template_variant, str):
        raise ValidationError("template_variant is required", field="template_variant")
    template_variant = template_variant.strip().lower()
    if not TECHNICAL_TEMPLATE_VARIANT_PATTERN.fullmatch(template_variant):
        raise ValidationError(
            "template_variant must contain 3-64 lowercase letters, numbers, '_' or '-'",
            field="template_variant",
        )

    require_editorial_transformation = phase == "t3"
    if require_editorial_transformation:
        if template_variant == "variant_default":
            raise ValidationError(
                "T3 requires a non-default template_variant", field="template_variant"
            )
        if not analytical_overlay and narration_path is None:
            raise ValidationError(
                "T3 requires analytical_overlay and/or narration_path", field="phase"
            )

    return {
        "phase": phase,
        "input_path": input_path,
        "whisper_model": whisper_model,
        "device": device,
        "language": language,
        "scene_threshold": scene_threshold,
        "min_scene_len": min_scene_len,
        "vertical_mode": vertical_mode,
        "blur_sigma": blur_sigma,
        "subtitle_font_name": subtitle_font_name,
        "subtitle_font_size": subtitle_font_size,
        "subtitle_margin_v": subtitle_margin_v,
        "analytical_overlay": analytical_overlay,
        "overlay_text": overlay_text,
        "narration_path": narration_path,
        "template_variant": template_variant,
        "require_editorial_transformation": require_editorial_transformation,
    }


class ClipperDashboardHandler(BaseHTTPRequestHandler):
    """Multi-threaded HTTP Request Handler for YouTube Clipper Dashboard & REST API."""

    GET_ROUTES = {"/", "/index.html"}
    TECHNICAL_GET_ROUTES = {"/technical", "/cortes"}
    POST_ROUTES = {
        "/api/analyze",
        "/api/editor-chat",
        "/api/editor-assets",
        "/api/generate-clip",
        "/api/gdrive-upload",
        "/api/cortes/run",
    }
    STATUS_ROUTE_PREFIX = "/api/status/"
    REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
    ASSET_ID_PATTERN = re.compile(r"^asset_[a-f0-9]{32}\.(?:aac|flac|jpe?g|m4a|mp3|ogg|png|wav|webp)$")
    MAX_REQUEST_BODY_BYTES = 36 * 1024 * 1024
    MAX_EDITOR_ASSET_FILES = 200
    MAX_EDITOR_ASSET_STORAGE_BYTES = 512 * 1024 * 1024
    EDITOR_ASSET_POLICIES = {
        "music": {
            "extensions": {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"},
            "mime_types": {
                "audio/aac",
                "audio/flac",
                "audio/m4a",
                "audio/mp4",
                "audio/mpeg",
                "audio/ogg",
                "audio/wav",
                "audio/x-wav",
            },
            "max_bytes": 25 * 1024 * 1024,
        },
        "intro_image": {
            "extensions": {".jpeg", ".jpg", ".png", ".webp"},
            "mime_types": {"image/jpeg", "image/png", "image/webp"},
            "max_bytes": 8 * 1024 * 1024,
        },
    }
    REQUEST_REGISTRY_LOCK = threading.Lock()
    ASSET_STORAGE_LOCK = threading.Lock()
    DOMAIN_STORE_LOCK = threading.Lock()
    API_V1_PREFIX = "/api/v1/"
    PROJECT_ID_ROUTE = re.compile(
        r"\A/api/v1/projects/(prj_[0-9a-f]{32})\Z"
    )
    PROJECT_CLIPS_ROUTE = re.compile(
        r"\A/api/v1/projects/(prj_[0-9a-f]{32})/clips\Z"
    )
    PROJECT_ANALYSIS_ROUTE = re.compile(
        r"\A/api/v1/projects/(prj_[0-9a-f]{32})/analysis-jobs\Z"
    )
    CLIP_ID_ROUTE = re.compile(
        r"\A/api/v1/clips/(clp_[0-9a-f]{32})\Z"
    )
    JOB_ID_ROUTE = re.compile(
        r"\A/api/v1/jobs/(job_[0-9a-f]{32})\Z"
    )
    CLIP_PREVIEW_ROUTE = re.compile(
        r"\A/api/v1/clips/(clp_[0-9a-f]{32})/preview-jobs\Z"
    )
    DOMAIN_ASSET_ROUTE = re.compile(
        r"\A/api/v1/assets/(ast_[0-9a-f]{32})\Z"
    )

    def _domain_store(self) -> ProjectStore:
        store = vars(self.server).get("project_store")
        if isinstance(store, ProjectStore):
            return store
        with self.DOMAIN_STORE_LOCK:
            store = vars(self.server).get("project_store")
            if isinstance(store, ProjectStore):
                return store
            workspace = Path(
                vars(self.server).get(
                    "panel_workspace", Path.cwd() / "panel_workspace"
                )
            ).resolve()
            workspace.mkdir(parents=True, exist_ok=True)
            store = ProjectStore(
                database_path=workspace / "projects.sqlite3",
                workspace_dir=workspace,
            )
            self.server.project_store = store
            return store

    def _send_domain_error(self, error: Exception) -> None:
        if isinstance(error, DomainNotFoundError):
            status_code = 404
        elif isinstance(error, DomainConflictError):
            status_code = 409
        else:
            status_code = 400
        self.send_json(
            status_code,
            {"success": False, "error": str(error)},
            no_store=True,
        )


    @classmethod
    def _normalize_request_id(cls, raw_request_id: str | None) -> str:
        candidate = str(raw_request_id or "").strip()
        if cls.REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
        return uuid.uuid4().hex

    def _register_request_run(self, request_id: str, run_id: str) -> None:
        """Associate an audited run with the browser operation that created it."""
        with self.REQUEST_REGISTRY_LOCK:
            registry = vars(self.server).get("request_runs")
            if registry is None:
                registry = {}
                self.server.request_runs = registry
            run_ids = registry.setdefault(request_id, [])
            if run_id not in run_ids:
                run_ids.append(run_id)
            while len(registry) > 256:
                registry.pop(next(iter(registry)))

    def _registered_request_runs(self, request_id: str) -> list[str]:
        with self.REQUEST_REGISTRY_LOCK:
            registry = vars(self.server).get("request_runs", {})
            return list(registry.get(request_id, []))

    def _new_child_run(self, label: str) -> str:
        safe_label = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
        run_id = f"run_dashboard_{safe_label}_{uuid.uuid4().hex}"
        self._register_request_run(self._audit_request_id, run_id)
        return run_id

    def _request_status_payload(self, request_id: str) -> dict | None:
        run_ids = self._registered_request_runs(request_id)
        if not run_ids:
            return None

        runs_root = Path.cwd() / "runs"
        public_events = []
        drive_events = []
        all_sealed = True
        failed = False

        for run_id in run_ids:
            run_dir = runs_root / run_id
            events_file = run_dir / "events.jsonl"
            seal_file = run_dir / "seal.json"
            all_sealed = all_sealed and seal_file.exists()

            if seal_file.exists():
                try:
                    seal_data = json.loads(seal_file.read_text(encoding="utf-8"))
                    failed = failed or seal_data.get("status") == "failed"
                except (OSError, ValueError, TypeError):
                    failed = True

            if not events_file.exists():
                continue

            try:
                lines = events_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue

            for line in lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if event.get("request_id") != request_id:
                    continue

                status = str(event.get("status") or "")
                failed = failed or status == "failed"
                error_data = event.get("error")
                error_message = None
                if isinstance(error_data, dict):
                    category = str(error_data.get("category") or "application")
                    exit_code = error_data.get("exit_code")
                    error_type = str(error_data.get("type") or "error")
                    if exit_code is not None:
                        error_message = f"{category} ({error_type}), código {exit_code}"
                    else:
                        error_message = f"{category} ({error_type})"
                elif error_data:
                    error_message = "application (error)"

                public_events.append(
                    {
                        "event_id": event.get("event_id"),
                        "run_id": event.get("run_id"),
                        "seq": event.get("seq"),
                        "ts": event.get("ts"),
                        "stage": event.get("stage"),
                        "status": status,
                        "component": event.get("component"),
                        "action": event.get("action"),
                        "duration_ms": event.get("duration_ms"),
                        "error": error_message,
                    }
                )

                if event.get("component") == "youtube_clipper.gdrive":
                    raw_decision = event.get("decision")
                    safe_decision = {}
                    if isinstance(raw_decision, dict):
                        for key in (
                            "progress_percent",
                            "uploaded_bytes",
                            "total_bytes",
                            "chunk_number",
                            "indeterminate",
                        ):
                            value = raw_decision.get(key)
                            if key == "indeterminate":
                                if isinstance(value, bool):
                                    safe_decision[key] = value
                            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                                numeric = float(value)
                                if math.isfinite(numeric):
                                    safe_decision[key] = numeric
                    attempt = event.get("attempt")
                    drive_events.append(
                        {
                            "run_id": event.get("run_id"),
                            "seq": event.get("seq"),
                            "ts": event.get("ts"),
                            "status": status,
                            "action": str(event.get("action") or ""),
                            "attempt": (
                                int(attempt)
                                if isinstance(attempt, (int, float)) and not isinstance(attempt, bool)
                                else None
                            ),
                            "progress": safe_decision,
                        }
                    )

        public_events.sort(
            key=lambda item: (
                str(item.get("ts") or ""),
                str(item.get("run_id") or ""),
                int(item.get("seq") or 0),
            )
        )
        drive_events.sort(
            key=lambda item: (
                str(item.get("ts") or ""),
                str(item.get("run_id") or ""),
                int(item.get("seq") or 0),
            )
        )
        drive_upload = None
        for drive_event in drive_events:
            action = drive_event["action"]
            event_status = drive_event["status"]
            progress = drive_event["progress"]
            if drive_upload is None:
                drive_upload = {
                    "state": "pending",
                    "determinate": False,
                    "progress_percent": None,
                    "uploaded_bytes": None,
                    "total_bytes": None,
                    "chunk_number": None,
                    "attempt": None,
                    "updated_at": drive_event.get("ts"),
                }
            drive_upload["updated_at"] = drive_event.get("ts")

            if event_status == "started" and (
                action.startswith("gdrive.auth.") or action == "gdrive.build_client"
            ):
                drive_upload["state"] = "authenticating"
                drive_upload["determinate"] = False
            elif event_status == "started" and action == "gdrive.resolve_folder":
                drive_upload["state"] = "preparing"
                drive_upload["determinate"] = False
            elif event_status == "failed" and (
                action.startswith("gdrive.auth.")
                or action in {"gdrive.build_client", "gdrive.resolve_folder"}
            ):
                drive_upload["state"] = "failed"
                drive_upload["determinate"] = False
            elif action.startswith("gdrive.upload.progress."):
                indeterminate = progress.get("indeterminate") is True
                percent = progress.get("progress_percent")
                uploaded = progress.get("uploaded_bytes")
                total = progress.get("total_bytes")
                chunk = progress.get("chunk_number")
                if total is not None:
                    drive_upload["total_bytes"] = max(0, int(total))
                if indeterminate:
                    drive_upload["state"] = "uploading"
                    drive_upload["determinate"] = False
                    drive_upload["progress_percent"] = None
                    drive_upload["uploaded_bytes"] = None
                else:
                    previous_percent = drive_upload.get("progress_percent")
                    normalized_percent = max(0.0, min(100.0, float(percent or 0.0)))
                    if isinstance(previous_percent, (int, float)):
                        normalized_percent = max(float(previous_percent), normalized_percent)
                    previous_uploaded = drive_upload.get("uploaded_bytes")
                    normalized_uploaded = max(0, int(uploaded or 0))
                    if isinstance(previous_uploaded, int):
                        normalized_uploaded = max(previous_uploaded, normalized_uploaded)
                    if isinstance(drive_upload.get("total_bytes"), int):
                        normalized_uploaded = min(
                            normalized_uploaded, drive_upload["total_bytes"]
                        )
                    drive_upload["state"] = (
                        "uploaded" if normalized_percent >= 100.0 else "uploading"
                    )
                    drive_upload["determinate"] = True
                    drive_upload["progress_percent"] = round(normalized_percent, 2)
                    drive_upload["uploaded_bytes"] = normalized_uploaded
                    drive_upload["chunk_number"] = (
                        max(0, int(chunk)) if chunk is not None else None
                    )
            elif action == "gdrive.upload" and event_status == "retrying":
                drive_upload["state"] = "retrying"
                drive_upload["attempt"] = drive_event.get("attempt")
            elif action == "gdrive.upload" and event_status == "failed":
                drive_upload["state"] = "failed"
            elif action == "gdrive.upload" and event_status == "succeeded":
                drive_upload["state"] = "uploaded"
                drive_upload["determinate"] = True
                drive_upload["progress_percent"] = 100.0
                if isinstance(drive_upload.get("total_bytes"), int):
                    drive_upload["uploaded_bytes"] = drive_upload["total_bytes"]
            elif action == "gdrive.set_permission" and event_status == "started":
                drive_upload["state"] = "finalizing"
            elif action == "gdrive.set_permission" and event_status == "succeeded":
                drive_upload["state"] = "succeeded"
            elif action == "gdrive.set_permission" and event_status == "failed":
                drive_upload["state"] = "link_warning"

        state = "failed" if failed else ("completed" if all_sealed else "running")
        return {
            "success": True,
            "request_id": request_id,
            "state": state,
            "completed": all_sealed,
            "run_ids": run_ids,
            "events": public_events[-250:],
            "drive_upload": drive_upload,
        }

    def _output_dir(self) -> Path:
        configured = vars(self.server).get("output_dir", Path.cwd() / "output")
        return Path(configured).resolve()

    def _asset_dir(self) -> Path:
        output_dir = self._output_dir()
        asset_dir = (output_dir / "_editor_assets").resolve()
        asset_dir.relative_to(output_dir)
        asset_dir.mkdir(parents=True, exist_ok=True)
        return asset_dir

    @staticmethod
    def _asset_signature_matches(kind: str, extension: str, data: bytes) -> bool:
        """Apply a small allow-list signature check before FFmpeg sees an upload."""
        if kind == "intro_image":
            if extension in {".jpg", ".jpeg"}:
                return len(data) >= 3 and data.startswith(b"\xff\xd8\xff")
            if extension == ".png":
                return data.startswith(b"\x89PNG\r\n\x1a\n")
            if extension == ".webp":
                return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            return False
        if extension in {".aac", ".mp3"}:
            return data.startswith(b"ID3") or (
                len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
            )
        if extension == ".wav":
            return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
        if extension == ".flac":
            return data.startswith(b"fLaC")
        if extension == ".ogg":
            return data.startswith(b"OggS")
        if extension == ".m4a":
            return len(data) >= 12 and data[4:8] == b"ftyp"
        return False

    @audited(
        stage="ingest",
        action="editor.store_asset",
        component="youtube_clipper.dashboard",
        redact_args=["payload"],
    )
    def _store_editor_asset(self, *, payload: dict) -> dict:
        kind = payload.get("kind")
        if kind not in self.EDITOR_ASSET_POLICIES:
            raise ValidationError(
                "kind must be music or intro_image", field="kind"
            )
        if payload.get("rights_confirmed") is not True:
            raise ValidationError(
                "Confirm that you have rights to use this asset",
                field="rights_confirmed",
            )

        file_name = payload.get("file_name")
        if not isinstance(file_name, str):
            raise ValidationError("file_name is required", field="file_name")
        file_name = re.sub(r"[\x00-\x1f\x7f]+", " ", file_name).strip()
        if (
            not file_name
            or len(file_name) > 180
            or Path(file_name).name != file_name
            or "/" in file_name
            or "\\" in file_name
        ):
            raise ValidationError("Invalid asset filename", field="file_name")

        mime_type = payload.get("mime_type")
        if not isinstance(mime_type, str):
            raise ValidationError("mime_type is required", field="mime_type")
        mime_type = mime_type.split(";", 1)[0].strip().lower()
        policy = self.EDITOR_ASSET_POLICIES[kind]
        extension = Path(file_name).suffix.lower()
        if extension not in policy["extensions"]:
            raise ValidationError(
                "Unsupported file extension for this asset", field="file_name"
            )
        if mime_type not in policy["mime_types"]:
            raise ValidationError(
                "Unsupported media type for this asset", field="mime_type"
            )

        raw_data = payload.get("data_base64")
        if not isinstance(raw_data, str) or not raw_data:
            raise ValidationError("data_base64 is required", field="data_base64")
        encoded = raw_data
        if raw_data.startswith("data:"):
            header, separator, encoded = raw_data.partition(",")
            if not separator or not header.lower().endswith(";base64"):
                raise ValidationError("Invalid base64 data URL", field="data_base64")
            declared_mime = header[5:-7].strip().lower()
            if declared_mime != mime_type:
                raise ValidationError(
                    "The data URL media type does not match mime_type",
                    field="mime_type",
                )
        if len(encoded) > ((int(policy["max_bytes"]) + 2) // 3) * 4 + 4:
            raise ValidationError("Asset exceeds the size limit", field="data_base64")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValidationError("Invalid base64 asset data", field="data_base64") from None
        if not decoded:
            raise ValidationError("Asset file is empty", field="data_base64")
        if len(decoded) > int(policy["max_bytes"]):
            raise ValidationError("Asset exceeds the size limit", field="data_base64")
        if not self._asset_signature_matches(kind, extension, decoded):
            raise ValidationError(
                "File content does not match its declared media type",
                field="data_base64",
            )

        asset_dir = self._asset_dir()
        asset_id = f"asset_{uuid.uuid4().hex}{extension}"
        asset_path = asset_dir / asset_id
        digest = hashlib.sha256(decoded).hexdigest()
        metadata = {
            "asset_id": asset_id,
            "kind": kind,
            "original_file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": len(decoded),
            "sha256": digest,
            "rights_confirmed": True,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.ASSET_STORAGE_LOCK:
            stored_assets = [
                candidate
                for candidate in asset_dir.iterdir()
                if self.ASSET_ID_PATTERN.fullmatch(candidate.name)
                and candidate.is_file()
            ]
            stored_bytes = sum(candidate.stat().st_size for candidate in stored_assets)
            if len(stored_assets) >= self.MAX_EDITOR_ASSET_FILES:
                raise ValidationError(
                    "Editor asset file quota reached", field="data_base64"
                )
            if stored_bytes + len(decoded) > self.MAX_EDITOR_ASSET_STORAGE_BYTES:
                raise ValidationError(
                    "Editor asset storage quota reached", field="data_base64"
                )
            with asset_path.open("xb") as asset_file:
                asset_file.write(decoded)
            try:
                metadata_path = asset_dir / f"{asset_id}.json"
                with metadata_path.open("x", encoding="utf-8") as metadata_file:
                    json.dump(metadata, metadata_file, ensure_ascii=False, sort_keys=True)
            except Exception:
                asset_path.unlink(missing_ok=True)
                raise
        return {
            "asset_id": asset_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": len(decoded),
            "sha256": digest,
        }

    @audited(
        stage="ingest",
        action="editor.resolve_asset",
        component="youtube_clipper.dashboard",
    )
    def _resolve_editor_asset(self, asset_id: object, *, expected_kind: str) -> Path:
        field = (
            "background_music_asset_id"
            if expected_kind == "music"
            else "intro_image_asset_id"
        )
        if expected_kind not in self.EDITOR_ASSET_POLICIES:
            raise ValidationError("Unsupported editor asset kind", field=field)
        if not isinstance(asset_id, str) or not self.ASSET_ID_PATTERN.fullmatch(asset_id):
            raise ValidationError("Invalid editor asset ID", field=field)
        extension = Path(asset_id).suffix.lower()
        if extension not in self.EDITOR_ASSET_POLICIES[expected_kind]["extensions"]:
            raise ValidationError("Editor asset type mismatch", field=field)

        asset_dir = self._asset_dir()
        unresolved = asset_dir / asset_id
        if unresolved.is_symlink():
            raise ValidationError("Invalid editor asset", field=field)
        try:
            asset_path = unresolved.resolve(strict=True)
            asset_path.relative_to(asset_dir)
        except (FileNotFoundError, OSError, ValueError):
            raise ValidationError("Editor asset was not found", field=field) from None
        if not asset_path.is_file() or asset_path.name != asset_id:
            raise ValidationError("Editor asset was not found", field=field)

        metadata_path = asset_dir / f"{asset_id}.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ValidationError("Editor asset metadata is invalid", field=field) from None
        if (
            not isinstance(metadata, dict)
            or metadata.get("asset_id") != asset_id
            or metadata.get("kind") != expected_kind
            or metadata.get("rights_confirmed") is not True
            or metadata.get("size_bytes") != asset_path.stat().st_size
        ):
            raise ValidationError("Editor asset metadata is invalid", field=field)
        digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if not hmac.compare_digest(str(metadata.get("sha256", "")), digest):
            raise ValidationError("Editor asset integrity check failed", field=field)
        return asset_path

    def _is_authorized(self) -> bool:
        expected = vars(self.server).get("api_token", None)
        bound_host = str(self.server.server_address[0])
        loopback = bound_host in {"127.0.0.1", "::1", "localhost"}
        if not expected:
            return loopback
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        return supplied.startswith(prefix) and hmac.compare_digest(
            supplied[len(prefix):], str(expected)
        )

    def _post_origin_allowed(self) -> bool:
        if self.headers.get("Sec-Fetch-Site", "").strip().lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        try:
            parsed = urllib.parse.urlsplit(origin)
        except ValueError:
            return False
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        request_host = self.headers.get("Host", "").strip().lower()
        if not request_host or parsed.netloc.lower() != request_host:
            return False
        if not vars(self.server).get("api_token", None):
            return parsed.hostname.lower() in {"127.0.0.1", "::1", "localhost"}
        return True

    @audited(
        stage="env",
        action="http.validate_post_context",
        component="youtube_clipper.dashboard",
    )
    def _require_safe_post_context(self) -> bool:
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            self.send_json(
                415,
                {"success": False, "error": "Content-Type must be application/json"},
                no_store=True,
            )
            return False
        if not self._post_origin_allowed():
            self.send_json(
                403,
                {"success": False, "error": "Cross-origin POST requests are not allowed"},
                no_store=True,
            )
            return False
        return True

    @audited(
        stage="env",
        action="http.authorize",
        component="youtube_clipper.dashboard",
    )
    def _require_authorization(self) -> bool:
        authorized = self._is_authorized()
        self._audit_authorized = authorized
        if authorized:
            return True
        self.send_json(401, {"success": False, "error": "Unauthorized"})
        return False

    @audited(
        stage="env",
        action="http.resolve_output_file",
        component="youtube_clipper.dashboard",
    )
    def _resolve_output_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser().resolve()
        candidate.relative_to(self._output_dir())
        return candidate

    def log_message(self, format, *args):
        if urllib.parse.urlsplit(self.path).path.startswith(self.STATUS_ROUTE_PREFIX):
            return
        entry = {
            "component": "youtube_clipper.dashboard",
            "request_id": vars(self).get("_audit_request_id"),
            "message": format % args,
        }
        sys.stderr.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def send_response(self, code, message=None):
        self._audit_response_status = int(code)
        return super().send_response(code, message)

    def end_headers(self):
        request_id = vars(self).get("_audit_request_id")
        if request_id:
            self.send_header("X-Request-ID", request_id)
        return super().end_headers()

    def _send_status_json(self, status_code: int, data: dict) -> None:
        payload = dict(data)
        payload.setdefault("request_id", vars(self).get("_audit_request_id"))
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def send_json(self, status_code: int, data: dict, *, no_store: bool = False):
        payload = dict(data)
        request_id = vars(self).get("_audit_request_id")
        if request_id:
            payload.setdefault("request_id", request_id)
        with action_span(
            "report",
            "http.send_json",
            component="youtube_clipper.dashboard",
            input_data={
                "http_status": status_code,
                "success": bool(payload.get("success")),
                "keys": sorted(payload.keys()),
            },
        ) as span:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if no_store:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            span.decision = {
                "http_status": status_code,
                "success": bool(payload.get("success")),
            }
            if status_code >= 400 or payload.get("success") is False:
                span.mark_failed(
                    f"JSON response reported failure ({status_code})",
                    category="http",
                    retryable=status_code >= 500,
                )

    def _persist_legacy_analysis(
        self,
        *,
        clean_url: str,
        result: dict,
        requested_project_id: object = None,
    ) -> dict[str, Any]:
        store = self._domain_store()
        if requested_project_id is None:
            video_id_match = re.search(r"([A-Za-z0-9_-]{11})(?:[?&/#]|$)", clean_url)
            label = video_id_match.group(1) if video_id_match else "YouTube"
            project = store.create_project(
                name=f"Projeto {label}",
                source_uri=clean_url,
                source_kind="youtube",
            )
        else:
            project = store.get_project(str(requested_project_id))
            source = store.get_primary_source(project["project_id"])
            if source["kind"] != "youtube" or source["uri"] != clean_url:
                raise DomainConflictError(
                    "The requested project belongs to a different source"
                )
        source = store.get_primary_source(project["project_id"])
        analysis = store.create_analysis(project_id=project["project_id"])
        if result.get("success") is False:
            store.fail_analysis(analysis["analysis_id"], result)
            clips = []
        else:
            clips = store.finish_analysis(
                analysis_id=analysis["analysis_id"],
                result=result,
            )
        return {
            "project_id": project["project_id"],
            "source_id": source["source_id"],
            "analysis_id": analysis["analysis_id"],
            "clips": clips,
        }

    def _send_domain_asset(self, asset_id: str) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        raw_version = query.get("v", [None])[0]
        if raw_version is None or not str(raw_version).isdigit():
            raise DomainValidationError("A numeric asset version is required")
        asset, path = self._domain_store().resolve_asset_file(
            asset_id, version=int(raw_version)
        )
        size = path.stat().st_size
        start = 0
        end = size - 1
        status = 200
        raw_range = self.headers.get("Range")
        if raw_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range.strip())
            if not match or (not match.group(1) and not match.group(2)):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                suffix_length = int(match.group(2))
                start = max(0, size - suffix_length)
                end = size - 1
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end = min(end, size - 1)
            status = 206

        content_length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", asset["mime_type"])
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("ETag", chr(34) + asset["sha256"] + chr(34))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = content_length
            while remaining:
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _handle_api_v1_get(self, route_path: str) -> None:
        store = self._domain_store()
        try:
            match = self.DOMAIN_ASSET_ROUTE.fullmatch(route_path)
            if match:
                self._send_domain_asset(match.group(1))
                return
            if route_path == "/api/v1/projects":
                self.send_json(
                    200,
                    {"success": True, "projects": store.list_projects()},
                    no_store=True,
                )
                return
            match = self.PROJECT_ID_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {"success": True, "project": store.get_project(match.group(1))},
                    no_store=True,
                )
                return
            match = self.PROJECT_CLIPS_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {
                        "success": True,
                        "project_id": match.group(1),
                        "clips": store.list_clips(match.group(1)),
                    },
                    no_store=True,
                )
                return
            match = self.CLIP_ID_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {"success": True, "clip": store.get_clip(match.group(1))},
                    no_store=True,
                )
                return
            match = self.JOB_ID_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {"success": True, "job": store.get_job(match.group(1))},
                    no_store=True,
                )
                return
            self.send_json(
                404,
                {"success": False, "error": "API v1 route not found"},
                no_store=True,
            )
        except (DomainNotFoundError, DomainConflictError, DomainValidationError) as exc:
            self._send_domain_error(exc)
        except Exception:
            self.send_json(
                500,
                {"success": False, "error": "Persistent API operation failed"},
                no_store=True,
            )

    def _create_preview_job(self, clip_id: str) -> dict[str, Any]:
        store = self._domain_store()
        clip = store.get_clip(clip_id)
        source = store.get_source(clip["source_id"])
        job = store.create_job(
            project_id=clip["project_id"],
            clip_id=clip_id,
            kind="preview",
            state="running",
        )
        run_id = self._new_child_run("preview-" + job["job_id"])
        try:
            clip = store.update_clip(clip_id, {"status": "previewing"})
            generated = generate_clip_preview(
                input_source=source["uri"],
                start_ms=clip["start_ms"],
                end_ms=clip["end_ms"],
                edit_plan=clip["edit_plan"],
                clip_id=clip_id,
                run_id=run_id,
                request_id=self._audit_request_id,
            )
            preview = store.add_asset(
                clip_id=clip_id,
                kind="preview",
                source_path=generated["preview_path"],
                mime_type="video/mp4",
                duration_ms=generated["duration_ms"],
                width=generated["width"],
                height=generated["height"],
            )
            poster = store.add_asset(
                clip_id=clip_id,
                kind="poster",
                source_path=generated["poster_path"],
                mime_type="image/jpeg",
                width=generated["width"],
                height=generated["height"],
            )
            completed_job = store.update_job(
                job["job_id"], state="completed", run_id=run_id
            )
            completed_clip = store.update_clip(clip_id, {"status": "ready"})
            return {
                "job": completed_job,
                "clip": completed_clip,
                "preview": preview,
                "poster": poster,
            }
        except Exception as exc:
            store.update_job(
                job["job_id"],
                state="failed",
                run_id=run_id,
                error=str(exc)[:500],
            )
            try:
                store.update_clip(clip_id, {"status": "failed"})
            except (DomainConflictError, DomainValidationError):
                pass
            raise

    def _handle_api_v1_post(self, route_path: str, payload: dict) -> bool:
        store = self._domain_store()
        try:
            match = self.CLIP_PREVIEW_ROUTE.fullmatch(route_path)
            if match:
                result = self._create_preview_job(match.group(1))
                self.send_json(201, {"success": True, **result}, no_store=True)
                return True
            if route_path == "/api/v1/projects":
                source = payload.get("source")
                if not isinstance(source, dict):
                    raise DomainValidationError("Project source must be an object")
                project = store.create_project(
                    name=payload.get("name", ""),
                    source_uri=source.get("uri", ""),
                    source_kind=source.get("kind", ""),
                )
                self.send_json(
                    201,
                    {"success": True, "project": project},
                    no_store=True,
                )
                return True

            match = self.PROJECT_ANALYSIS_ROUTE.fullmatch(route_path)
            if match:
                project_id = match.group(1)
                project = store.get_project(project_id)
                source = store.get_primary_source(project_id)
                analysis = store.create_analysis(project_id=project_id)
                job = store.create_job(
                    project_id=project_id,
                    analysis_id=analysis["analysis_id"],
                    kind="analysis",
                    state="running",
                )
                try:
                    result = extract_transcript_and_analyze(
                        source["uri"],
                        cookies_file=payload.get("cookies"),
                    )
                    if result.get("success") is False:
                        store.fail_analysis(analysis["analysis_id"], result)
                        store.update_job(
                            job["job_id"],
                            state="failed",
                            error=str(result.get("error") or "Analysis failed"),
                        )
                        self.send_json(
                            422,
                            {
                                "success": False,
                                "project_id": project["project_id"],
                                "analysis_id": analysis["analysis_id"],
                                "job_id": job["job_id"],
                                "error": result.get("error") or "Analysis failed",
                            },
                            no_store=True,
                        )
                        return True
                    clips = store.finish_analysis(
                        analysis_id=analysis["analysis_id"],
                        result=result,
                    )
                    completed_job = store.update_job(
                        job["job_id"],
                        state="completed",
                    )
                    self.send_json(
                        201,
                        {
                            "success": True,
                            "project_id": project["project_id"],
                            "source_id": source["source_id"],
                            "analysis_id": analysis["analysis_id"],
                            "job": completed_job,
                            "clips": clips,
                        },
                        no_store=True,
                    )
                    return True
                except Exception as exc:
                    store.fail_analysis(
                        analysis["analysis_id"],
                        {"success": False, "error": str(exc)},
                    )
                    store.update_job(
                        job["job_id"],
                        state="failed",
                        error=str(exc)[:500],
                    )
                    raise

            return False
        except (DomainNotFoundError, DomainConflictError, DomainValidationError) as exc:
            self._send_domain_error(exc)
            return True
        except Exception:
            self.send_json(
                500,
                {"success": False, "error": "Persistent API operation failed"},
                no_store=True,
            )
            return True

    def _handle_api_v1_patch(self, route_path: str, payload: dict) -> bool:
        match = self.CLIP_ID_ROUTE.fullmatch(route_path)
        if not match:
            return False
        try:
            clip = self._domain_store().update_clip(match.group(1), payload)
            self.send_json(
                200,
                {"success": True, "clip": clip},
                no_store=True,
            )
        except (DomainNotFoundError, DomainConflictError, DomainValidationError) as exc:
            self._send_domain_error(exc)
        except Exception:
            self.send_json(
                500,
                {"success": False, "error": "Persistent API operation failed"},
                no_store=True,
            )
        return True

    @observed_http_request
    def do_GET(self):
        route_path = urllib.parse.urlsplit(self.path).path
        if route_path.startswith(self.STATUS_ROUTE_PREFIX):
            self._audit_authorized = self._is_authorized()
            if not self._audit_authorized:
                self._send_status_json(
                    401, {"success": False, "error": "Unauthorized"}
                )
                return
            raw_request_id = urllib.parse.unquote(
                route_path[len(self.STATUS_ROUTE_PREFIX):]
            )
            if not self.REQUEST_ID_PATTERN.fullmatch(raw_request_id):
                self._send_status_json(
                    400, {"success": False, "error": "Invalid request ID"}
                )
                return
            status_payload = self._request_status_payload(raw_request_id)
            if status_payload is None:
                self._send_status_json(
                    404, {"success": False, "error": "Operation not found"}
                )
                return
            self._send_status_json(200, status_payload)
            return

        if not self._require_authorization():
            return
        if route_path.startswith(self.API_V1_PREFIX):
            self._handle_api_v1_get(route_path)
            return
        if route_path in self.GET_ROUTES:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif route_path in self.TECHNICAL_GET_ROUTES:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(TECHNICAL_HTML_TEMPLATE.encode("utf-8"))
        elif route_path.startswith("/api/download/"):
            raw_param = urllib.parse.unquote(route_path[len("/api/download/"):])

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
                    self.wfile.write(f.read())
            else:
                self.send_json(404, {"success": False, "error": "File not found"})
        elif route_path in self.POST_ROUTES:
            self.send_error(405, "Method Not Allowed")
        else:
            self.send_error(404, "File Not Found")

    @observed_http_request
    def do_POST(self):
        if not self._require_authorization():
            return
        if not self._require_safe_post_context():
            return
        route_path = urllib.parse.urlsplit(self.path).path
        if (
            route_path in self.GET_ROUTES
            or route_path in self.TECHNICAL_GET_ROUTES
            or route_path.startswith("/api/download/")
            or route_path.startswith(self.STATUS_ROUTE_PREFIX)
        ):
            self.send_error(405, "Method Not Allowed")
            return
        elif route_path not in self.POST_ROUTES and not route_path.startswith(self.API_V1_PREFIX):
            self.send_error(404, "Endpoint not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return
        if content_length < 0:
            self.send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return
        if content_length > self.MAX_REQUEST_BODY_BYTES:
            self.send_json(413, {"success": False, "error": "Request body is too large"})
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

        if route_path.startswith(self.API_V1_PREFIX):
            if self._handle_api_v1_post(route_path, payload):
                return
            self.send_json(
                404,
                {"success": False, "error": "API v1 route not found"},
                no_store=True,
            )
            return

        if self.path == "/api/editor-chat":
            try:
                result = request_gemini_edit(
                    message=payload.get("message"),
                    clip=payload.get("clip", {}),
                    config=payload.get("config", {}),
                    history=payload.get("history", []),
                )
                self.send_json(200, {"success": True, **result}, no_store=True)
            except GeminiConfigurationError:
                self.send_json(
                    503,
                    {
                        "success": False,
                        "error": "Editor Gemini não configurado. Defina GEMINI_API_KEY no servidor.",
                    },
                    no_store=True,
                )
            except GeminiInputError as exc:
                self.send_json(
                    400, {"success": False, "error": str(exc)}, no_store=True
                )
            except GeminiEditorError as exc:
                self.send_json(
                    502, {"success": False, "error": str(exc)}, no_store=True
                )

        elif self.path == "/api/editor-assets":
            try:
                asset = self._store_editor_asset(payload=payload)
                self.send_json(201, {"success": True, **asset}, no_store=True)
            except ValidationError as exc:
                self.send_json(
                    400,
                    {"success": False, "error": str(exc), "field": exc.field},
                    no_store=True,
                )
            except OSError:
                self.send_json(
                    500,
                    {
                        "success": False,
                        "error": "Não foi possível armazenar o anexo.",
                    },
                    no_store=True,
                )

        elif self.path == "/api/cortes/run":
            try:
                settings = validate_technical_payload(payload)
                pipeline_run_id = self._new_child_run("cortes")
                pipeline_result = run_full_pipeline(
                    input_source=settings["input_path"],
                    run_id=pipeline_run_id,
                    request_id=self._audit_request_id,
                    whisper_model=settings["whisper_model"],
                    device=settings["device"],
                    language=settings["language"],
                    scene_threshold=settings["scene_threshold"],
                    min_scene_len=settings["min_scene_len"],
                    vertical_mode=settings["vertical_mode"],
                    blur_sigma=settings["blur_sigma"],
                    subtitle_font_name=settings["subtitle_font_name"],
                    subtitle_font_size=settings["subtitle_font_size"],
                    subtitle_margin_v=settings["subtitle_margin_v"],
                    analytical_overlay=settings["analytical_overlay"],
                    overlay_text=settings["overlay_text"],
                    narration_path=settings["narration_path"],
                    template_variant=settings["template_variant"],
                    require_editorial_transformation=settings[
                        "require_editorial_transformation"
                    ],
                )

                returned_run_id = str(
                    pipeline_result.get("run_id") or pipeline_run_id
                )
                run_dir = (Path.cwd() / "runs" / returned_run_id).resolve()
                with action_span(
                    "verify",
                    "pipeline.verify",
                    component="youtube_clipper.dashboard",
                    input_data={"run_id": returned_run_id},
                ) as verify_span:
                    measured = verify_run(run_dir)
                    verification = {
                        "overall_passed": bool(measured.get("overall_passed")),
                        "total_checks": int(measured.get("total_checks", 0)),
                        "passed_checks": int(measured.get("passed_checks", 0)),
                        "failed_checks": int(measured.get("failed_checks", 0)),
                    }
                    verify_span.decision = dict(verification)

                render_path_raw = pipeline_result.get("render_path")
                if not isinstance(render_path_raw, (str, os.PathLike)):
                    raise RuntimeError("Technical pipeline did not return render_path")
                render_path = Path(render_path_raw).resolve()
                if (
                    not render_path.exists()
                    or not render_path.is_file()
                    or render_path.suffix.lower() != ".mp4"
                ):
                    raise RuntimeError(
                        "Technical pipeline render_path is not a readable MP4 file"
                    )

                output_dir = self._output_dir()
                output_dir.mkdir(parents=True, exist_ok=True)
                request_token = re.sub(
                    r"[^A-Za-z0-9_-]", "", self._audit_request_id or ""
                )[-12:] or uuid.uuid4().hex[:12]
                generated_at = datetime.now(timezone.utc)
                filename = (
                    f"cortes_{settings['phase']}_"
                    f"{generated_at.strftime('%Y%m%d_%H%M%S_%f')}_"
                    f"{request_token}_{uuid.uuid4().hex[:8]}.mp4"
                )
                output_path = output_dir / filename
                shutil.copy2(render_path, output_path)
                download_url = f"/api/download/{urllib.parse.quote(filename)}"

                applied_settings = {
                    "phase": settings["phase"],
                    "input_path": str(settings["input_path"]),
                    "whisper_model": settings["whisper_model"],
                    "device": settings["device"],
                    "language": settings["language"],
                    "scene_threshold": settings["scene_threshold"],
                    "min_scene_len": settings["min_scene_len"],
                    "vertical_mode": settings["vertical_mode"],
                    "blur_sigma": (
                        settings["blur_sigma"]
                        if settings["vertical_mode"] != "crop_center"
                        else None
                    ),
                    "subtitles": {
                        "font_name": settings["subtitle_font_name"],
                        "font_size": settings["subtitle_font_size"],
                        "margin_v": settings["subtitle_margin_v"],
                        "burned_in": True,
                    },
                    "editorial": {
                        "required": settings["require_editorial_transformation"],
                        "analytical_overlay": settings["analytical_overlay"],
                        "overlay_text": settings["overlay_text"],
                        "narration_path": (
                            str(settings["narration_path"])
                            if settings["narration_path"] is not None
                            else None
                        ),
                        "template_variant": settings["template_variant"],
                    },
                }
                report_path = pipeline_result.get("report_path")
                subtitles_path = pipeline_result.get("subtitles_path")
                render_receipt = {
                    "request_id": self._audit_request_id,
                    "generated_at": generated_at.isoformat(),
                    "status": "measured",
                    "status_label": "Medição pós-run; não é declaração de fase",
                    "run_id": returned_run_id,
                    "file": {
                        "name": filename,
                        "size_bytes": output_path.stat().st_size,
                        "download_url": download_url,
                    },
                    "subtitles": {
                        "path": str(subtitles_path) if subtitles_path else None,
                        "label": "Arquivo ASS gerado e aplicado no render",
                    },
                    "report_snapshot": {
                        "path": str(report_path) if report_path else None,
                        "label": "Snapshot interno não verificado",
                    },
                    "verification": verification,
                    "applied_settings": applied_settings,
                }
                self.send_json(
                    200,
                    {
                        "success": True,
                        "overall_status": "measured",
                        "pipeline_run_id": returned_run_id,
                        "output_path": str(output_path),
                        "download_url": download_url,
                        "verification": verification,
                        "applied_settings": applied_settings,
                        "render_receipt": render_receipt,
                    },
                    no_store=True,
                )
            except ValidationError as e:
                self.send_json(
                    400,
                    {
                        "success": False,
                        "error": str(e),
                        "field": e.field,
                    },
                    no_store=True,
                )
            except FileNotFoundError as e:
                self.send_json(
                    404, {"success": False, "error": str(e)}, no_store=True
                )
            except Exception as e:
                self.send_json(
                    500, {"success": False, "error": str(e)}, no_store=True
                )

        elif self.path == "/api/analyze":
            url = payload.get("url", "")
            cookies = payload.get("cookies", None)
            if not url or not isinstance(url, str) or not url.strip():
                self.send_json(400, {"success": False, "error": "URL parameter required"})
                return
            try:
                clean_url = validate_input_source(url)
                if not is_youtube_url(clean_url):
                    raise ValidationError("Dashboard analysis accepts only YouTube URLs")
                analysis_result = extract_transcript_and_analyze(
                    clean_url, cookies_file=cookies
                )
                domain_result = self._persist_legacy_analysis(
                    clean_url=clean_url,
                    result=analysis_result,
                    requested_project_id=payload.get("project_id"),
                )
                stored_by_rank = {
                    int(clip["rank"]): clip
                    for clip in domain_result["clips"]
                }
                for candidate in analysis_result.get("clips", []):
                    stored = stored_by_rank.get(int(candidate.get("rank", 0)))
                    if stored:
                        candidate["clip_id"] = stored["clip_id"]
                        candidate["project_id"] = stored["project_id"]
                        candidate["analysis_id"] = stored["analysis_id"]
                        candidate["plan_version"] = stored["plan_version"]
                        candidate["preview_status"] = "not_created"
                        candidate["render_status"] = "not_started"
                analysis_result.update(
                    {
                        "project_id": domain_result["project_id"],
                        "source_id": domain_result["source_id"],
                        "analysis_id": domain_result["analysis_id"],
                    }
                )
                if isinstance(analysis_result, dict):
                    clips = analysis_result.get("clips", [])
                    all_transcripts = " ".join(c.get("transcript", "") for c in clips)
                    all_tags = list({tag for c in clips for tag in c.get("hashtags", [])})
                    analysis_result.setdefault("transcript", all_transcripts)
                    analysis_result.setdefault("hashtags", all_tags)
                if analysis_result.get("success") is False:
                    self.send_json(422, analysis_result)
                else:
                    self.send_json(200, analysis_result)
            except (DomainNotFoundError, DomainConflictError, DomainValidationError) as e:
                self._send_domain_error(e)
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

            if payload.get("confirmed_configuration") is not True:
                self.send_json(400, {
                    "success": False,
                    "error": "Review and explicitly confirm the clip configuration before rendering",
                    "field": "confirmed_configuration",
                })
                return

            start = payload.get("start", "0")
            end = payload.get("end", "10")
            fmt_mode = payload.get("format", payload.get("mode", "blur_background"))
            upload_gdrive = payload.get("gdrive", False)
            include_audio = payload.get("include_audio", True)
            folder_id = payload.get("folder_id", None)
            cookies = payload.get("cookies", None)
            crop_focus = payload.get("crop_focus", "center")
            overlay_position = payload.get("overlay_position", "top")
            overlay_text = payload.get("overlay_text", "")
            blur_sigma_raw = payload.get("blur_sigma", 12.0)
            music_asset_id = payload.get("background_music_asset_id") or None
            music_volume_raw = payload.get("background_music_volume", 0.2)
            intro_asset_id = payload.get("intro_image_asset_id") or None
            intro_duration_raw = payload.get("intro_duration", 0.0)
            background_music_path = None
            intro_image_path = None

            valid_modes = {"blur_background", "split_blur", "crop_center"}
            if fmt_mode not in valid_modes:
                self.send_json(400, {"success": False, "error": f"Invalid format mode: {fmt_mode}. Must be one of {sorted(list(valid_modes))}"})
                return
            if not isinstance(upload_gdrive, bool):
                self.send_json(400, {"success": False, "error": "gdrive must be a boolean"})
                return
            if not isinstance(include_audio, bool):
                self.send_json(400, {"success": False, "error": "include_audio must be a boolean"})
                return
            if crop_focus not in {"left", "center", "right"}:
                self.send_json(400, {"success": False, "error": "crop_focus must be left, center, or right"})
                return
            if overlay_position not in {"top", "bottom"}:
                self.send_json(400, {"success": False, "error": "overlay_position must be top or bottom"})
                return
            if not isinstance(overlay_text, str):
                self.send_json(400, {"success": False, "error": "overlay_text must be text"})
                return
            overlay_text = re.sub(r"[\x00-\x1f\x7f]+", " ", overlay_text).strip()
            if not overlay_text:
                self.send_json(400, {
                    "success": False,
                    "error": "An editorial overlay text is required for this render",
                    "field": "overlay_text",
                })
                return
            if len(overlay_text) > 90:
                self.send_json(400, {"success": False, "error": "overlay_text must contain at most 90 characters"})
                return
            if isinstance(blur_sigma_raw, bool):
                self.send_json(400, {"success": False, "error": "blur_sigma must be a number between 0 and 50"})
                return

            try:
                blur_sigma = float(blur_sigma_raw)
                if not 0.0 <= blur_sigma <= 50.0:
                    raise ValueError("blur_sigma must be between 0 and 50")
                if isinstance(music_volume_raw, bool):
                    raise ValidationError(
                        "background_music_volume must be between 0 and 1",
                        field="background_music_volume",
                    )
                music_volume = float(music_volume_raw)
                if not math.isfinite(music_volume) or not 0.0 <= music_volume <= 1.0:
                    raise ValidationError(
                        "background_music_volume must be between 0 and 1",
                        field="background_music_volume",
                    )
                if isinstance(intro_duration_raw, bool):
                    raise ValidationError(
                        "intro_duration must be between 0 and 5", field="intro_duration"
                    )
                intro_duration = float(intro_duration_raw)
                if not math.isfinite(intro_duration) or not 0.0 <= intro_duration <= 5.0:
                    raise ValidationError(
                        "intro_duration must be between 0 and 5", field="intro_duration"
                    )
                if music_asset_id and not include_audio:
                    raise ValidationError(
                        "Enable audio before adding a soundtrack", field="include_audio"
                    )
                if music_asset_id:
                    background_music_path = self._resolve_editor_asset(
                        music_asset_id, expected_kind="music"
                    )
                if intro_asset_id:
                    if intro_duration < 0.5:
                        raise ValidationError(
                            "intro_duration must be between 0.5 and 5",
                            field="intro_duration",
                        )
                    intro_image_path = self._resolve_editor_asset(
                        intro_asset_id, expected_kind="intro_image"
                    )
                elif intro_duration != 0.0:
                    raise ValidationError(
                        "intro_duration requires an intro image", field="intro_image_asset_id"
                    )
                start_seconds, end_seconds = validate_time_range(start, end, None)
                duration_seconds = end_seconds - start_seconds
                final_duration_seconds = duration_seconds + intro_duration
                if final_duration_seconds > 59.9:
                    raise ValidationError("The clip plus intro must be at most 59.9 seconds", field="time_range")

                clean_url = validate_input_source(url)
                if not is_youtube_url(clean_url):
                    raise ValidationError("Dashboard generation accepts only YouTube URLs")

                store = None
                persisted_clip = None
                requested_clip_id = payload.get("clip_id")
                if requested_clip_id:
                    store = self._domain_store()
                    persisted_clip = store.get_clip(str(requested_clip_id))
                    requested_project_id = payload.get("project_id")
                    if (
                        requested_project_id
                        and persisted_clip["project_id"] != requested_project_id
                    ):
                        raise DomainConflictError("Clip belongs to a different project")
                    source = store.get_source(persisted_clip["source_id"])
                    if source["uri"] != clean_url:
                        raise DomainConflictError("Clip belongs to a different source")
                    expected_start = int(round(start_seconds * 1000))
                    expected_end = int(round(end_seconds * 1000))
                    if (
                        persisted_clip["start_ms"] != expected_start
                        or persisted_clip["end_ms"] != expected_end
                    ):
                        raise DomainConflictError(
                            "Render interval differs from the persisted edit plan"
                        )
                    persisted_clip = store.update_clip(
                        persisted_clip["clip_id"],
                        {
                            "layout": {
                                "mode": fmt_mode,
                                "crop_focus": crop_focus,
                                "blur_sigma": blur_sigma,
                                "overlay_position": overlay_position,
                            },
                            "audio": {"include_source": include_audio},
                            "editorial": {"overlay_text": overlay_text},
                        },
                    )
                    render_plan = persisted_clip["edit_plan"]
                    render_layout = render_plan["layout"]
                    fmt_mode = render_layout.get("mode", "blur_background")
                    crop_focus = render_layout.get("crop_focus", "center")
                    blur_sigma = float(render_layout.get("blur_sigma", 12.0))
                    overlay_position = render_layout.get("overlay_position", "top")
                    include_audio = bool(
                        (render_plan.get("audio") or {}).get("include_source", True)
                    )
                    overlay_text = (
                        (render_plan.get("editorial") or {}).get("overlay_text")
                        or overlay_text
                    )

                output_dir = self._output_dir()
                output_dir.mkdir(parents=True, exist_ok=True)
                request_token = re.sub(r"[^A-Za-z0-9_-]", "", self._audit_request_id or "")[-12:]
                if not request_token:
                    request_token = uuid.uuid4().hex[:12]
                output_target = output_dir / (
                    f"clip_{int(start_seconds * 1000)}_{int(end_seconds * 1000)}_{request_token}.mp4"
                )
                pipeline_run_id = self._new_child_run("pipeline")
                output_path = run_pipeline(
                    input_source=clean_url,
                    start=start_seconds,
                    end=end_seconds,
                    output=str(output_target),
                    vertical=True,
                    mode=fmt_mode,
                    blur_sigma=blur_sigma,
                    crop_focus=crop_focus,
                    include_audio=include_audio,
                    background_music_path=background_music_path,
                    background_music_volume=music_volume,
                    intro_image_path=intro_image_path,
                    intro_duration=intro_duration,
                    overlay_text=overlay_text,
                    overlay_position=overlay_position,
                    cookies=cookies,
                    run_id=pipeline_run_id,
                    request_id=self._audit_request_id,
                    clip_id=(
                        persisted_clip["clip_id"]
                        if persisted_clip is not None
                        else None
                    ),
                )

                try:
                    probed = probe_video_metadata(Path(output_path))
                    media_probe = {
                        "verified": bool(
                            probed.get("duration", 0) > 0
                            and probed.get("width", 0) > 0
                            and probed.get("height", 0) > 0
                            and probed.get("video_codec") not in {None, "", "unknown"}
                        ),
                        "duration_seconds": probed.get("duration"),
                        "width": probed.get("width"),
                        "height": probed.get("height"),
                        "fps": probed.get("fps"),
                        "video_codec": probed.get("video_codec"),
                        "audio_codec": probed.get("audio_codec"),
                        "audio_channels": probed.get("audio_channels"),
                        "file_size_bytes": probed.get("file_size"),
                        "sha256": probed.get("sha256"),
                        "error": None,
                    }
                except Exception as probe_error:
                    media_probe = {
                        "verified": False,
                        "duration_seconds": None,
                        "width": None,
                        "height": None,
                        "fps": None,
                        "video_codec": None,
                        "audio_codec": None,
                        "audio_channels": None,
                        "file_size_bytes": os.path.getsize(output_path),
                        "sha256": None,
                        "error": str(probe_error)[:240],
                    }

                domain_render = None
                if persisted_clip is not None and store is not None:
                    render_asset = store.add_asset(
                        clip_id=persisted_clip["clip_id"],
                        kind="render",
                        source_path=output_path,
                        mime_type="video/mp4",
                        duration_ms=(
                            int(round(float(media_probe["duration_seconds"]) * 1000))
                            if media_probe.get("duration_seconds") is not None
                            else None
                        ),
                        width=media_probe.get("width"),
                        height=media_probe.get("height"),
                    )
                    current_status = persisted_clip["status"]
                    if current_status in {"proposed", "previewing", "rejected"}:
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "ready"}
                        )
                        current_status = persisted_clip["status"]
                    if current_status == "ready":
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "approved"}
                        )
                        current_status = persisted_clip["status"]
                    if current_status in {
                        "approved", "failed", "rendered", "exported"
                    }:
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "rendering"}
                        )
                        current_status = persisted_clip["status"]
                    if current_status == "rendering":
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "rendered"}
                        )
                    domain_render = store.create_render(
                        clip_id=persisted_clip["clip_id"],
                        asset_id=render_asset["asset_id"],
                        status="rendered",
                    )
                    domain_render["asset"] = render_asset

                gdrive_link = None
                gdrive_result = {
                    "requested": upload_gdrive,
                    "success": None,
                    "error": None,
                    "web_view_link": None,
                    "permission_configured": None,
                }
                if upload_gdrive:
                    gdrive_run_id = self._new_child_run("gdrive")
                    res = upload_clip_to_gdrive(
                        output_path,
                        folder_id=folder_id,
                        run_id=gdrive_run_id,
                        request_id=self._audit_request_id,
                    )
                    gdrive_result["success"] = bool(res.get("success"))
                    gdrive_result["error"] = res.get("error")
                    gdrive_result["permission_configured"] = res.get("permission_configured")
                    progress_result = res.get("upload_progress") or {}
                    gdrive_result["progress_percent"] = progress_result.get("progress_percent")
                    gdrive_result["uploaded_bytes"] = progress_result.get("uploaded_bytes")
                    gdrive_result["total_bytes"] = progress_result.get("total_bytes")
                    gdrive_result["chunk_number"] = progress_result.get("chunk_number")
                    if res.get("success"):
                        gdrive_link = res.get("web_view_link")
                        gdrive_result["web_view_link"] = gdrive_link

                filename = os.path.basename(output_path)
                download_url = f"/api/download/{filename}"
                partial_success = upload_gdrive and (
                    not gdrive_result["success"]
                    or gdrive_result["permission_configured"] is False
                )
                overall_status = "partial_success" if partial_success else "success"
                format_labels = {
                    "blur_background": "Fundo desfocado",
                    "split_blur": "Fundo desfocado",
                    "crop_center": "Crop vertical",
                }
                applied_settings = {
                    "start_seconds": start_seconds,
                    "end_seconds": end_seconds,
                    "duration_seconds": round(duration_seconds, 3),
                    "final_duration_seconds": round(final_duration_seconds, 3),
                    "format": fmt_mode,
                    "format_label": format_labels[fmt_mode],
                    "crop_focus": crop_focus,
                    "blur_sigma": blur_sigma if fmt_mode in {"blur_background", "split_blur"} else None,
                    "audio_included": include_audio,
                    "background_music": {
                        "included": background_music_path is not None,
                        "asset_id": music_asset_id,
                        "volume": music_volume if background_music_path is not None else None,
                    },
                    "intro_image": {
                        "included": intro_image_path is not None,
                        "asset_id": intro_asset_id,
                        "duration_seconds": intro_duration if intro_image_path is not None else 0.0,
                    },
                    "editorial_overlay": {
                        "included": True,
                        "text": overlay_text,
                        "position": overlay_position,
                    },
                    "captions_included": False,
                    "narration_included": False,
                    "hashtags_burned_in": False,
                    "resolution": {"width": 1080, "height": 1920, "aspect_ratio": "9:16"},
                    "destination": {
                        "local": True,
                        "gdrive_requested": upload_gdrive,
                        "gdrive_completed": gdrive_result["success"] is True,
                    },
                }
                included = ["Vídeo no intervalo selecionado", "Selo editorial sobreposto"]
                if include_audio:
                    included.append("Áudio original em AAC")
                if background_music_path is not None:
                    included.append("Trilha sonora mixada")
                if intro_image_path is not None:
                    included.append("Imagem inicial")
                not_included = ["Legendas queimadas", "Narração", "Hashtags visuais"]
                if not include_audio:
                    not_included.insert(0, "Áudio original")
                if background_music_path is None:
                    not_included.append("Trilha sonora")
                if intro_image_path is None:
                    not_included.append("Imagem inicial")
                render_receipt = {
                    "request_id": self._audit_request_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": overall_status,
                    "file": {
                        "name": filename,
                        "size_bytes": media_probe.get("file_size_bytes") or os.path.getsize(output_path),
                        "download_url": download_url,
                        "video_codec": media_probe.get("video_codec") or "h264",
                        "audio_codec": media_probe.get("audio_codec") if include_audio else None,
                        "sha256": media_probe.get("sha256"),
                    },
                    "measured_media": media_probe,
                    "included": included,
                    "not_included": not_included,
                    "applied_settings": applied_settings,
                }
                resp_data = {
                    "success": True,
                    "project_id": domain_render.get("project_id") if domain_render else None,
                    "clip_id": domain_render.get("clip_id") if domain_render else None,
                    "render_id": domain_render.get("render_id") if domain_render else None,
                    "asset": domain_render.get("asset") if domain_render else None,
                    "overall_status": overall_status,
                    "output_path": output_path,
                    "clip_path": output_path,
                    "download_url": download_url,
                    "gdrive_link": gdrive_link,
                    "upload": gdrive_result,
                    "applied_settings": applied_settings,
                    "render_receipt": render_receipt,
                }
                self.send_json(200, resp_data)
            except (DomainNotFoundError, DomainConflictError, DomainValidationError) as e:
                self._send_domain_error(e)
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
                gdrive_run_id = self._new_child_run("gdrive")
                res = upload_clip_to_gdrive(
                    str(allowed_file),
                    folder_id=folder_id,
                    run_id=gdrive_run_id,
                    request_id=self._audit_request_id,
                )
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

    @observed_http_request
    def do_PUT(self):
        self._handle_unsupported_method()

    @observed_http_request
    def do_DELETE(self):
        self._handle_unsupported_method()

    @observed_http_request
    def do_PATCH(self):
        if not self._require_authorization():
            return
        if not self._require_safe_post_context():
            return
        route_path = urllib.parse.urlsplit(self.path).path
        if not route_path.startswith(self.API_V1_PREFIX):
            self._handle_unsupported_method()
            return
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return
        if content_length <= 0 or content_length > self.MAX_REQUEST_BODY_BYTES:
            status = 413 if content_length > self.MAX_REQUEST_BODY_BYTES else 400
            self.send_json(status, {"success": False, "error": "Invalid request body size"})
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            self.send_json(400, {"success": False, "error": "Invalid JSON format"})
            return
        if not isinstance(payload, dict):
            self.send_json(400, {"success": False, "error": "JSON payload must be an object"})
            return
        if self._handle_api_v1_patch(route_path, payload):
            return
        self.send_json(
            404,
            {"success": False, "error": "API v1 route not found"},
            no_store=True,
        )


    @observed_http_request
    def do_HEAD(self):
        self._handle_unsupported_method()

    @observed_http_request
    def do_OPTIONS(self):
        self._handle_unsupported_method()

    def _handle_unsupported_method(self):
        if not self._require_authorization():
            return
        all_routes = self.GET_ROUTES | self.TECHNICAL_GET_ROUTES | self.POST_ROUTES
        if (
            self.path in all_routes
            or self.path.startswith("/api/download/")
            or self.path.startswith(self.STATUS_ROUTE_PREFIX)
        ):
            self.send_error(405, "Method Not Allowed")
        else:
            self.send_error(404, "Not Found")


def start_dashboard_server(
    port: int = 8080,
    host: str = "127.0.0.1",
    api_token: str | None = None,
    output_dir: str | Path | None = None,
):
    """Start the dashboard with explicit exposure and a dedicated output root."""
    normalized_host = host.strip() or "127.0.0.1"
    if normalized_host not in {"127.0.0.1", "::1", "localhost"} and not api_token:
        raise ValueError("A bearer API token is required when binding beyond loopback")
    server_address = (normalized_host, port)
    httpd = ThreadingHTTPServer(server_address, ClipperDashboardHandler)
    httpd.api_token = api_token
    httpd.output_dir = Path(output_dir or (Path.cwd() / "output")).resolve()
    httpd.output_dir.mkdir(parents=True, exist_ok=True)
    httpd.panel_workspace = (httpd.output_dir.parent / "panel_workspace").resolve()
    httpd.panel_workspace.mkdir(parents=True, exist_ok=True)
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
