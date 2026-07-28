# Limitações — Fase UI-0

## 1. A UI-0 não corrige o painel

Esta fase cria baseline, matriz e fixture. Ela não introduz IDs persistentes,
preview MP4, React, FastAPI, SQLite ou fila de jobs.

## 2. Preview atual depende do YouTube

Antes do render, o card usa `youtube-nocookie.com` com `start` e `end`. Isso
permite conferir o intervalo, mas não prova a identidade de um asset produzido
pelo sistema e depende de rede, disponibilidade e política do YouTube.

## 3. Dois pipelines permanecem ativos

O fluxo rápido continua em `youtube_clipper.pipeline`; o fluxo técnico usa
`cortes.pipeline`. A consolidação pertence à UI-1/Fase 0 arquitetural.

## 4. Estado não sobrevive ao reinício

O registro de `request_id → run_id` fica em memória. Reiniciar o servidor perde
a capacidade de consultar essas operações pela API, embora as runs permaneçam
no filesystem.

## 5. Operações longas ocupam requisições

Análise, render e upload ainda são iniciados dentro do handler HTTP. O polling
expõe eventos, mas não equivale a uma fila persistente com cancelamento,
retomada e retry.

## 6. Defeitos anteriores ainda abertos

O baseline incorpora os achados da auditoria funcional de 2026-07-28:

- estado agregado pode marcar falha após recuperação utilizável;
- download conjunto de legendas pode transformar fallback válido em falha;
- legendas automáticas progressivas podem duplicar transcrição;
- execução direta do módulo ignora `--port`;
- primeira consulta de status pode retornar 404;
- alguns métodos inválidos ainda retornam HTML em vez de JSON.

## 7. A fixture não valida ainda o vínculo card → asset

Ela prova somente que existem três intervalos físicos inequívocos. O vínculo
persistente `clip_id → preview_id → asset_id`, a invalidação seletiva e o
streaming HTTP Range são entregas da UI-1/UI-2.
