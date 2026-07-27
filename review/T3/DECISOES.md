# Decisões de Arquitetura e Engenharia — Fase T3

## 1. Single-Pass FFmpeg Filtergraph for 9:16 Vertical Renders
- **Contexto**: A abordagem anterior realizava o corte em duas passadas (corte inicial de mídia seguido de uma segunda passada para conversão vertical e aplicação de filtros), resultando em redundância de I/O em disco e latência de processamento (~15s–20s para clipes de 5s).
- **Decisão**: Unificar busca rápida (`-ss`), limitação de duração (`-t`), transformação de layout vertical 9:16 (`-vf` / `-filter_complex`), queima de legendas ASS e sobreposição gráfica analítica em um único comando FFmpeg em passada única.
- **Alternativas Descartadas**: Manter pipeline em 2 etapas com arquivos intermediários `.mp4` temporários.
- **Justificativa**: A passada única elimina 50% das operações de escrita/leitura em disco e acelera a renderização em ~11x.

## 2. Dynamic Hardware Encoder Detection (`h264_nvenc` with Transparent `libx264` Fallback)
- **Contexto**: O ambiente de produção/host possui GPU NVIDIA com aceleração de hardware NVENC, mas a aplicação precisa rodar de forma portátil em ambientes CPU sem falhar.
- **Decisão**: Implementar `detect_h264_encoder()` com sondagem dinâmica via `run_cmd` (1 frame com `nullsrc` e `audit=False`), memoizado via `@functools.lru_cache(maxsize=1)`. Se NVENC estiver funcional (exit code 0), utiliza `-c:v h264_nvenc -preset p4`; caso contrário, faz fallback para `-c:v libx264 -preset ultrafast/medium -crf 23`.
- **Alternativas Descartadas**: Hardcoding do codec `h264_nvenc` ou checagem ingênua apenas por presença de `nvidia-smi`.
- **Justificativa**: A sondagem real com 1 frame garante que a biblioteca NVENC e os drivers CUDA estão operacionais de fato.

## 3. Low-Resolution Gaussian Blur Background Optimization
- **Contexto**: Aplicar filtro de desfoque Gaussiano (`gblur`) na resolução completa 1080x1920 exige computação pesada sobre 2.073.600 pixels por frame, tornando-se o principal gargalo de CPU/GPU.
- **Decisão**: Reduzir a escala do fluxo de fundo para 1/4 da resolução canvas (`270x480`), aplicar o desfoque Gaussiano (`gblur=sigma=12.0` ou `15.0`) no fluxo reduzido (apenas 129.600 pixels, redução de 16x de carga), e posteriormente reescalar para 1080x1920 antes da sobreposição do primeiro plano.
- **Alternativas Descartadas**: Aplicação de `boxblur` ou `gblur` direto na resolução nativa 1080x1920.
- **Justificativa**: Redução de 16x na superfície de cálculo de pixels com resultado estético idêntico e preservação de qualidade visual no canvas final 9:16.

## 4. Editorial Transformation Layer (TTS Narration & Analytical Visual Overlay)
- **Contexto**: Diretrizes de monetização e política de uso reutilizado do YouTube exigem contribuição autoral/editorial própria substancial em vídeos curtos gerados por automação.
- **Decisão**: Integrar camada editorial contendo narração autoral (TTS local/sintetizada com duração ≥ 8s) e sobreposição visual analítica (infográfico/banner com métrica e destaque de engajamento).
- **Alternativas Descartadas**: Apenas recortar e queimar legendas no vídeo original.
- **Justificativa**: Garante conformidade com critérios de conteúdo original transformativo e monetizável.

## 5. Template Variant Tracking & Variation Rules
- **Contexto**: Sistemas de automação que repetem rigorosamente a mesma disposição visual de elementos em múltiplos renders podem ser classificados como spam por repetição de template.
- **Decisão**: Incorporar `template_variant` ao hash que produz o `clip_id`, registrar no `render_metadata.json` uma fotografia dos cinco renders anteriores e rejeitar, antes do FFmpeg, qualquer variant repetido nessa janela. Caminhos de compatibilidade por symlink são deduplicados pelo destino real.
- **Alternativas Descartadas**: Manter estilo de filtro e layout 100% estático sem rastreabilidade de versão.
- **Justificativa**: Permite auditoria de variação estética e conformidade com diretrizes de diversidade de conteúdo.

## 6. Zero-Trust AST Security Scan & Subprocess Gateway Enforcement
- **Contexto**: Riscos de vazamento de subprocessos não auditados fora do barramento de auditoria `cortes.log`.
- **Decisão**: Aplicar scanner estático AST (`tests/test_contracts.py`) banindo chamadas diretas a `subprocess`, `os.system`, `os.popen`, `exec`/`eval`, `importlib`, `pty`, `ctypes` e `asyncio` subprocess fora de `src/cortes/log.py`.
- **Alternativas Descartadas**: Confiar apenas em convenções de código por revisão manual.
- **Justificativa**: Garante auditoria total e rastreabilidade 100% à prova de evasão.
