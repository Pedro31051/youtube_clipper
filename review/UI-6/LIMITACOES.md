# Limitações — UI-6

- A entrega não declara aprovação visual; esse aceite pertence ao revisor
  externo conforme as regras do repositório.
- Não foi gerado snapshot em navegador real porque a solicitação não incluiu
  QA visual automatizado. Tokens, breakpoints, semântica, contraste e build
  são validados automaticamente.
- O modo móvel empilha o inspetor abaixo do player; ele não implementa uma
  navegação móvel dedicada.
- A pilha tipográfica usa fontes locais disponíveis no sistema e não baixa
  arquivos de fonte externos.
- O diálogo do editor controla foco inicial, Escape e scroll do documento,
  mas não inclui uma biblioteca completa de focus trap.
- A aplicação permanece local, dependente de FastAPI, SQLite, filesystem e
  FFmpeg. Publicação e operação pertencem à UI-7.
