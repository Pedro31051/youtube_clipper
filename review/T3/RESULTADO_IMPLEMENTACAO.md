# Resultado da Implementação Corretiva T3

Data: 2026-07-27

## Correções entregues

1. Narração deixou de ser um booleano declarativo. A renderização exige um
   arquivo físico, mede duração mínima de 8 s, copia o arquivo para o run,
   registra hash/tamanho e o mistura com `amix`.
2. A mixagem passa por medição e aplicação `loudnorm` em duas etapas sem
   adicionar uma segunda passagem de codificação de vídeo.
3. O verificador comprova narração, overlay, requisitos editoriais,
   singularidade do variant e recomposição do `clip_id`.
4. `template_variant` é validado e rejeitado se aparecer nos cinco renders
   anteriores.
5. O contrato genérico `run_render(callback, **kwargs)` voltou a encaminhar
   todos os argumentos.
6. Os testes NVENC usam o limite real de 5 s; o fallback CPU permanece um
   caminho funcional sem produzir falsa prova de performance GPU. Falhas no
   encoder durante a conversão real disparam retry automático com `libx264`.
7. A fixture cara de mutação passou a ser criada uma vez por módulo.
8. Os cenários empíricos usam CPU explicitamente no CI hospedado e preservam
   a execução CUDA dos mesmos testes em workflow GPU dedicado.
9. A T1 corrigida foi integrada no merge commit `6c982a9` e a branch T3 foi
   reaplicada diretamente sobre essa `main`.

## Evidência final

- Golden: `runs/run_t3_golden_v5`
- Artefato: `artifacts/clip_f6be54249092/short.mp4`
- Zero-trust: 28/28 checks
- Resolução/FPS: 1080×1920, 30 FPS constante
- Duração: 26,43 s
- Áudio: uma faixa, −15,30 LUFS
- Narração: 10,0 s, hash e tamanho conferidos, `amix` presente no comando
- Variant: `variant_t3_analytical_v5`
- Histórico: v4, v3 e v1, sem duplicação causada por symlinks
- Testes completos: 654 aprovados em 329,19 s no commit `06b4a98`
- Testes focais: 32 aprovados
