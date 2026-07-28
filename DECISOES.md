# Decisões — Observabilidade 2.0

## Evento canônico

**Decisão:** `runs/<run_id>/events.jsonl` continua sendo a única fonte de
verdade e novos eventos usam o schema `2.0.0`. O leitor e o verificador aceitam
runs históricos `1.0.0`.

**Alternativa descartada:** criar um segundo JSONL operacional. Isso permitiria
preservar o escritor 1.0, mas criaria duas timelines divergentes.

## Lifecycle

**Decisão:** toda fronteira observável emite `started` antes do trabalho e um
estado terminal. O orquestrador declara `planned`; no encerramento, toda ação
sem terminal é reconciliada como `skipped`.

**Alternativa descartada:** um único evento ao final. Ele não distingue uma
ação que nunca iniciou de uma ação interrompida.

## Concorrência

**Decisão:** run, trace, span e request usam `contextvars`. O lock de arquivo
continua responsável pela sequência atômica.

**Alternativa descartada:** manter um `run_id` global de processo, pois o
dashboard usa `ThreadingHTTPServer` e misturaria requisições simultâneas.

## Comandos e streams

**Decisão:** `commands.log` é um índice; stdout e stderr completos ficam em
`commands/`, com SHA-256 e tamanho no evento.

**Alternativa descartada:** incorporar streams ilimitados ao JSONL, o que
degradaria leitura, recuperação e análise.

## Falha do próprio logger

**Decisão:** falhar fechado. Se o evento canônico não puder ser persistido, a
ação aborta com `AuditLogError` e uma mensagem mínima é enviada ao stderr.

**Alternativa descartada:** continuar a operação silenciosamente, pois isso
permitiria sucesso sem trilha auditável.

## Retenção

**Decisão:** nenhum run é removido ou rotacionado automaticamente. Runs
terminais recebem `seal.json` com hash do `events.jsonl`.

**Alternativa descartada:** expiração automática, incompatível com a regra de
preservação de tentativas falhas e com a proibição de apagar sem autorização.


# Decisões — Editor e recibo de renderização

## Confirmação por corte

**Decisão:** cada sugestão mantém configuração própria e nenhuma renderização
parte do painel sem `confirmed_configuration=true`. A confirmação é consumida no
início da operação e qualquer edição posterior exige uma nova confirmação.

**Alternativa descartada:** manter os botões diretos de gerar/upload, porque eles
não mostravam nem congelavam a especificação que seria aplicada.

## Controles realmente aplicados

**Decisão:** início/fim exatos, layout, foco horizontal do crop, intensidade do
blur, áudio original/mudo, texto/posição do selo editorial e destino são
normalizados pelo servidor e propagados explicitamente até o FFmpeg. Texto livre
do overlay é lido por `drawtext=textfile` temporário para não virar sintaxe de
filtro.

**Alternativa descartada:** oferecer toggles somente visuais para legenda,
narração ou hashtags. Esses itens aparecem como não incluídos até haver
integração física com o renderizador correspondente.

## Recibo e versões

**Decisão:** cada render recebe nome único vinculado ao request ID e devolve
`applied_settings` e `render_receipt`. O recibo inclui itens incluídos/excluídos,
resultado do Drive, tamanho, SHA-256 e metadados medidos por ffprobe quando
disponíveis. A versão anterior e seu recibo permanecem visíveis ao editar.

**Alternativa descartada:** inferir o resultado apenas no JavaScript ou
sobrescrever `clip_<video>_<inicio>_<fim>.mp4`, pois ambas as opções ocultariam
diferenças entre versões.

## Validação funcional

**Decisão:** validar no navegador com o vídeo `3Vpf3EaE1mc`, exercitando tempos
fracionários, confirmação/revogação, preview do intervalo, crop à direita, áudio
mudo, overlay no rodapé, recibo, edição pós-render e responsividade 390x844.

**Alternativa descartada:** considerar apenas testes unitários como prova do
fluxo do painel.


