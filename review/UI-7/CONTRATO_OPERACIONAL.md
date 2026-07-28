# Contrato operacional — UI-7

## Jobs persistentes

Cada job possui identidade imutável, tentativa, vínculo opcional com a
tentativa anterior, payload mínimo para retry e eventos ordenados no SQLite.
Os eventos alimentam SSE e continuam disponíveis depois de reiniciar a API.

Estados terminais são `completed`, `failed` e `cancelled`. Retry aceita somente
`failed` ou `cancelled` e cria outro `job_id`, preservando `parent_job_id` e
incrementando `attempt`.

## Cancelamento

Preview e render recebem um sinal cooperativo que chega ao limite canônico de
subprocessos. O grupo de processos FFmpeg recebe `SIGTERM` e, se necessário,
`SIGKILL`; artefatos parciais são removidos e não entram na tabela `assets`.

Análise e Drive verificam o sinal antes de persistir resultados. A interface
oferece cancelamento somente enquanto o job está em fila ou execução.

## Entrega

Download e Drive exigem um asset `render` válido e um clipe no estado
`rendered` ou `exported`.

- download usa streaming com HTTP Range e `Content-Disposition`;
- Drive cria job assíncrono de concorrência unitária;
- relatório JSON reúne job, eventos, clipe e identidades de assets;
- falhas armazenam detalhe técnico, causa legível e próxima ação.

## Evidências

Os gates combinam testes físicos de FFmpeg/assets, integração FastAPI/SQLite,
componentes React e Playwright Chromium com download real, screenshot e vídeo.
Essas evidências são entregues ao revisor externo; o agente não aprova a fase.
