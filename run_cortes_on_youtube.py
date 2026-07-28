#!/usr/bin/env python3
import sys
from pathlib import Path
from youtube_clipper.downloader import YouTubeDownloader
from cortes.pipeline import run_full_pipeline
from youtube_clipper.gdrive_uploader import upload_clip_to_gdrive

def main():
    url = "https://www.youtube.com/watch?v=IRRYIuKv-9w"
    start = 585.0  # 09:45
    end = 615.0    # 10:15
    run_id = "run_cortes_youtube_test"

    print("📥 1. Baixando segmento horizontal de 30s do YouTube...")
    downloader = YouTubeDownloader()
    output_dir = Path("runs") / "temp_input"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        media_source_path = downloader.download_segment(
            url=url,
            start=start,
            end=end,
            output_dir=output_dir,
        )
        print(f"✅ Vídeo baixado localmente em: {media_source_path}")
    except Exception as e:
        print(f"❌ Falha ao baixar vídeo do YouTube: {e}")
        sys.exit(1)

    print("\n🎬 2. Iniciando Pipeline Técnico 'cortes' (Transcrição, Legenda e Render 9:16)...")
    try:
        pipeline_res = run_full_pipeline(
            input_source=media_source_path,
            run_id=run_id,
            whisper_model="small",
            device="cuda",
            vertical_mode="blur_background",
            analytical_overlay=True,
            overlay_text="CORTES AI | NILO AZUL",
            require_editorial_transformation=True,
            template_variant="variant_youtube_short",
        )
        render_path = pipeline_res["render_path"]
        print(f"✅ Renderização concluída com sucesso!")
        print(f"📹 Vídeo Vertical com legendas queimadas em: {render_path}")
    except Exception as e:
        print(f"❌ Falha ao executar o pipeline técnico 'cortes': {e}")
        sys.exit(1)

    print("\n☁️ 3. Fazendo upload do clipe com legendas queimadas para o Google Drive...")
    try:
        upload_res = upload_clip_to_gdrive(render_path)
        if upload_res.get("success"):
            print("✅ Upload concluído no Google Drive!")
            print(f"🔗 Link: {upload_res.get('web_view_link')}")
        else:
            print(f"❌ Falha no upload: {upload_res.get('error')}")
    except Exception as e:
        print(f"❌ Erro ao enviar para o Google Drive: {e}")

if __name__ == "__main__":
    main()