# Decisões — Progresso do upload ao Drive

## Progresso confirmado

**Decisão:** usar upload resumível em chunks explícitos de 4 MiB e publicar 0%, bytes reconhecidos pelo Drive, percentual monotônico e 100% somente após a resposta final. Retries preservam o último valor confirmado.

**Alternativa descartada:** animar um percentual estimado pelo tempo, pois sugeriria avanço sem confirmação do servidor.

## Contrato público e interface

**Decisão:** `/api/status` projeta apenas `drive_upload` com estado, percentual, bytes, total, chunk e tentativa. O `decision` bruto continua privado. A mesma informação aparece no painel geral e no card do corte, com `role=progressbar`, estados determinados/indeterminados e etapas Autenticação, Envio e Link.

**Alternativa descartada:** expor o evento de auditoria completo ao navegador ou depender apenas de mensagens de log.

## Confirmação da entrega

**Decisão:** separar bytes enviados de permissão compartilhável. Uma falha ao criar a permissão mantém o upload como não fatal, mas termina visualmente como `100% · link pendente`; somente bytes mais permissão concluída recebem sucesso completo.

**Alternativa descartada:** declarar link disponível sempre que o arquivo fosse criado no Drive.

## Validação funcional

**Decisão:** exercitar o vídeo `3Vpf3EaE1mc` no navegador e simular apenas os eventos do Drive: 37,5%, retry, fallback indeterminado, 100%/finalização, link pendente, sucesso e viewport 390x844. Nenhum upload externo foi realizado.


# Decisões — Editor conversacional Gemini e composição de mídia

## Conversa por corte e confirmação humana

**Decisão:** cada card mantém seu próprio histórico de chat. O Gemini devolve
somente uma resposta em português e um patch estruturado de campos permitidos;
o navegador aplica o patch aos controles, revoga a confirmação anterior e não
inicia o render automaticamente.

**Alternativa descartada:** permitir que texto livre do modelo vire comando,
caminho local ou ação de FFmpeg, pois isso eliminaria a revisão humana e o
contrato já auditado do render.

## Chave e privacidade

**Decisão:** chamar a Interactions API somente no backend com
`GEMINI_API_KEY`. Chat, transcrição, histórico, chave e base64 são mascarados na
auditoria; ficam apenas metadados operacionais necessários.

**Alternativa descartada:** colocar a chave no HTML/JavaScript ou persistir o
prompt completo nos eventos de auditoria.

## Proteção do serviço local

**Decisão:** todos os POSTs exigem `application/json`; requisições de navegador
com `Origin` diferente do `Host` do dashboard ou `Sec-Fetch-Site: cross-site`
são recusadas mesmo quando o servidor está limitado ao loopback.

**Alternativa descartada:** tratar `127.0.0.1` como proteção suficiente, pois
uma página externa pode tentar provocar chamadas pagas e renders via CSRF.

## Anexos e composição física

**Decisão:** receber trilha e imagem inicial por ID opaco, após confirmação de
direitos, allow-list de formato, assinatura, tamanho e integridade SHA-256. O
pipeline concatena a abertura, mistura a trilha e rejeita duração final acima de
59,9 s. O recibo registra os IDs e parâmetros aplicados, sem expor caminhos.

**Alternativa descartada:** aceitar caminhos/URLs fornecidos pelo cliente ou
truncar silenciosamente a edição para caber no limite de Shorts.


## Preview isolado por sugestão

**Decisão:** cada card começa com uma tela própria contendo número, título e intervalo da sugestão. O iframe do YouTube só é montado após o clique em `Reproduzir sugestão #N`; ao abrir outro card, o iframe anterior é desmontado e volta ao seu resumo.

**Alternativa descartada:** pré-carregar cinco iframes do mesmo vídeo, pois todos exibiam a mesma capa e `0:00`, ocultando que os intervalos eram diferentes e consumindo recursos sem interação.
