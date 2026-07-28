# Decisões — Fase UI-1

## 1. SQLite como fonte de identidade

- **Decisão:** persistir projetos, fontes, análises, clipes, jobs, assets e
  renders em SQLite com chaves prefixadas e estrangeiras.
- **Alternativa descartada:** reconstruir identidade a partir de `rank`, nome
  de arquivo ou posição do card.
- **Por quê:** esses valores mudam; os IDs persistidos sobrevivem a reload,
  reranqueamento e novas versões de assets.

## 2. Mídia no filesystem e metadados no banco

- **Decisão:** SQLite armazena metadados e relações; arquivos permanecem sob o
  workspace do projeto.
- **Alternativa descartada:** gravar MP4 e imagens como BLOBs.
- **Por quê:** arquivos grandes degradariam backup, streaming e concorrência do
  banco. O filesystem permite nomes imutáveis e HTTP Range na UI-2.

## 3. Assets imutáveis e versionados

- **Decisão:** o nome físico contém `asset_id` e versão; uma edição de timeline
  invalida poster/preview anteriores sem apagá-los.
- **Alternativa descartada:** sobrescrever `preview.mp4`.
- **Por quê:** elimina colisão de cache e mantém rastreabilidade. A próxima
  versão recebe outro ID, outro nome e `?v=<versão>`.

## 4. Manifesto atômico por clipe

- **Decisão:** cada clipe recebe `manifest.json`, escrito em arquivo temporário
  e publicado com `os.replace`.
- **Alternativa descartada:** um manifesto global reescrito após cada job.
- **Por quê:** reduz contenção, limita o impacto de falhas e mantém a relação
  `clip_id → plano → assets` legível fora do banco.

## 5. API versionada sem remoção imediata das rotas antigas

- **Decisão:** introduzir `/api/v1` e adaptar `/api/analyze` e
  `/api/generate-clip` para devolver/consumir IDs persistentes.
- **Alternativa descartada:** remover os endpoints antigos nesta fase.
- **Por quê:** o HTML atual e sua suíte continuam operacionais durante a
  migração para React/FastAPI.

## 6. Render rápido migrado para componentes canônicos

- **Decisão:** substituir a importação de `youtube_clipper.pipeline` por
  `cortes.dashboard_pipeline`, reutilizando ingestão, áudio, render e composição
  auditados.
- **Alternativa descartada:** manter um adaptador que apenas chamasse o pipeline
  antigo por baixo.
- **Por quê:** isso esconderia a duplicidade sem remover a dependência real.

## 7. Máquina de estados validada no domínio

- **Decisão:** rejeitar transições impossíveis, incluindo
  `proposed → exported`.
- **Alternativa descartada:** permitir que cada endpoint escreva qualquer
  string de status.
- **Por quê:** regras no domínio impedem que clientes diferentes corrompam o
  fluxo editorial.
