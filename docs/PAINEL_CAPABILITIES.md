# Matriz honesta de capacidades do painel

Esta matriz é a fonte de verdade do painel React/FastAPI. Um controle só fica
ativo quando o mesmo plano produz efeito físico verificável no preview e no
render final. Capacidades indisponíveis são desabilitadas na interface e
rejeitadas pela API.

| Função | Campo do `EditPlan` | Implementação física | Preview | Final | Evidência |
| --- | --- | --- | --- | --- | --- |
| Início e fim | `timeline.start_ms`, `timeline.end_ms` | `-ss` e `-t` do FFmpeg | Sim | Sim | `tests/test_edit_plan_compiler.py`, `tests/test_ui5_editor_flow.py` |
| Aspecto e resolução | `output.aspect_ratio`, `output.resolution` | dimensões validadas pelo compilador e filtergraph | Sim, resolução reduzida do mesmo aspecto | Sim | `tests/test_edit_plan_compiler.py` |
| Fundo desfocado | `layout.mode=blur_background` | escala, crop e `boxblur` | Sim | Sim | `tests/test_panel_render_capabilities.py` |
| Crop | `layout.mode=crop_center`, `layout.crop_focus` | crop calculado para o aspecto e foco escolhido | Sim | Sim | `tests/test_panel_render_capabilities.py` |
| Intensidade do blur | `layout.blur_sigma` | parâmetro do `boxblur` | Sim, somente em fundo desfocado | Sim, somente em fundo desfocado | `tests/test_edit_plan_compiler.py` |
| Legendas | `captions.*` | indisponível; não existe asset de legenda ligado ao clip | Não | Não | controles desabilitados e API rejeita `enabled=true` |
| Áudio original | `audio.include_source` | map de áudio ou `-an` | Sim | Sim | `tests/test_panel_render_capabilities.py` |
| Normalização | `audio.normalize` | `loudnorm`; final usa análise/aplicação de duas passagens | Sim | Sim | `tests/test_panel_render_capabilities.py` |
| Narração | `audio.narration_*` | indisponível; não existe asset validado de narração | Não | Não | controle desabilitado e API rejeita narração |
| Overlay analítico | `editorial.overlay_enabled`, `overlay_text` | `drawtext` com texto validado | Sim | Sim | `tests/test_panel_render_capabilities.py` |
| Template | `editorial.template_variant` | somente `variant_default`; outras variantes não têm composição física | Não selecionável | Não selecionável | controle desabilitado e API rejeita variante não padrão |
| Perfil de encoder | derivado de `profile` | preset, CRF, bitrate e resolução | Perfil rápido | Perfil final | `tests/test_edit_plan_compiler.py` |
| Identidade do plano | `plan_version`, `clip_id` | gravada em jobs/assets e recursos aplicados | Sim | Sim | `tests/test_preview_final_equivalence.py` |

## Combinações de saída aceitas

| Aspecto | Preview | Render final |
| --- | --- | --- |
| `9:16` | `360x640` | `720x1280` ou `1080x1920` |
| `1:1` | `480x480` | `1080x1080` |
| `16:9` | `640x360` | `1920x1080` |

Combinações diferentes são recusadas com HTTP 400. O perfil pode alterar apenas
resolução, preset, CRF/bitrate e qualidade de áudio; timeline, layout, overlay,
seleção de áudio e aspecto permanecem idênticos.

## Regras operacionais

- O render final exige aprovação explícita e preview válido da mesma
  `plan_version`.
- Editar qualquer campo suportado incrementa a versão e invalida preview, poster
  e render anteriores.
- Conflitos de `expected_plan_version` retornam HTTP 409; a interface preserva a
  edição local e oferece recarga ou nova tentativa.
- Nenhuma chave desconhecida ou capacidade indisponível é persistida como no-op.
- Jobs `queued` ou `running` sem worker após reinício tornam-se `interrupted` e
  só voltam a executar por retry com novo `job_id`.

## Limites deliberados desta fase

Não fazem parte deste painel: thumbnails por IA, Gemini TTS, tradução, remoção
automática de silêncios, queima de legendas, narração externa e templates
visuais alternativos.
