"""H05 — O corte de URL do YouTube aplica o offset duas vezes.

Correção do FISC-GPT-001: o run anterior classificou H05 como REFUTADA depois de
apenas imprimir o código-fonte de ``cut_media``. Nenhum cenário foi executado.
Aqui a hipótese é reproduzida de ponta a ponta, como o plano exige:

  - fonte sintética local de 30 s criada com ``ffmpeg lavfi`` (nada é baixado
    do YouTube; nenhuma credencial é lida);
  - ``download_segment`` é substituído por monkeypatch e devolve esse arquivo já
    recortado começando em t=0, exatamente como ocorre após o corte por
    ``download_ranges`` do yt-dlp;
  - o pipeline real é chamado com o intervalo absoluto 60–90 s;
  - o comando FFmpeg efetivamente construído é capturado;
  - código de saída, existência, tamanho e duração via ffprobe são medidos.

Classificação exigida pelo plano: erro corretamente detectado / arquivo inválido
aceito como sucesso / comportamento não reproduzível.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))

tmp = pathlib.Path(tempfile.mkdtemp(prefix="h05_"))
fonte = tmp / "fonte_30s.mp4"
saida = tmp / "clip_saida.mp4"

print("== H05.1 — fonte sintética local de 30 s (ffmpeg lavfi, sem YouTube) ==")
mk = subprocess.run(
    ["ffmpeg", "-y", "-v", "error",
     "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=30",
     "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
     "-c:v", "libx264", "-c:a", "aac", "-shortest", str(fonte)],
    capture_output=True, text=True,
)
print(f"  ffmpeg exit={mk.returncode} stderr={mk.stderr.strip()[:200] or '<vazio>'}")


def ffprobe(path: pathlib.Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return {"exit": r.returncode, "stderr": r.stderr.strip(),
            "data": json.loads(r.stdout) if r.stdout.strip() else {}}


p_fonte = ffprobe(fonte)
dur_fonte = float(p_fonte["data"].get("format", {}).get("duration", 0.0))
print(f"  fonte: bytes={fonte.stat().st_size} duração_ffprobe={dur_fonte:.3f}s")

print()
print("== H05.2 — monkeypatch: downloader devolve o trecho já recortado em t=0 ==")
from youtube_clipper import pipeline as pl  # noqa: E402
from youtube_clipper import processor as pr  # noqa: E402

chamadas_download: list[dict] = []
comandos_ffmpeg: list[list[str]] = []


class FakeDownloader:
    """Emula o downloader real: já entrega o segmento recortado a partir de t=0."""

    def download_segment(self, url, start, end, output_dir, progress_callback=None):
        destino = pathlib.Path(output_dir) / "segmento_ja_recortado.mp4"
        shutil.copy2(fonte, destino)
        chamadas_download.append({"url": url, "start": start, "end": end,
                                  "retorno": str(destino),
                                  "duracao_retornada_s": dur_fonte})
        return str(destino)


_subprocess_run_real = pr.subprocess.run


def subprocess_run_espiao(cmd, *a, **kw):
    if isinstance(cmd, (list, tuple)):
        comandos_ffmpeg.append(list(cmd))
    return _subprocess_run_real(cmd, *a, **kw)


pl.YouTubeDownloader = FakeDownloader
pr.subprocess.run = subprocess_run_espiao

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
print(f"  URL de entrada (nunca acessada em rede): {URL}")
print("  intervalo absoluto solicitado: start=60 end=90")

print()
print("== H05.3 — execução do pipeline real ==")
resultado, excecao = None, None
try:
    resultado = pl.run_pipeline(input_source=URL, start=60, end=90, output=str(saida))
except Exception as e:  # noqa: BLE001 - a natureza da exceção é o dado medido
    excecao = f"{type(e).__name__}: {e}"
finally:
    pr.subprocess.run = _subprocess_run_real

print(f"  chamadas a download_segment: {json.dumps(chamadas_download, ensure_ascii=False, indent=2)}")
print(f"  comandos FFmpeg efetivamente construídos ({len(comandos_ffmpeg)}):")
for c in comandos_ffmpeg:
    print(f"    {' '.join(c)}")
print(f"  retorno do pipeline: {resultado}")
print(f"  exceção levantada: {excecao or '<nenhuma>'}")

print()
print("== H05.4 — medição do artefato produzido ==")
existe = saida.exists()
tamanho = saida.stat().st_size if existe else 0
print(f"  arquivo de saída existe: {existe}")
print(f"  bytes: {tamanho}")
p_saida = ffprobe(saida) if existe else {"exit": None, "stderr": "arquivo inexistente", "data": {}}
dur_saida = float(p_saida["data"].get("format", {}).get("duration", 0.0)) if p_saida["data"] else 0.0
streams = p_saida["data"].get("streams", []) if p_saida["data"] else []
print(f"  ffprobe exit={p_saida['exit']} stderr={p_saida['stderr'][:200] or '<vazio>'}")
print(f"  streams detectados: {len(streams)} -> {[s.get('codec_type') for s in streams]}")
print(f"  duração medida: {dur_saida:.3f}s (esperado por um usuário: 30.000s)")

print()
print("== H05.4b — CONTROLE: mesmo pipeline com intervalo 0–10 s ==")
print("  (serve para distinguir defeito do pipeline de defeito do próprio ensaio)")
saida_ctl = tmp / "clip_controle.mp4"
comandos_ffmpeg_ctl: list[list[str]] = []
_ctl_real = pr.subprocess.run


def espiao_ctl(cmd, *a, **kw):
    if isinstance(cmd, (list, tuple)):
        comandos_ffmpeg_ctl.append(list(cmd))
    return _ctl_real(cmd, *a, **kw)


pr.subprocess.run = espiao_ctl
resultado_ctl, excecao_ctl = None, None
try:
    resultado_ctl = pl.run_pipeline(input_source=URL, start=0, end=10, output=str(saida_ctl))
except Exception as e:  # noqa: BLE001
    excecao_ctl = f"{type(e).__name__}: {e}"
finally:
    pr.subprocess.run = _ctl_real

p_ctl = ffprobe(saida_ctl) if saida_ctl.exists() else {"exit": None, "stderr": "inexistente", "data": {}}
dur_ctl = float(p_ctl["data"].get("format", {}).get("duration", 0.0)) if p_ctl["data"] else 0.0
for c in comandos_ffmpeg_ctl:
    print(f"    {' '.join(c)}")
print(f"  exceção: {excecao_ctl or '<nenhuma>'}")
print(f"  saída existe={saida_ctl.exists()} duração_medida={dur_ctl:.3f}s (esperado 10.000s)")
controle_ok = excecao_ctl is None and abs(dur_ctl - 10.0) < 1.0
print(f"  H05_CONTROLE_OK={controle_ok}")

print()
print("== H05.5 — classificação ==")
offset_duplo = any(
    "-ss" in c and float(c[c.index("-ss") + 1]) >= dur_fonte for c in comandos_ffmpeg
)
print(f"  o pipeline reaplicou o offset absoluto a um arquivo que já começa em t=0: {offset_duplo}")

if excecao and not existe:
    classificacao = "ERRO_CORRETAMENTE_DETECTADO"
elif existe and (len(streams) == 0 or dur_saida < 1.0):
    classificacao = "ARQUIVO_INVALIDO_ACEITO_COMO_SUCESSO"
elif existe and abs(dur_saida - 30.0) < 1.0:
    classificacao = "COMPORTAMENTO_CORRETO"
elif excecao:
    classificacao = "ERRO_DETECTADO_COM_ARTEFATO_RESIDUAL"
else:
    classificacao = "COMPORTAMENTO_NAO_REPRODUZIVEL"

print(f"  H05_CLASSIFICACAO={classificacao}")
print(f"H05_ESTADO={'CONFIRMADA' if offset_duplo else 'REFUTADA'}")
print(f"H05_SANDBOX={tmp}")
