# Decisões — UI-4

## Análise e preview como jobs independentes

Decisão: a análise roda em um worker serial e, ao terminar, agenda um job de
preview por `clip_id` no worker já existente.

Alternativa descartada: manter a requisição HTTP aberta durante análise e
FFmpeg.

Motivo: o painel precisa continuar responsivo, mostrar progresso real e
recuperar estado persistido após recarga.

## Revisão atômica e limitada

Decisão: aprovação e rejeição compartilham um endpoint transacional limitado a
20 cortes de um único projeto.

Alternativa descartada: disparar uma sequência de `PATCH` no navegador.

Motivo: uma falha no meio da sequência não pode deixar um lote parcialmente
decidido.

## Player sob demanda

Decisão: o card começa com poster e a interface monta apenas o vídeo atualmente
reproduzido.

Alternativa descartada: manter um elemento de vídeo ativo em todos os cards.

Motivo: reduz decodificação simultânea e garante que trocar de card pause e
desmonte o player anterior.

## Limite entre revisão e editor

Decisão: “Abrir editor” seleciona o corte e expõe identidade, intervalo e versão
do plano no inspetor. Waveform, handles, ajustes e autosave permanecem na UI-5.

Alternativa descartada: introduzir edição parcial nesta fase.

Motivo: preservar o princípio “aprovação primeiro, edição profunda depois”
confirmado no plano e no NotebookLM.

## Execução local

Decisão: manter a aplicação integrada ao FastAPI local, SQLite, filesystem e
workers de FFmpeg.

Alternativa descartada: publicar somente o frontend estático nesta fase.

Motivo: sem o backend e os assets locais, o fluxo central da UI-4 seria apenas
uma demonstração sem funcionalidade real. Hospedagem e operação pertencem à
etapa posterior prevista no plano.
