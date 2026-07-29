# Baseline do painel — UI-0

Data do levantamento: 2026-07-28

Este documento congela o estado observado antes de mudanças visuais ou da
migração para React/FastAPI. Ele não declara a fase concluída; registra a base
que as fases UI-1 a UI-7 terão de superar.

## Superfícies atuais

O painel é composto por duas páginas HTML montadas como strings dentro de
`src/youtube_clipper/web_dashboard.py`:

- `/` e `/index.html`: fluxo rápido para URL do YouTube;
- `/technical` e `/cortes`: formulário local para o pipeline auditado.

Ambas são servidas por `ThreadingHTTPServer` e
`ClipperDashboardHandler`. Não existe frontend empacotado, roteador cliente,
banco de projetos ou fila persistente de jobs.

## Fluxo rápido atual

```text
URL do YouTube
  → POST /api/analyze
  → extract_transcript_and_analyze
  → cards identificados por rank
  → iframe youtube-nocookie com start/end
  → confirmação manual
  → POST /api/generate-clip
  → youtube_clipper.pipeline.run_pipeline
  → MP4 em output/
  → GET /api/download/<filename>
  → upload opcional ao Drive
```

O card possui iframe próprio e recebe intervalo próprio. Depois do render, o
MP4 retornado é associado ao card acionado. Porém, antes do render não existe
`preview_id`, `asset_id`, manifesto ou MP4 de preview versionado. A identidade
continua baseada principalmente em `rank`, URL e intervalo.

## Fluxo técnico atual

```text
arquivo local
  → POST /api/cortes/run
  → cortes.pipeline.run_full_pipeline
  → verify_run
  → cópia do render para media_workspace/
  → recibo e download
```

Esta superfície expõe opções técnicas do pipeline auditado, mas permanece
separada do fluxo principal e não oferece revisão de múltiplos candidatos.

## Fronteira arquitetural confirmada

Existem dois caminhos de execução ativos:

- o painel rápido chama `src/youtube_clipper/pipeline.py`;
- o painel técnico chama `src/cortes/pipeline.py`.

Essa duplicidade impede um contrato único entre análise, preview, edição e
render. A UI-1 deverá introduzir IDs estáveis e adaptar o painel para usar
`cortes.pipeline` como fonte canônica sem remover os endpoints antigos de uma
vez.

## Persistência e identidade

Estado atual:

- sem `project_id`, `source_id`, `analysis_id`, `preview_id`, `render_id` ou
  `job_id`;
- `request_id` correlaciona operações e runs, mas não representa entidade de
  produto;
- assets de editor possuem IDs aleatórios, porém não são ligados a um
  `clip_id`;
- resultados vivem em filesystem; o registro em memória de requests se perde
  ao reiniciar o servidor;
- não há SQLite nem migração de schema.

## Progresso e erros

- `GET /api/status/<request_id>` agrega eventos auditados das runs associadas;
- o browser consulta status por polling;
- render e análise ainda ocupam a requisição HTTP;
- não há fila persistente, cancelamento nem retry de job pelo painel;
- a auditoria funcional anterior encontrou estado agregado `failed` mesmo
  quando a análise recuperou candidatos utilizáveis.

## Evidência visual

As capturas novas desta fase devem ser gravadas em:

- `review/UI-0/screenshots/painel-principal.png`;
- `review/UI-0/screenshots/painel-tecnico.png`.

As dimensões e o conteúdo dessas capturas são registrados pelo navegador real,
sem alteração visual prévia.

## Caso reproduzível de identidade

`tests/fixtures/panel_preview_identity/source_three_candidates.mp4` contém três
intervalos inequívocos:

- vermelho/uma barra/440 Hz, 0–3 s;
- verde/duas barras/660 Hz, 3–6 s;
- azul/três barras/880 Hz, 6–9 s.

O teste físico extrai um frame real de cada intervalo com FFmpeg e exige três
hashes diferentes. Essa fixture será o gate de UI-2 para provar correspondência
`clip_id → preview_id → asset`.

## Métricas congeladas

| Métrica | Baseline |
|---|---|
| Implementação visual | HTML/CSS/JS dentro de uma string Python |
| Servidor | `ThreadingHTTPServer` |
| Pipelines chamados pelo painel | 2 |
| Persistência de entidades | nenhuma |
| Identidade principal dos cards | `rank` |
| Preview intermediário versionado | inexistente |
| Progresso | polling de eventos por `request_id` |
| Fila persistente | inexistente |
| Teste físico de três identidades | introduzido na UI-0 |

## Gate para iniciar mudanças visuais

Mudança visual só deve começar depois que:

1. a fixture sintética puder ser regenerada;
2. o teste físico provar três intervalos distintos;
3. as duas páginas atuais tiverem screenshots;
4. a matriz função → API → componente → teste estiver versionada;
5. decisões e limitações da fase estiverem registradas.
