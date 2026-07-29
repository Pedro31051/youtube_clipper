# Limitações — UI-7

- A autenticação real do Google Drive depende de OAuth de usuário ou Shared
  Drive com cota. O teste usa arquivo físico e adaptador injetado; homologar
  contra uma conta real exige credenciais do operador.
- Cancelar um upload do Drive impede persistência local do resultado, mas a
  API do cliente atual não oferece handle para desfazer bytes já aceitos.
- O cancelamento de análise é cooperativo no retorno do analisador. FFmpeg de
  preview/render é terminado fisicamente; bibliotecas externas sem handle
  podem terminar antes de o resultado ser descartado.
- Tempo de render depende de encoder, resolução e hardware. A execução registra
  duração, frames, tempo real e razão processamento/duração, sem impor um
  limite universal.
- Traces Playwright completos ficam por 14 dias no artifact da CI, não
  permanentemente no Git. Vídeo é retido somente em falha.
- A aplicação requer SQLite, filesystem, FFmpeg e credenciais locais; não há
  configuração de hospedagem estática.
- Aprovação visual, de Drive e funcional continua pertencendo ao revisor
  externo; esta entrega apenas produz evidências verificáveis.
