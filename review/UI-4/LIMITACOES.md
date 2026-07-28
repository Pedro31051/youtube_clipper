# Limitações — UI-4

- O formulário web aceita URL do YouTube; upload de arquivo local ainda não
  possui endpoint multipart e permanece fora desta entrega.
- Cookies do YouTube continuam configurados no ambiente do processo, não no
  formulário principal. Links bloqueados exibem erro persistente, mas a
  configuração guiada de cookies pertence a Configurações.
- A fila usa executores no processo da API. Reiniciar o processo interrompe
  trabalho em andamento; um worker durável separado ainda é necessário para
  operação distribuída.
- O histórico de eventos SSE reside em memória. Jobs e erros persistem no
  SQLite, mas eventos antigos não sobrevivem ao reinício.
- O botão “Abrir editor” abre apenas o contexto do corte. Waveform, ajuste de
  intervalo, layout, legendas, áudio, undo/redo e regeneração ficam na UI-5.
- Ações em lote usam uma decisão única sobre até 20 cortes; não há
  “rejeitar não selecionados” nem seleção entre páginas.
- Não houve publicação em hospedagem: a tela depende do FastAPI local, FFmpeg,
  SQLite e arquivos de mídia. Uma publicação estática isolada não executaria o
  produto.
