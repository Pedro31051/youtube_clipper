# Runbook de observabilidade

## Artefatos de um run

- `events.jsonl`: timeline canônica append-only.
- `commands.log`: índice legível de subprocessos.
- `commands/*.stdout.log` e `commands/*.stderr.log`: streams completos redigidos.
- `seal.json`: estado final, quantidade de eventos e hash da timeline.

## Lifecycle

O fluxo normal é `planned → started → succeeded`. Falhas terminam em `failed`;
ramos não escolhidos e dependências bloqueadas terminam em `skipped`. Retentativas
emitem `retrying` entre o início e o terminal. Todo terminal contém `next.action`
ou um motivo explícito de encerramento.

## Investigação

1. Execute `python -m cortes.verify <runs/run_id>` apontando a saída para fora
   do run quando precisar persistir `verify_result.json`.
2. Procure o primeiro evento `failed`, depois siga `trace.parent_span_id` para
   localizar o limite de negócio que originou a falha.
3. Consulte `error.stderr_path` e `error.traceback_path`, quando presentes.
4. Confira ações `started` sem terminal e a presença de `seal.json`. Ausência de
   seal indica interrupção ou falha do processo antes da finalização.
5. Nunca edite o run. Corrija o código/configuração e crie uma nova execução.

## Schema 2.0

Além dos campos históricos 1.0, cada evento possui `event_id`, `request_id`,
`component`, `action`, `status`, `decision`, `next`, `input` e `execution`.
Erros são objetos estruturados com categoria, tipo, mensagem, causas, ponto da
falha, retryability, exit code/sinal, remediação e caminhos de evidência.

Valores sensíveis são substituídos por `[REDACTED]` antes de persistir. Não
inclua credenciais em nomes de arquivo ou identificadores de ação.
