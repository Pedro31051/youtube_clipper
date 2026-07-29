# Contrato de revisão — UI-4

## Objetivo

Permitir que uma pessoa complete, no painel, o caminho fonte → análise →
previews → revisão sem recorrer à CLI.

## Fluxo

1. `POST /api/v1/projects` persiste projeto e fonte.
2. `POST /api/v1/projects/{project_id}/analysis-jobs` responde `202` e cria um
   job assíncrono.
3. O worker persiste candidatos com `clip_id` imutável e agenda um preview
   físico por corte.
4. SSE publica progresso real; consultas de projetos, jobs e cortes permitem
   recuperar o estado após recarregar a página.
5. `POST /api/v1/clips/review` aprova ou rejeita de 1 a 20 `clip_id`s do mesmo
   projeto em uma única transação.

## Invariantes

- Rank nunca é identidade de uma ação.
- Aprovação exige preview válido e estado `ready` ou `rejected`.
- Rejeição aceita apenas `proposed`, `ready` ou `approved`.
- Um lote inválido não altera parcialmente nenhum corte.
- Cada card usa `poster_url` e `preview_url` versionadas do próprio `clip_id`.
- Só um player de card é montado por vez.
- Falhas de análise e preview permanecem visíveis com ação de recuperação.

## Gate verificável

- O endpoint de análise libera a requisição antes do trabalho pesado.
- Três intervalos físicos conhecidos geram três posters e três MP4s distintos.
- Filtros e ações principais estão visíveis na grade de revisão.
- Abrir editor expõe o plano selecionado, mas não antecipa as funções da UI-5.
- Build TypeScript, contrato OpenAPI e testes Python/React passam.

O cumprimento desses itens produz evidência para revisão externa; não constitui
aprovação da fase por parte do agente.
