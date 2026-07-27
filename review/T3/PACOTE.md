# Pacote de Revisão Corrigido — Fase T3

Branch: `agent/t2-short-tecnico`  
Commit Base: `cc3b399`  
Commit baseline: `969a219`  
Commit corretivo T3: `39bf229`  
Golden Run validada: `runs/run_t3_golden_v5`  
Clip ID: `clip_f6be54249092`  
Artefato Final: `review/T3/runs/run_t3_golden_v5/artifacts/clip_f6be54249092/short.mp4`  

## Resumo dos Resultados

- **Verificação Zero-Trust (Read-Only)**: **28/28 checks APROVADOS** tanto na execução original (`verify_result_v5.json`) quanto na cópia congelada (`verify_result_v5_frozen.json`).
- **Suíte completa**: **648 testes aprovados** em 308,65 s no commit `39bf229`, com evidência JUnit em `review/T3/pytest_full_results.xml`.
- **Suíte focal T3/render/mutação**: **32 testes aprovados** em 40,86 s, com evidência JUnit em `review/T3/pytest_t3_results.xml`.
- **Desempenho**: os dois testes NVENC aplicam o limite contratual `< 5 s` exclusivamente à conversão; ambos passaram. A execução golden completa renderizou 26,43 s de mídia em 9,78 s.
- **Otimização de Fundo Desfocado**: Aplicação do filtro Gaussiano em resolução reduzida (`scale=270:480` + `gblur=sigma=12.0`/`15.0`) com reescalonamento posterior para 1080x1920.
- **Camada Editorial Original**: Narração física de 10,0 s copiada para a execução, medida por `ffprobe`, misturada por `amix`, normalizada em duas passagens e combinada com overlay analítico.
- **Rastreabilidade de Variação de Template**: `template_variant` participa do `clip_id`; a execução rejeita variantes presentes nos cinco renders anteriores e o verificador recompõe a prova.
- **Áudio final**: uma faixa, **−15,30 LUFS**, dentro do intervalo exigido `[-16, -13]`.
- **Compatibilidade de Reprodução**: Garantida pela inclusão do parâmetro `-pix_fmt yuv420p` e pré-validação estrita de timestamps (`start < end`).

> A execução histórica `run_t3_golden` e os resultados v1, v3 e v4 foram
> preservados com nomes explícitos. Os arquivos canônicos `verify_result.json`
> e `report.md` agora representam exclusivamente a golden v5.

## Índice do Pacote de Revisão (`review/T3/`)

- `PACOTE.md`: Índice executivo, branch, metadados da execução golden e aviso obrigatório.
- `runs/run_t3_golden_v5/`: Cópia congelada da execução corrigida, contendo `events.jsonl`, `commands.log`, artefatos, relatório original e `report_verified.md`.
- `pytest_t3_results.xml`: resultado legível por máquina dos 32 testes focais.
- `pytest_full_results.xml`: resultado legível por máquina dos 648 testes da suíte completa final.
- `PACKAGE_MANIFEST.sha256`: hashes SHA256 dos documentos e dos 26 arquivos/symlinks da golden v5 congelada.
- `diff.patch`: diff binário reproduzível de `cc3b399..39bf229`, excluindo o próprio pacote para evitar autorreferência.
- `files_changed.txt`: tabela de 57 caminhos com SHA256 e tamanho antes/depois entre `cc3b399` e `39bf229`.
- `verify_result.json`: resultado canônico da golden v5, idêntico a `verify_result_v5_frozen.json`.
- `verify_result_v5.json`: saída legível por máquina de `python3 -m cortes.verify --run-dir runs/run_t3_golden_v5 --audit-out review/T3/verify_result_v5.json`.
- `verify_result_v5_frozen.json`: repetição da verificação sobre `review/T3/runs/run_t3_golden_v5`.
- `DECISOES.md`: Registro detalhado das 6 decisões arquiteturais principais.
- `LIMITACOES.md`: Documento não-vazio com fronteiras operacionais e limitações conhecidas.
- `CRITICA_INTERNA.md`: Síntese da auditoria interna, resultados empíricos de benchmark e auditoria estática AST.
