# Limitações e Fronteiras — T1

1. **Margem de disco**: a run golden mediu exatamente `20 GiB`, o mínimo
   permitido. Recriar caches grandes ou imagens Docker pode fazer uma execução
   futura reprovar novamente.
2. **Dependência de hardware**: o contrato T1 exige `nvidia-smi` funcional; a
   portabilidade sem GPU é tratada posteriormente, mas não altera este critério.
3. **Dependência de fontes do host**: a medição requer ao menos uma família
   Inter, Roboto ou Noto registrada no fontconfig.
4. **Histórico preservado**: `run_t1_20260727T122944Z` permanece bloqueada em
   6/8 e com falha temporal. Ela não deve ser confundida com a run golden
   `run_t1_20260727T193302Z`.
5. **Caches removidos**: caches e temporários usados para recuperar espaço são
   recriáveis, mas futuros testes podem precisar baixar novamente modelos e
   imagens.
