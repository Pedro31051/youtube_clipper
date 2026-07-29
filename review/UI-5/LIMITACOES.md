# Limitações — UI-5

- A análise atual não gera um asset ASS/VTT persistente por corte; opções de
  estilo e posição de legenda são salvas, mas a queima física fica bloqueada
  até esse asset existir.
- Narração externa ainda não possui endpoint de upload. O editor não aceita
  TTS apenas como metadado, pois o pipeline exige áudio físico válido.
- A variante de template é persistida, porém o compilador visual atual só
  materializa o overlay analítico; templates gráficos distintos permanecem
  limitados.
- O preview aplica loudnorm em uma passagem. O render editorial completo de
  duas passagens continua disponível no pipeline especializado, mas ainda não
  foi conectado a arquivos de narração no painel.
- O player permanece nativo porque a versão disponível de `@vidstack/react`
  não declara compatibilidade com React 19.
- A waveform permite reduzir o intervalo contido no preview atual. Para
  expandir além dele, é necessário editar os valores numéricos e regenerar.
- Jobs em execução não sobrevivem ao reinício do processo FastAPI.
- Não houve teste visual automatizado em navegador real nesta entrega; os
  testes cobrem componentes, estado e mídia física, mas não screenshots.
