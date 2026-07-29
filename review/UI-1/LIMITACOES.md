# Limitações — Fase UI-1

## 1. Servidor HTTP legado

A API v1 ainda é servida por `ThreadingHTTPServer`. FastAPI, OpenAPI e geração
de cliente TypeScript pertencem à UI-3.

## 2. Jobs de análise ainda são síncronos

`POST /api/v1/projects/{project_id}/analysis-jobs` cria e persiste um `job_id`,
mas executa a análise dentro da mesma requisição. Fila, worker, cancelamento,
retry e SSE ainda não foram implementados.

## 3. Preview e poster ainda não são produzidos

O domínio já suporta assets versionados e invalidação seletiva, porém a geração
física de preview/poster, streaming Range e cache imutável pertencem à UI-2.

## 4. Render rápido usa um caminho canônico reduzido

O painel não chama mais `youtube_clipper.pipeline`. O novo limite em
`cortes.dashboard_pipeline` executa ingestão do intervalo, normalização de áudio,
render editorial, composição de assets e publicação auditada. Como o candidato
já foi escolhido pela análise do painel, esse caminho não repete transcrição,
detecção de cenas ou seleção semântica durante o render.

Esse fluxo ainda precisa ser consolidado com `cortes.pipeline` por um plano de
edição compartilhado, evitando que existam dois orquestradores dentro do pacote
canônico.

## 5. Frontend ainda usa rank em IDs DOM

Cada card agora carrega `clip_id`, `project_id` e `analysis_id` em seu dataset e
propaga esses IDs ao backend. Os IDs dos elementos HTML continuam baseados em
`rank` para compatibilidade com o painel atual. A remoção completa ocorre com os
componentes React da UI-3/UI-4.

## 6. Sem migrações incrementais além do schema inicial

O banco possui `PRAGMA user_version = 1`, mas ainda não existe runner de
migrações entre versões futuras. Antes de alterar o schema para a UI-2, deve ser
adicionado um mecanismo transacional de migração.

## 7. Arquivos invalidados não são apagados

Assets antigos permanecem fisicamente no workspace e são marcados como
inválidos no banco/manifesto. Isso preserva auditoria, mas exigirá política
explícita de retenção e coleta de lixo.
