# Plano de Melhorias — YouTube Clipper

Baseado na execução real do pipeline em 26/07/2026 na VM `render-gpu`.
Estado inicial: 406 testes passando, pipeline gera 9:16 corretamente a partir de fonte local,
YouTube bloqueado por botguard, Drive bloqueado por cota da service account.

Ordem escolhida por **risco de dado corrompido → visibilidade de erro → custo de máquina → desbloqueios → produto**.
As fases 1-3 são independentes entre si e não dependem de nenhuma decisão externa.

---

## Fase 0 — Baseline anti-regressão

**Por quê:** as fases 1 e 3 mudam o que sai do ffmpeg. Sem baseline não dá pra provar que não quebrou.

- Congelar o clipe de referência atual (`short_teste_9x16.mp4`, 30 s, 1080x1920) como artefato de comparação.
- Registrar o tempo de parede atual (3m27s para 30 s de vídeo) como número a bater.
- Adicionar `tests/test_regression_media.py`: gera um clipe curto a partir de um MP4 sintético
  (`ffmpeg -f lavfi -i testsrc`) e afirma **duração, resolução e tamanho mínimo** do arquivo de saída.
  Hoje nenhum teste valida o conteúdo real do MP4 — por isso o bug da Fase 1 passou despercebido.

**Esforço:** ~1h · **Risco:** nenhum

---

## Fase 1 — 🔴 Corrigir o corte duplo (crítico, corrompe dados em silêncio)

**Arquivo:** `src/youtube_clipper/pipeline.py:138-174`

**Defeito:** `download_segment` já devolve o trecho recortado começando em t=0
(yt-dlp aplica `-ss/-t` sem `-copyts`). O pipeline então corta **de novo** usando o `start_sec`
absoluto. Com `--start 60 --end 90` o segundo corte procura o segundo 60 dentro de um arquivo de 30 s.
Reproduzido: ffmpeg retorna **exit 0** e escreve um MP4 de **262 bytes sem duração**,
que o caminho não-vertical devolve como sucesso.

**Correção:** após o download, o offset já foi consumido. Normalizar antes do corte:

```python
if is_youtube_url(clean_input):
    media_source_path = downloader.download_segment(...)
    cut_start, cut_end = 0.0, end_sec - start_sec   # o offset já foi aplicado no download
else:
    media_source_path = clean_input
    cut_start, cut_end = start_sec, end_sec
```

e usar `cut_start`/`cut_end` nas duas chamadas de `cut_media` (linhas 151 e 174).

**Correção secundária —** `src/youtube_clipper/processor.py`: `cut_media` só verifica
`outp.exists()`. Passar a validar `st_size > 1024` **e** que o `ffprobe` devolve duração,
para que um corte fora de faixa vire erro em vez de arquivo vazio. Essa é a defesa que faltava
para o bug acima ser barulhento em vez de silencioso.

**Validação:** teste que simula o cenário (arquivo de 30 s + `start=60`) e exige `ProcessingError`.
Depois de desbloquear os cookies (Fase 4), rodar o caso real ponta a ponta.

**Esforço:** ~2h · **Risco:** baixo — os testes atuais mockam o downloader, então o comportamento
mockado precisa ser revisto junto

---

## Fase 2 — 🟡 Tornar os erros visíveis

**Arquivo:** `src/youtube_clipper/analyzer.py:279-291`

**Defeito:** o stderr do yt-dlp vai para `PIPE` e é descartado. O erro real
(`Sign in to confirm you're not a bot`) vira `"Legendas automáticas não encontradas para o vídeo."`.
Foi esse mascaramento que fez o diagnóstico apontar para o lado errado.

**Correção:**
- Capturar `res.stderr` e incluí-lo no dict de retorno (`"detail"`), além de logar.
- Classificar as causas conhecidas em mensagens acionáveis:
  `bot / Sign in` → "YouTube exigiu autenticação — use `--cookies`";
  `Video unavailable` → indisponível/privado;
  ausência real de faixa → a mensagem atual.
- `analyzer.py:255`: trocar `python_env_bin: str = ".venv/bin"` (relativo ao cwd) por resolução
  a partir de `sys.executable` — `Path(sys.executable).parent / "yt-dlp"`, com fallback no PATH.

**Correção de contexto:** o projeto não emite **nenhum** log. A VM já tem barramento de eventos
(`/media/logs/pipeline-events.jsonl` via `/usr/local/bin/pipeline-event`) usado pelo pipeline de
produção. Emitir os eventos de etapa nesse mesmo barramento dá observabilidade de graça e
alinha os dois pipelines. Ver `pipeline-cortes-observabilidade`.

**Esforço:** ~2h · **Risco:** nenhum

---

## Fase 3 — ⚡ Performance: 11x mais rápido

**Arquivos:** `src/youtube_clipper/video_formatter.py:37,70-71` e `pipeline.py`

**Defeito:** o gargalo **não é o encoder** — é o `boxblur=20:10` rodando em 1080x1920.
Medições reais para o mesmo clipe de 30 s:

| Variante | Tempo |
|---|---|
| Atual (2 passes, libx264) | ~207 s |
| 1 passe, libx264 | 193 s |
| 1 passe, NVENC | 184 s |
| **1 passe + blur em baixa-res + NVENC** | **18 s** |

Trocar o encoder sozinho ganha 4%. Blurar em baixa resolução ganha 11x.

**Correção 3a — filtro (o ganho real):**

```
split[bg][fg];
[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,gblur=sigma=12,scale=1080:1920[blurred];
[fg]scale=1080:-2[scaled_fg];
[blurred][scaled_fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2
```

Frames comparados lado a lado: visualmente equivalente. `sigma` fica exposto como parâmetro
para ajuste fino da intensidade.

