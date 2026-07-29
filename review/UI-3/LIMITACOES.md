# Limitações — UI-3

- O worker é local ao processo FastAPI. Reiniciar o servidor interrompe jobs em
  execução; fila durável, retry e cancelamento pertencem à UI-7.
- O histórico SSE fica em memória. Estado terminal e erro permanecem no SQLite,
  mas eventos detalhados anteriores ao reinício não são reemitidos.
- A FastAPI ainda não porta análise por IA, editor Gemini, render final ou
  Google Drive. Essas operações continuam disponíveis no adaptador legado até
  as fases de revisão/editor/exportação.
- O shell é deliberadamente somente leitura. Criar projeto, analisar, revisar
  cards e editar cortes entram nas UI-4/UI-5.
- O inspetor é um placeholder sem controles funcionais.
- A autenticação remota do servidor legado não foi portada. A nova entrada liga
  apenas em loopback por padrão e não deve ser exposta publicamente nesta fase.
- O build React precisa existir em `web/dist/`; sem ele, a raiz responde 503
  com instrução acionável.
- A validação desta fase cobre Chrome headless indiretamente por UI-2 e testes
  de componentes em jsdom. Homologação visual cruzada e Playwright completo
  continuam na UI-7.
- Não houve publicação em hospedagem externa: a aplicação depende de FastAPI,
  FFmpeg, SQLite e filesystem local. Empacotamento/deploy fazem parte da
  homologação operacional, não do shell UI-3.
- Os dois testes históricos de orçamento NVENC continuaram excedendo 5 s no
  ambiente atual antes desta fase; a funcionalidade de mídia permanece válida,
  mas o orçamento exige investigação de infraestrutura.
- Nenhuma aprovação final é declarada aqui; os artefatos ficam disponíveis ao
  revisor externo.
