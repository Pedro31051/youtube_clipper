# Sistema visual — UI-6

## Direção

O painel usa Graphite/Cobalt: superfícies neutras escuras para hierarquia e
azul somente para ação, seleção e foco. Verde comunica sucesso, amarelo
processamento ou atenção e vermelho falha ou destruição. Scores permanecem
neutros.

Os tokens canônicos estão em `web/src/design-tokens.css`. A escala usa espaços
múltiplos de 4 px, controles com raio de 8 px e painéis com raio de 12 px.
Inter, Geist e fontes de sistema formam a pilha tipográfica.

## Primitivos e estados

`web/src/ui.tsx` centraliza botão, badge de status, empty state e skeleton.
Os estados reconhecidos são vazio, carregando, pronto, desatualizado, erro,
desabilitado, processando e concluído. Ícones Lucide complementam texto; não
substituem rótulos de ação.

## Responsividade e teclado

- padrão: sidebar de 236 px e inspetor de 312 px;
- até 1180 px: modo compacto, sem coluna redundante de candidatos no editor;
- até 680 px: leitura em uma coluna e barra de lote contida no viewport;
- link para pular ao conteúdo, foco visível e ordem DOM coerente;
- editor com semântica de diálogo, fechamento por Escape e abas navegáveis por
  setas, Home e End.

O gate alvo cobre 1180×720, 1440×900 e 1920×1080, contraste WCAG AA e fluxo
principal por teclado. As evidências são submetidas à revisão externa; o
agente não aprova a fase.
