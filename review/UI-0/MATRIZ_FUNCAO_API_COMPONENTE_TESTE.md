# Matriz função → API → componente → teste — UI-0

Esta matriz descreve o contrato atual e o destino planejado. “Lacuna” não
significa que a função deva ser simulada; indica o teste físico ou de contrato
que precisa existir antes da migração.

| Função de produto | API atual | Componente atual | Teste/evidência atual | Destino |
|---|---|---|---|---|
| Abrir painel rápido | `GET /` | `HTML_TEMPLATE` | `test_web_dashboard.py` | shell React |
| Abrir painel técnico | `GET /technical` | `TECHNICAL_HTML_TEMPLATE` | `test_technical_dashboard.py` | configurações avançadas |
| Analisar URL | `POST /api/analyze` | `extract_transcript_and_analyze` | `test_web_dashboard.py` | job de análise |
| Listar candidatos | resposta de `/api/analyze` | `renderClips` | contratos estáticos do template | coleção de `Clip` |
| Prévia antes do render | iframe YouTube por intervalo | `setCardSourcePreview` | `test_card_preview.py` | `Asset(kind=preview)` |
| Identificar card | sem endpoint próprio | `rank` e atributos DOM | lacuna física | `clip_id` imutável |
| Editar início/fim | estado JS local | `editorFieldChanged` | `test_card_preview.py` | versão de `EditPlan` |
| Ajustar formato vertical | payload de `/api/generate-clip` | editor dentro do card | `test_web_dashboard.py` | seção Layout |
| Ajustar foco de crop | payload de `/api/generate-clip` | editor dentro do card | testes de payload | seção Layout |
| Ajustar blur | payload de `/api/generate-clip` | editor dentro do card | testes de payload | seção Layout |
| Definir overlay editorial | payload de `/api/generate-clip` | editor dentro do card | testes de payload | seção Editorial |
| Anexar trilha/imagem | `POST /api/editor-assets` | upload em base64 | testes do dashboard | serviço de assets |
| Pedir edição Gemini | `POST /api/editor-chat` | chat por card | `test_gemini_dashboard.py` | adaptador opcional |
| Confirmar configuração | campo em `/api/generate-clip` | checkbox/estado JS | `test_web_dashboard.py` | status `approved` |
| Render rápido | `POST /api/generate-clip` | `youtube_clipper.pipeline` | testes unitários com stubs e E2E | job em `cortes.pipeline` |
| Executar pipeline auditado | `POST /api/cortes/run` | `cortes.pipeline` | `test_technical_dashboard.py` | worker canônico |
| Acompanhar progresso | `GET /api/status/<request_id>` | polling | testes de status | SSE por `job_id` |
| Baixar MP4 | `GET /api/download/<filename>` | filesystem de output | `test_web_dashboard.py` | asset autorizado |
| Enviar ao Drive | `POST /api/gdrive-upload` | `gdrive_uploader` | testes do uploader | ação de exportação |
| Exibir recibo | resposta do render | `renderReceipt` | testes do dashboard | detalhe do render |
| Persistir projeto | inexistente | inexistente | lacuna | SQLite |
| Cancelar/repetir job | inexistente | inexistente | lacuna | fila local |
| Provar previews distintos | inexistente | iframe por intervalo | fixture UI-0 + teste físico | gate de UI-2 |

## Regras para a migração

1. Endpoints antigos permanecem atrás de um adaptador até seus consumidores
   terem teste equivalente na API versionada.
2. Nenhum componente novo usa `rank` como chave persistente.
3. Preview e render devem consumir o mesmo `EditPlan`.
4. O teste da fixture sintética não pode usar mock de FFmpeg ou ffprobe.
5. Uma mudança de intervalo deve invalidar somente o preview do respectivo
   `clip_id`.
