# Decisões — gates finais do painel

## Asset segue a versão do plano

Decisão: persistir a versão do preview/render a partir do `EditPlan` esperado
pelo worker.

Alternativa descartada: inferir a versão pelo número de assets já gravados.

Motivo: um resultado obsoleto pode ser rejeitado antes de registrar asset; a
sequência de arquivos não representa necessariamente a sequência de planos.

## Fallback NVENC limitado

Decisão: após uma falha física do `h264_nvenc`, preservar o diagnóstico e
executar exatamente uma tentativa com `libx264`.

Alternativa descartada: repetir NVENC ou alternar encoders indefinidamente.

Motivo: o job precisa terminar de forma determinística e explicar por que
mudou de hardware.

## Evidência de navegador fora do Git

Decisão: versionar screenshots pequenos e guardar traces completos no artifact
`playwright-evidence` da CI por 14 dias.

Alternativa descartada: adicionar todos os traces binários ao histórico Git.

Motivo: traces são essenciais para inspeção da execução, mas multiplicam o
tamanho do PR em cada navegador e viewport.

## Runs do servidor Playwright

Decisão: preservar os runs auditáveis criados pelo servidor com CWD `web/`,
mas ignorar `web/runs/` no Git.

Alternativa descartada: apagar os runs após o teste ou versioná-los junto com
as evidências visuais.

Motivo: a primeira opção viola a imutabilidade da auditoria; a segunda mistura
logs e mídia transitórios ao diff do painel.

## Relatório gerado

Decisão: produzir `report.json` e `report.md` exclusivamente pelo script
`scripts/generate_final_panel_report.py`.

Alternativa descartada: atualizar números e resultados manualmente.

Motivo: resultados de teste, hashes e benchmark devem permanecer
reproduzíveis e vinculados às entradas observadas.
