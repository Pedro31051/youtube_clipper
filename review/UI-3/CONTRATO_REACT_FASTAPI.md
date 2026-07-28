# Contrato React + FastAPI — UI-3

## Entrada principal

O painel React compilado em `web/dist/` é servido pela aplicação FastAPI:

```bash
.venv/bin/python -m youtube_clipper.api
```

A aplicação vincula `127.0.0.1:8080` por padrão. O desenvolvimento usa Vite em
`127.0.0.1:5173`, com proxy para `/api` e `/openapi.json`.

## API versionada

Rotas da fundação:

- `GET /api/v1/health`;
- `GET|POST /api/v1/projects`;
- `GET /api/v1/projects/{project_id}`;
- `GET /api/v1/projects/{project_id}/clips`;
- `GET|PATCH /api/v1/clips/{clip_id}`;
- `GET /api/v1/jobs`;
- `GET /api/v1/jobs/{job_id}`;
- `POST /api/v1/clips/{clip_id}/preview-jobs`;
- `GET /api/v1/jobs/{job_id}/events`;
- `GET /api/v1/assets/{asset_id}?v={version}`.

As rotas usam o mesmo `ProjectStore` SQLite e os mesmos assets imutáveis da
UI-1/UI-2. Erros de validação, conflito e ausência continuam retornando JSON
acionável com HTTP 400, 409 e 404.

## Worker e eventos

O POST de preview:

1. persiste um job `queued`;
2. devolve HTTP 202 sem esperar o FFmpeg;
3. executa a mídia em um `ThreadPoolExecutor` local;
4. verifica se `plan_version` não mudou durante o render;
5. registra preview/poster e conclui o job.

O broker publica:

- `job_queued`;
- `stage_start`;
- `progress`;
- `stage_completed`;
- `job_failed`.

O SSE usa `id`, `event` e `data`, aceita `Last-Event-ID`, envia keep-alive e
encerra após estado terminal.

## OpenAPI e TypeScript

`npm run build` executa primeiro:

```text
FastAPI app.openapi()
  → web/openapi.json
  → openapi-typescript
  → web/src/api/schema.d.ts
  → TypeScript/Vite
```

O cliente React importa `ProjectSummary`, `ProjectsResponse` e `JobsResponse`
do arquivo gerado. Mudanças incompatíveis no backend quebram o build antes de
chegar ao navegador.

## Shell

O shell contém:

- sidebar de navegação;
- topbar com conexão;
- área principal com projetos persistidos;
- estado vazio e skeleton;
- erro persistente com retry explícito;
- atividade operacional alimentada por SSE;
- inspetor placeholder, sem antecipar controles da UI-5.

Os componentes React ficam em `web/src/`. As páginas legadas foram movidas para
`src/youtube_clipper/templates/`, eliminando HTML/CSS/JavaScript embutido em
strings Python.
