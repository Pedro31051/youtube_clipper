# Decisões — UI-6

## Tokens CSS nativos

Decisão: manter os tokens em CSS e os primitivos em React tipado.

Alternativa descartada: introduzir Tailwind apenas para esta fase.

Motivo: preserva a arquitetura e o build existentes, reduz dependências e
oferece o mesmo contrato centralizado para todas as telas.

## Estados semânticos

Decisão: estado sempre combina texto, cor, ícone e atributos ARIA.

Alternativa descartada: comunicar estado somente por cor.

Motivo: melhora leitura rápida sem excluir navegação assistiva.

## Compactação por remoção de redundância

Decisão: em 1180 px, ocultar a coluna de identidade repetida do editor e
preservar player, inspetor e timeline.

Alternativa descartada: comprimir permanentemente as três colunas.

Motivo: mantém as ações críticas legíveis na menor largura do gate.

## Ícones como apoio

Decisão: usar imports diretos do Lucide junto de rótulos nas ações principais.

Alternativa descartada: emojis ou botões importantes somente com ícone.

Motivo: consistência visual, semântica previsível e melhor descoberta.
