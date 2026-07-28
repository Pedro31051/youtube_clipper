# Limitações — UI-7

- A autenticação real do Google Drive depende de OAuth de usuário ou Shared
  Drive com cota. O teste de orquestração copia mídia física por um adaptador
  injetado; a homologação contra uma conta real requer credenciais do operador.
- Cancelar um upload do Drive impede persistência local do resultado, mas a API
  do cliente atual não oferece handle para desfazer bytes que o Google já tenha
  aceitado.
- O cancelamento de análise é cooperativo no retorno do analisador. Processos
  FFmpeg de preview/render são terminados fisicamente; uma transcrição externa
  já dentro de biblioteca de terceiros pode terminar antes de ser descartada.
- O orçamento automatizado mede primeira tela abaixo de 2 s e atualização
  React abaixo de 100 ms no ambiente local. Tempo de render depende do encoder,
  resolução e hardware e permanece registrado por job, sem limite universal.
- O relatório Playwright cobre Tela 5, download, relatório, screenshot e vídeo
  usando mídia física. Ele não usa uma conta Drive real pela ausência de
  credenciais versionáveis.
- A aplicação não foi publicada via Sites: ela requer SQLite, filesystem,
  FFmpeg e credenciais locais e não possui `.openai/hosting.json`.
- Aprovação visual, de Drive e do fluxo completo continua pertencendo ao
  revisor externo; esta entrega apenas produz evidências verificáveis.
