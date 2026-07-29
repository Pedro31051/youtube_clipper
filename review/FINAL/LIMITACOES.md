# Limitações — gates finais do painel

- A aprovação funcional e visual continua dependendo de revisor externo; os
  artefatos desta fase não constituem veredito.
- A integração Google Drive exige credenciais e cota de uma conta do operador.
  A suíte comprova o contrato e o uso de arquivo físico, mas não autentica uma
  conta real.
- O benchmark representa o hardware registrado no relatório. Relações de tempo
  podem variar em outro driver, GPU, CPU ou carga concorrente.
- A falha NVENC é reproduzida ocultando o dispositivo CUDA para o subprocesso;
  falhas específicas de driver ou exaustão de sessão podem emitir diagnóstico
  diferente, embora usem a mesma rota de fallback.
- Traces Playwright completos ficam disponíveis por 14 dias no artifact da CI,
  não permanentemente no Git.
- O servidor Playwright ainda grava runs físicos sob `web/runs/` porque seu CWD
  é `web/`; eles são preservados localmente e ignorados pelo Git.
- O cancelamento de bibliotecas externas que não exponham um handle continua
  cooperativo. FFmpeg de preview/render é encerrado fisicamente.
