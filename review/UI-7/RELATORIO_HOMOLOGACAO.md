# Relatório de homologação — UI-7

## Escopo exercitado

- persistência de eventos após reabertura do SQLite;
- download MP4 com HTTP Range;
- upload assíncrono consumindo arquivo físico;
- erro de cota do Drive com causa e ação;
- retry com nova identidade e tentativa;
- cancelamento de render ativo sem asset órfão;
- navegação Chromium pela Tela 5;
- abertura do diálogo, download de mídia e relatório JSON.

## Evidências Playwright

- `runs/playwright/ui7-observa-jobs-e-baixa-mídia-e-relatório-físicos-chromium/jobs-exportacoes.png`
- `runs/playwright/ui7-observa-jobs-e-baixa-mídia-e-relatório-físicos-chromium/dialog-exportacao.png`
- `runs/playwright/ui7-observa-jobs-e-baixa-mídia-e-relatório-físicos-chromium/video.webm`

O teste usa `source_three_candidates.mp4`, arquivo físico versionado com
intervalos visuais conhecidos. Nenhum mock de FFmpeg, ffprobe ou player é usado
no cancelamento e na prova de mídia.

## Performance local

O Playwright falha se a primeira tela útil ultrapassar 2 segundos ou se a
mudança React para Jobs e exportações ultrapassar 100 ms no relógio do
navegador.

## Resultado

- regressão Python: `820 passed, 2 deselected`;
- contratos e operações UI-7: incluídos na regressão, com mídia física;
- componentes React: `11 passed`;
- build Vite/TypeScript/OpenAPI: aprovado;
- Playwright Chromium: `1 passed`;
- auditoria de dependências: `0 vulnerabilities`.

Os dois testes removidos da regressão são benchmarks locais de timing/NVENC
preexistentes. Os testes funcionais de FFmpeg e mídia permanecem ativos.

## Parecer

Este relatório não constitui aprovação da fase; reúne material para revisão
externa.
