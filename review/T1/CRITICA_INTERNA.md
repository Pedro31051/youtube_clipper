# Crítica Interna — T1

## Achados corrigidos

- A branch anterior confundia a T1 formal com a “Fase 1” do plano de melhorias.
- O run anunciado não estava versionado porque `runs/` era ignorado.
- Relatório e verificação estavam órfãos, sem os artefatos que alegavam medir.
- A branch anterior carregava aproximadamente 140 arquivos de auditoria T0.
- O decorator `@audited` podia produzir timestamps não monotônicos quando uma
  função auditada executava comandos internos.

## Provas atuais

- Branch reconstruída diretamente de `origin/main`.
- O pacote inclui o run completo por adição forçada, sem alterar `.gitignore`.
- `diff.patch` contém apenas o commit de implementação T1.
- O executor impede reabertura de runs existentes.
- Há teste de adulteração da declaração ambiental.
- Há teste de monotonicidade para evento final com comando interno.
- O falso negativo de fontes foi reproduzido e corrigido com regex estendida.
- Run golden: 8/8 checks; rechecagem ambiental: 8/8; integridade: 10/10.
- Suíte completa final: `483 passed in 107.90s`.

## Conclusão

O pacote e o ambiente satisfazem T1. A run bloqueada anterior continua sendo
evidência histórica válida, mas não é usada como prova de aprovação.
