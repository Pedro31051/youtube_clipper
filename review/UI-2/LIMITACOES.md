# Limitações — UI-2

- O job de preview possui identidade e estados persistidos, mas ainda executa
  de forma síncrona na thread HTTP. Fila, worker, cancelamento e retry ficam
  para a evolução da infraestrutura.
- A análise não dispara previews em lote automaticamente. Cada corte inicia o
  próprio job sob demanda, evitando baixar e codificar candidatos que o usuário
  nunca abrirá.
- A interface HTML legada já mantém um player por card, mas ainda usa o trecho
  incorporado do YouTube como preview inicial. A troca completa para os assets
  persistidos integra a fase React/revisão (UI-3/UI-4).
- Captions fazem parte do plano e invalidam assets, porém a UI-2 não gera
  legendas para o preview porque ainda não existe um asset de legenda associado
  ao corte.
- A verificação de integridade relê o asset inteiro antes de atender um Range.
  A leitura é em blocos e não aumenta o uso de memória com o tamanho do vídeo,
  mas adiciona I/O por requisição.
- A prova automatizada usa três candidatos semanticamente distintos. O
  contrato não limita a quantidade, mas a prova de dez cards e a validação
  manual cruzada em Safari/Chrome permanecem como gate de produto externo.
- Não há declaração de aprovação final nesta fase; os artefatos e testes ficam
  disponíveis para o revisor externo do projeto.
