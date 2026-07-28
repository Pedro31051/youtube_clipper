# Crítica interna e resolução dos achados

## Achados P0

1. **Verificador incompleto** — corrigido. Agora exige render final e mede FPS,
   limites da seleção, alinhamento físico das legendas e integridade.
2. **Golden sem fala/legendas** — corrigido. O golden contém 54 palavras e 54
   eventos ASS.
3. **Run reprovado pelo próprio verificador** — corrigido. A cópia congelada
   passa 22/22.
4. **Caminhos absolutos aceitos** — corrigido. Caminhos absolutos e traversal
   reprovam.

## Achados P1

1. **Suítes falhando** — corrigido: 635/635.
2. **Scanner AST tolerava subprocesso em testes** — corrigido; chamadas diretas
   foram roteadas por `run_cmd`.
3. **Fallback CUDA para CPU** — removido; golden comprova CUDA.
4. **Layout sem clip_id** — corrigido com identificador determinístico.
5. **Branch e pacote ausentes** — branch local e pacote presentes.

## Achados adicionais durante a correção

- O teto de true peak impedia fala dinâmica de atingir a faixa LUFS. O alvo foi
  ajustado para permitir normalização dentro do contrato.
- A atualização in-place de `report.md` quebrava hashes anteriores. Relatórios
  inicial e verificado agora são artefatos distintos e imutáveis.
- Parâmetros `output_path` eram consumidos por wrappers de callback; o
  encaminhamento foi restaurado.

## Discordâncias não resolvidas

Não há discordância funcional aberta. Permanece a limitação ambiental de espaço
livre inferior a 20 GiB, explicitada em `LIMITACOES.md`.
