# Pacote de revisão — Fase T2

Branch: `agent/t2-short-tecnico`  
Base: `cc3b399`  
Golden run: `runs/run_t2_golden`  
Clip: `clip_bf969de3835e`  
Artefato final: `runs/run_t2_golden/artifacts/clip_bf969de3835e/short.mp4`

## Resultado

- Verificação zero-trust da cópia congelada: 22/22 checks aprovados.
- Pytest consolidado: 635/635 testes aprovados em 1039,83 s.
- Whisper: `small`, `device_used=cuda`, 54 palavras.
- Legendas: 54 eventos ASS, todos alinhados em tolerância de +/-200 ms.
- Render: 1080x1920, FPS constante, duração dentro de 20–58 s,
  uma faixa de áudio e LUFS dentro de [-16, -13].

Este pacote não declara a fase concluída. Essa decisão pertence ao revisor
externo.

## Índice

- `runs/run_t2_golden/`: cópia congelada do run completo.
- `verify_result.json`: verificação read-only da cópia congelada.
- `report.md`: relatório verificado.
- `diff.patch`: alterações de código, testes e documentação contra a base.
- `files_changed.txt`: hashes antes/depois do escopo do diff.
- `DECISOES.md`: decisões técnicas e alternativas.
- `LIMITACOES.md`: limitações e pendências externas.
- `CRITICA_INTERNA.md`: achados da auditoria e resolução.
- `evidencias/pytest_full.txt`: saída literal da suíte consolidada.
- `evidencias/pytest.xml`: relatório JUnit consolidado.
- `evidencias/golden_generation.txt`: resumo da geração do golden.
- `evidencias/verify_copy_stdout.json`: saída da verificação da cópia.

