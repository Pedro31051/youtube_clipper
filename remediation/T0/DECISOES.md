# Decisões da remediação T0

- O offset absoluto é consumido apenas no download; o processamento do segmento
  começa em `t=0`.
- Toda saída FFmpeg é validada por tamanho, stream de vídeo e duração via
  ffprobe.
- `verify_run` é read-only por padrão; saída persistente exige caminho explícito
  fora do run verificado.
- Evidências são resolvidas relativamente ao run fornecido, com compatibilidade
  para o sufixo `artifacts/` dos pacotes legados.
- Dashboard permanece anônimo somente em loopback. Exposição remota exige bearer
  token e usa diretório dedicado para download e upload.
- A alternativa de reescrever o histórico da `main` foi descartada porque
  destruiria rastreabilidade; CI passa a impedir regressões futuras.
