# Decisões — UI-7

## Um histórico para API e SSE

Decisão: persistir eventos ordenados em `job_events` e usar a mesma sequência
como fonte da lista e do stream.

Alternativa descartada: manter o histórico somente na memória do processo.

Motivo: recarregar ou reiniciar a API não pode apagar progresso, falhas e
orientações operacionais.

## Retry cria nova identidade

Decisão: retry cria outro job ligado por `parent_job_id`.

Alternativa descartada: zerar e reutilizar o registro que falhou.

Motivo: preserva auditoria, contagem de tentativas e evidência da falha
original.

## Cancelamento no limite de subprocesso

Decisão: propagar um evento de cancelamento até `run_cmd` e encerrar o grupo do
FFmpeg.

Alternativa descartada: mudar apenas o status no SQLite enquanto o processo
continua consumindo CPU ou GPU.

Motivo: o estado mostrado deve corresponder à execução física.

## Exportação condicionada a asset

Decisão: resolver novamente o asset final válido no backend para download e
Drive.

Alternativa descartada: confiar apenas no estado ou habilitação do botão
React.

Motivo: evita exportação impossível, arquivo inválido ou caminho forjado.

## Aplicação permanece local

Decisão: manter FastAPI, SQLite, filesystem, FFmpeg e credenciais locais.

Alternativa descartada: publicar esta fase em hospedagem estática.

Motivo: o worker de mídia e os arquivos físicos são parte do produto e não
cabem em uma implantação estática sem uma migração operacional fora do escopo.
