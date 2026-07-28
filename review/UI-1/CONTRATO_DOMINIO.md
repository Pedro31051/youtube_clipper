# Contrato de domínio persistente — UI-1

## Identificadores

| Entidade | Prefixo |
|---|---|
| Project | `prj_` |
| Source | `src_` |
| Analysis | `anl_` |
| Clip | `clp_` |
| Job | `job_` |
| Asset | `ast_` |
| Render | `rnd_` |

Todos os IDs usam 32 caracteres hexadecimais aleatórios após o prefixo e são
validados antes de consultas.

## Relações

```text
Project
  ├── Source
  ├── Analysis
  │     └── Clip
  │           ├── manifest.json
  │           ├── Asset v1..n
  │           └── Render
  └── Job
```

Um asset pertence obrigatoriamente a um único clipe. Um render não pode apontar
para um asset de outro clipe.

## API disponível nesta etapa

```text
POST  /api/v1/projects
GET   /api/v1/projects
GET   /api/v1/projects/{project_id}

POST  /api/v1/projects/{project_id}/analysis-jobs
GET   /api/v1/projects/{project_id}/clips

GET   /api/v1/clips/{clip_id}
PATCH /api/v1/clips/{clip_id}

GET   /api/v1/jobs/{job_id}
```

As rotas antigas continuam disponíveis. `/api/analyze` agora cria ou usa um
projeto persistente e devolve os IDs. `/api/generate-clip` registra o MP4 como
asset/render quando recebe `clip_id`.

## Invariantes verificadas

- recarregar `ProjectStore` preserva projetos e IDs;
- dois clipes não compartilham `asset_id` nem URL;
- editar a timeline incrementa `plan_version`;
- editar um clipe invalida somente seus previews/posters;
- assets invalidados continuam versionados e auditáveis;
- caminhos físicos internos não aparecem na API nem no manifesto;
- um intervalo de render diferente do `EditPlan` retorna conflito;
- transições impossíveis retornam HTTP 409.
