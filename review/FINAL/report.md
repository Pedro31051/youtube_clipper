# Relatório gerado — gates finais do painel

Gerado por `scripts/generate_final_panel_report.py`. Este documento registra
evidências; o veredito funcional e visual permanece com o revisor externo.

## Identidade da entrega

- base de comparação: `581fb30`
- commit observado: `119ac9c8384006479c32e6d162ba60d957fc1c2a`
- branch: `codex/finalize-panel`
- arquivos alterados desde a base: 117
- nomes sensíveis encontrados no diff: 0

## Testes observados

- Python: 830 testes, 0 falhas,
  0 erros, 0 ignorados,
  610.629 s
- Playwright: 24 testes, 0 falhas,
  0 erros, 5 ignorados,
  87.058 s
- repetição física análise→preview: 50 projetos, um preview válido por
  `clip_id` e `plan_version`
- navegadores/viewports: Chromium 1440×900, 1280×800, 768×1024 e 390×844;
  Firefox 1280×800; WebKit 1280×800

## Benchmark do encoder

- encoder físico: `h264_nvenc`
- razão mediana na base: 0.7414
- razão mediana atual: 0.7394
- variação atual/base: -0.270%
- repetições por checkout: 7
- hardware: `Linux-6.17.0-1021-gcp-x86_64-with-glibc2.39`

## Evidências visuais

- screenshots com hash: 24
- traces: produzidos para todos os projetos e preservados no artifact
  `playwright-evidence` da CI por 14 dias
- vídeo: `retain-on-failure`

## Gates que exigem veredito externo

- aprovação funcional e visual das telas;
- homologação contra uma conta Google Drive real;
- decisão de retirar o PR de draft.
