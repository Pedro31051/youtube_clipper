# Fixture de identidade dos previews

Esta fixture é o caso reproduzível da fase UI-0. Ela contém três candidatos
consecutivos, visual e sonoramente distintos:

| Candidato | Intervalo | Identidade visual | Tom |
|---|---:|---|---:|
| `fixture-red-440` | 0–3 s | vermelho, uma barra branca | 440 Hz |
| `fixture-green-660` | 3–6 s | verde, duas barras brancas | 660 Hz |
| `fixture-blue-880` | 6–9 s | azul, três barras brancas | 880 Hz |

Regeneração:

```bash
.venv/bin/python scripts/generate_panel_baseline_fixture.py \
  --run-id run_ui0_panel_fixture_<novo_identificador>
```

O gerador recusa implicitamente reutilizar um run selado, conforme o contrato
imutável de `cortes.log`. Use sempre um identificador novo para uma nova
evidência.

Uso esperado nas fases seguintes:

1. analisar ou cadastrar os três intervalos;
2. gerar um preview independente para cada `clip_id`;
3. provar que cada card aponta para o asset de seu próprio `clip_id`;
4. alterar apenas o segundo intervalo;
5. provar que somente o preview verde é invalidado e versionado novamente.
