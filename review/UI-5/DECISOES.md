# Decisões — UI-5

## Plano único e concorrência otimista

Decisão: autosave envia o plano completo com `expected_plan_version`.

Alternativa descartada: salvar campos isolados sem versão.

Motivo: evita sobrescrever ajustes feitos por outra janela e garante que
preview e render consumam a mesma versão.

## Histórico local com Zustand

Decisão: snapshots de undo/redo ficam no navegador e são zerados ao mudar de
`clip_id`.

Alternativa descartada: persistir cada passo do histórico no SQLite.

Motivo: resposta imediata, isolamento simples e ausência de crescimento
indefinido do banco.

## Waveform sobre o preview

Decisão: wavesurfer.js carrega o MP4 leve versionado e o plugin Regions fornece
os handles.

Alternativa descartada: carregar a mídia final ou desenhar uma onda fictícia.

Motivo: a forma de onda deriva do asset real sem aumentar o tráfego.

## Player nativo nesta fase

Decisão: manter o elemento `video` acessível já usado pelo painel.

Alternativa descartada: forçar `@vidstack/react` 0.6.15.

Motivo: a versão publicada declara peer dependency de React 18, enquanto o
projeto usa React 19. Forçar a instalação criaria uma árvore incompatível.

## Fila separada para render final

Decisão: renders finais usam executor próprio e exigem preview atual.

Alternativa descartada: disputar as mesmas threads dos previews interativos.

Motivo: preservar a responsividade da edição e impedir artefato final baseado
em plano desatualizado.
