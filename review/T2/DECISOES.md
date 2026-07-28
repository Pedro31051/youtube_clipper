# Decisões técnicas — T2

## Whisper executado como processo auditado

O faster-whisper é invocado por `python -m cortes.whisper_worker` através de
`cortes.log.run_cmd()`. Isso registra o comando e impede processos externos de
escaparem do gateway.

Alternativa descartada: chamada direta da biblioteca dentro do estágio. Embora
mais simples, ela não satisfazia o contrato de processo auditado.

## CUDA sem fallback silencioso

Quando `device=cuda`, falhas CUDA encerram o estágio. CPU continua disponível
somente quando solicitada explicitamente. O runtime Linux x86_64 recebe cuBLAS
e cuDNN via dependências Python.

Alternativa descartada: fallback automático para CPU. Ele produzia saída, mas
falsificava a prova de execução GPU.

## Eventos timestampados na conclusão

Eventos auditados aninhados recebem timestamp no momento de append. Assim, a
ordem temporal acompanha a sequência física de `events.jsonl`.

Alternativa descartada: timestamp de entrada da função. Funções filhas eram
gravadas antes da função pai, gerando timestamps regressivos.

## Evidências estritamente relativas

Somente arquivos dentro de `runs/<run_id>` podem ser declarados como evidência.
Callbacks de compatibilidade podem operar externamente, mas seus caminhos não
entram no log do run.

Alternativa descartada: caminhos relativos ao repositório ou absolutos. Ambos
quebram portabilidade e isolamento zero-trust.

## `clip_id` determinístico

O identificador é `clip_` seguido dos primeiros 12 hexadecimais do SHA-256 de
`selection.json`. O render final fica em
`artifacts/<clip_id>/short.mp4`. Um symlink em `artifacts/render/` preserva
descoberta por consumidores legados sem duplicar o MP4.

## Relatórios imutáveis

`report.md` representa o relatório inicial e `report_verified.md` representa o
relatório posterior ao zero-trust. Arquivos existentes não são sobrescritos.

Alternativa descartada: atualizar `report.md` in-place. Isso invalidava o hash
já registrado no log.

## Fonte golden original

O golden usa texto original, `testsrc` e síntese local `flite`, dedicado a CC0.
Não há download nem conteúdo audiovisual de terceiro.

