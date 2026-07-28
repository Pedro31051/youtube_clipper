# Auditoria independente — Fase T2

Data UTC: 2026-07-27T14:45:21Z  
Base declarada: `cc3b399` (`main`, 6 commits à frente de `origin/main`)  
Objeto auditado: árvore de trabalho não commitada de `youtube_clipper`  
Veredito: **REPROVADO / NÃO APTO PARA REVISÃO**

## Resumo executivo

O trabalho interrompido produz um MP4 final fisicamente válido em parte dos
critérios (1080x1920, 30,10 s, uma faixa de áudio, -13,99 LUFS), mas não conclui
a Fase T2. O próprio `verify.py` reprova o run empírico mais recente, a suíte
possui falhas reproduzíveis, faltam verificações obrigatórias e não existe o
pacote de revisão nem a branch exigida.

Não foi feita qualquer correção de código nesta auditoria.

## Achados

### [P0] O verificador zero-trust não implementa quatro provas obrigatórias

`src/cortes/verify.py:479-538` mede somente resolução, número de faixas de
áudio, duração e LUFS do render final. Não existe prova de:

- FPS constante;
- limites `0 <= selection.start_ms < selection.end_ms <= duração da fonte`;
- correspondência de cada legenda com palavras do transcript em tolerância de
  +/-200 ms;
- ausência de eventos de legenda fora da seleção.

Além disso, o laço em `src/cortes/verify.py:480-481` não cria uma falha quando
nenhum render final é encontrado. Portanto, a ausência do `short.mp4` não é,
por si, uma asserção obrigatoriamente reprovadora.

Impacto: `overall_passed` não representa todos os critérios de aceitação de T2.

### [P0] O run empírico não prova transcrição por palavra nem legendas

No run `runs/run_challenger_6_e2e_stress`:

- `artifacts/transcribe/transcript.json` contém `segments: []` e `words: []`;
- `artifacts/subtitles/subtitles.ass` contém zero eventos `Dialogue`;
- a seleção foi feita com score `2.0` sobre 30 s, sem densidade real de fala.

O vídeo usado contém tom senoidal, não fala. Assim, o run não demonstra Whisper
GPU com timestamps por palavra nem o mapeamento de legendas exigido.

### [P0] O próprio run mais recente é reprovado pelo verificador

Comando:

```text
.venv/bin/python -m cortes.verify runs/run_challenger_6_e2e_stress
```

Resultado: exit code 1, 17 checks, 15 aprovados e 2 reprovados:

- `ts_monotonic`: timestamp do evento 2 anterior ao evento 1;
- `producer_evidence_required`: evento de ingestão sem evidência.

A causa estrutural está no decorador: `src/cortes/log.py:263-265` captura o
timestamp de início e só emite o evento no `finally`, depois dos eventos filhos.
Funções auditadas aninhadas produzem ordem de append incompatível com os
timestamps de início. O mesmo desenho cria eventos intermediários de produtor
sem `evidence_paths`, que `verify.py:334-354` rejeita.

### [P0] Requisito de caminhos relativos foi relaxado indevidamente

`src/cortes/log.py:229-240` passou a aceitar evidência fora do run e, no último
fallback, grava caminho absoluto. Isso contradiz R3, que exige que todas as
evidências usem caminhos relativos ao run. A alteração foi introduzida para
fazer testes com arquivos em `/tmp` avançarem, mas enfraquece o contrato.

### [P1] Suítes do próprio trabalho falham

Resultados reproduzidos:

```text
tests/test_contracts.py
7 passed

testes funcionais T2 selecionados
43 passed, 4 failed em 595,21 s

tests/e2e/test_tier1_feature_coverage.py
40 passed, 5 failed
```

As quatro falhas pesadas decorrem do baseline zero-trust reprovado. As cinco
falhas de cobertura Tier 1 decorrem de `generate_report()` retornar `dict`
(`src/cortes/report.py:180-185`) enquanto os testes esperam `pathlib.Path`.

A execução completa iniciada pelo Antigravity coletou 635 testes, registrou
cinco falhas iniciais e foi interrompida sem resumo final. Logo, não há prova de
pytest com 0 falhas.

### [P1] Scanner AST declara cobrir testes, mas permite `subprocess` direto neles

`tests/test_contracts.py:231-254` percorre `src/` e `tests/`, porém passa
`is_test_file=True`; o scanner condiciona a proibição de `subprocess` a
`not is_test_file`. Há imports e chamadas diretas de `subprocess` em vários
arquivos de teste. Isso não satisfaz a redação de R2, que exige varredura de
100% de `src/` e `tests/` e ausência de subprocesso direto.

### [P1] Execução Whisper pode cair silenciosamente para CPU

`src/cortes/transcribe.py:60-90` captura qualquer exceção de CUDA e refaz a
operação em CPU/int8 sem registrar a decisão como bloqueio ou evidência. T2
exige transcrição Whisper em GPU. O run não comprova qual dispositivo executou
o modelo.

### [P1] Layout do artefato final diverge do contrato

O contrato exige:

```text
runs/<run_id>/artifacts/<clip_id>/short.mp4
```

A implementação escreve:

```text
runs/<run_id>/artifacts/render/short.mp4
```

Também não há `clip_id` determinístico materializado no caminho ou no resultado
do orquestrador (`src/cortes/pipeline.py:66-77`).

### [P1] Entrega e pacote obrigatórios inexistem

- branch local/remota `agent/t2-short-tecnico`: ausente;
- diretório `review/T2/`: ausente;
- `PACOTE.md`, golden run, `diff.patch`, `files_changed.txt`,
  `verify_result.json`, `report.md`, `DECISOES.md`, `LIMITACOES.md` e
  `CRITICA_INTERNA.md`: ausentes;
- prova de licença da fonte: ausente;
- árvore está em `main`, com 22 arquivos rastreados modificados e 23 arquivos
  não rastreados.

### [P2] Disciplina de arquivos foi violada

Existem `pytest_summary.txt` e `scratch/` soltos na raiz, apesar da regra dura
que permite escrita apenas em `src/`, `tests/`, `runs/` e `review/<fase>/`.

### [P2] Pré-condição de espaço não está satisfeita no momento da auditoria

`df -B1G --output=avail . | tail -1` reportou 17 GiB, abaixo dos 20 GiB
exigidos. Os demais checks observados passaram: Python 3.12.3, FFmpeg com
libass/libfreetype, ffprobe, dependências Python, fontes Noto, Tesla T4 15 GiB
e Git 2.43.0.

## O que está comprovadamente funcional

- contrato AST atual: 7/7 testes verdes;
- dependências essenciais instaladas;
- PySceneDetect invocado por `run_cmd`;
- loudnorm em dois passos implementado;
- render empírico medido em 1080x1920, 30,10 s, 1 áudio e -13,99 LUFS;
- hashes e tamanhos declarados do run empírico conferem nos checks executados.

## Condições mínimas para nova auditoria

1. Corrigir o modelo de eventos aninhados e manter somente caminhos relativos ao run.
2. Implementar no verificador as provas ausentes e exigir explicitamente o render final.
3. Executar golden com fala real/licenciada, palavras e legendas não vazias.
4. Fazer todas as suítes passarem, incluindo os testes E2E, em execução completa.
5. Materializar `clip_id` no layout contratual.
6. Remover violações de disciplina e criar `review/T2/` completo.
7. Entregar em `agent/t2-short-tecnico`, sem commit direto em `main`.