**Correção 3b — passe único:** hoje o caminho vertical corta com libx264 e **re-encoda** na
conversão. Além do tempo, isso é perda de geração. Aplicar `-ss`/`-t` e o filtro numa única
invocação do ffmpeg.

**Correção 3c — NVENC opcional:** a T4 da máquina está ociosa e o `h264_nvenc` já existe no ffmpeg
local. Detectar em runtime (`ffmpeg -encoders`) e cair para `libx264` quando ausente — o código
precisa continuar rodando em máquina sem GPU.

**Validação:** comparar contra o baseline da Fase 0 — mesma duração, mesma resolução, tempo < 30 s.

**Esforço:** ~3h · **Risco:** médio — muda a saída visual; exige conferência de um frame antes/depois

---

## Fase 4 — 🔓 Desbloquear o YouTube (cookies)

**Bloqueio:** `Sign in to confirm you're not a bot` em **todos** os player clients testados
(tv, web_safari, web_embedded, android_vr, mweb, ios) e nas duas versões de yt-dlp da VM.
É o IP de datacenter do GCP, não a versão. Nenhum ajuste de código resolve.

**Ação — depende de você:** exportar `cookies.txt` (formato Netscape) de uma sessão logada do YouTube
e colocar na VM. A flag `--cookies` e a env `YOUTUBE_COOKIES_FILE` já existem e funcionam
(`downloader.py:59-64`); falta só o arquivo.

**Cuidados:**
- Cookies do YouTube são credencial de sessão — arquivo `600`, dono `mediaops`, fora do repositório.
- Eles expiram. Sem tratamento, a expiração volta como o mesmo erro genérico — o que torna a
  Fase 2 pré-requisito prático desta.
- Alternativa sem credencial: proxy residencial. Mais caro e mais frágil.

**Esforço:** ~1h de código (validar/avisar expiração) + ação sua · **Risco:** operacional

---

## Fase 5 — 🔓 Desbloquear o Drive

**Bloqueio:** `mcp-google-drive@tes-fu.iam.gserviceaccount.com` tem `storageQuota.limit = 0`.
Erro 403 `storageQuotaExceeded`. Testado: subir para pasta sua compartilhada com a SA **não resolve**
(a cota é cobrada de quem sobe, não do dono da pasta). Não há Shared Drive disponível
(`drives().list()` vazio) e a conta é gmail.com, então delegação domain-wide não é opção.
**Nenhum upload por essa service account vai funcionar.** Os flags `supportsAllDrives` adicionados
recentemente ao `gdrive_uploader.py` não mudam isso.

Duas saídas — escolha sua:

**Opção A — reusar o rclone da produção (recomendada).**
O pipeline de cortes já sobe pro Drive por rclone nesta mesma VM, com credencial funcionando.
Reaproveitar elimina um segundo caminho de autenticação para manter. Substituir
`gdrive_uploader.py` por uma chamada ao remote existente.
*Pendência:* a `rclone.conf` em `~/.config/rclone/` está como `root:root 600` — a mesma regressão
de identidade descrita em `pipeline-cortes-identidade-mediaops`. Precisa voltar para `mediaops`
antes de funcionar.

**Opção B — OAuth de usuário.**
Fluxo de app instalado, uma autorização manual, refresh token guardado. Os arquivos passam a ser
seus de verdade (aparecem no seu Drive, contam na sua cota). Mais trabalho inicial, independente
do rclone.

**Esforço:** A ≈ 2h · B ≈ 4h · **Risco:** baixo em ambas

---

## Fase 6 — Conectar análise e corte

**Defeito de produto:** `--analyze` devolve 5 sugestões com timestamp e o usuário precisa rodar o
comando de novo, à mão, para cada uma. As duas metades do projeto não se falam.

**Correção:** flag `--auto-clips N` que roda a análise e renderiza os N melhores cortes direto,
nomeando a saída pelo rank e pelo score. Com a Fase 3 aplicada, 5 cortes saem em ~90 s em vez de ~17 min.

**Esforço:** ~3h · **Risco:** baixo · **Depende de:** Fases 3 e 4

---

## Fase 7 — Hardening do dashboard

**Arquivo:** `src/youtube_clipper/web_dashboard.py:864`

- Bind em `0.0.0.0` sem autenticação nenhuma. Numa VM do GCP a exposição depende só do firewall.
  Passar o default para `127.0.0.1` e exigir `--host 0.0.0.0` explícito para abrir.
- `/api/generate-clip` aceita URL arbitrária — quem alcança a porta usa a sua GPU e a sua banda.
- O path traversal do `/api/download/` está **bem defendido**, mas `Path.cwd()` está na allowlist:
  qualquer arquivo do diretório atual é servido pelo nome. Restringir a um diretório de saída dedicado.

**Esforço:** ~2h · **Risco:** baixo

---

## Sequência sugerida

```
Fase 0 (baseline)
   ├── Fase 1  🔴 corte duplo          ~2h   independente
   ├── Fase 2  🟡 erros visíveis       ~2h   independente
   └── Fase 3  ⚡ performance 11x      ~3h   independente
              │
     Fase 4 (cookies — decisão sua) ──┐
     Fase 5 (Drive — decisão sua)  ───┤
                                      └── Fase 6 (auto-clips)
     Fase 7 (dashboard) — a qualquer momento
```

**Bloco imediato:** Fases 0-3, ~8h, sem nenhuma dependência externa.
Corrige o bug que corrompe dados, torna os erros legíveis e derruba o tempo de render de 3m27s
para menos de 30 s.

**Portão de validação final:** com cookies e Drive resolvidos, rodar o vídeo original
(`6_By00hRl-c`) ponta a ponta — análise → corte automático → 9:16 → upload — e conferir o
arquivo no Drive. Só aí o pipeline está provado de verdade.
