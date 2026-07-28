# Limitações conhecidas — Observabilidade 2.0

- `SIGKILL`, OOM killer, perda de energia ou falha física podem impedir o
  processo de emitir o evento terminal. O efeito é detectável: o run fica sem
  `seal.json` e o verificador reprova `lifecycle_complete`/`run_sealed`.
- `contextvars` isola threads e tarefas no mesmo processo, mas o contexto não é
  propagado automaticamente a processos Python independentes. Eles precisam
  receber `CORTES_RUN_ID` ou iniciar um run filho.
- A redação cobre nomes comuns de segredo, Bearer tokens e query strings
  assinadas. Texto livre pode conter um formato de segredo desconhecido; novos
  padrões devem ser adicionados quando identificados.
- O progresso detalhado do Google Drive depende do transporte expor
  `next_chunk`. Transportes simplificados registram apenas início e término.
- Runs 1.0 são legíveis, mas não possuem informação suficiente para reconstruir
  `planned`, `started`, `skipped` ou a próxima ação.
- Não existe exportação para SaaS de observabilidade nem exclusão automática.
  Capacidade e arquivamento do diretório `runs/` continuam operacionais e
  dependem de decisão humana.


# Limitações conhecidas — Editor e recibo de renderização

- O editor rápido aceita um único intervalo contínuo; não concatena frases ou
  cenas não adjacentes.
- Legendas queimadas, narração e hashtags visuais não fazem parte deste fluxo.
  O painel os marca explicitamente como não incluídos.
- O selo editorial é estático. Não existe reposicionamento por quadro nem
  rastreamento automático de rosto/objeto.
- O áudio pode ser preservado ou removido, mas este caminho rápido ainda não
  aplica loudness normalization nem comprova LUFS. Portanto a validação aqui é
  funcional do painel e da mídia, não a certificação editorial completa do
  pipeline T3.
- O upload real ao Google Drive não foi executado durante a validação de
  navegador para evitar uma gravação externa. Contrato, sucesso parcial e logs
  foram cobertos por testes com transporte simulado.
- A análise do vídeo usado no teste registrou retorno 1 do yt-dlp ao baixar
  legendas, mas recuperou um VTT utilizável e terminou com aviso auditável.
- O recibo aparece na sessão atual do navegador e o MP4 permanece em disco; o
  histórico visual ainda não é reidratado automaticamente após recarregar a
  página.


# Limitações conhecidas — Progresso do Drive

- O percentual representa bytes reconhecidos pelo protocolo resumível do Drive, não bytes ainda em buffers locais ou no socket.
- O painel consulta o status a cada 750 ms; uploads muito pequenos ou muito rápidos podem saltar visualmente entre marcos, embora 0% e 100% permaneçam auditados.
- Se o transporte não expuser `next_chunk`, a interface mostra progresso indeterminado até a resposta final e não inventa percentual intermediário.
- O upload real ao Drive não foi repetido nesta validação para evitar escrita externa; integração, retry, falha e permissão foram exercitados com eventos e transportes simulados.
- O Drive pode aceitar o arquivo e recusar a permissão pública por política do domínio. Nesse caso o arquivo permanece enviado, mas o painel o distingue como `link pendente`.


# Limitações conhecidas — Editor Gemini e anexos

- O chat exige `GEMINI_API_KEY`, conectividade com a API e cota disponível. A
  suíte não realiza uma chamada Gemini real, para não consumir credenciais ou
  cobrança; transporte, schema e respostas foram testados offline.
- O Gemini edita apenas o intervalo contínuo e os controles expostos pelo
  cartão. Ele não edita uma timeline multipista, não gera mídia e não publica.
- Histórico de chat e recibos visuais vivem na sessão atual do navegador; após
  recarregar, os arquivos continuam em disco, mas a conversa não é reidratada.
- Anexos ficam em `_editor_assets` sob o diretório de saída e não são removidos
  automaticamente. A quota de 200 arquivos ou 512 MiB bloqueia novos uploads
  quando atingida; liberação de espaço exige uma decisão humana explícita.
- A opção de render sem áudio produz um MP4 totalmente silencioso; para usar
  trilha sonora, o áudio precisa permanecer habilitado.
- A confirmação de direitos é uma declaração do operador, não uma verificação
  automática de licença, Content ID, disponibilidade territorial ou royalties.

- A prévia da sugestão usa o vídeo-fonte do YouTube limitado por `start`/`end`; o MP4 vertical com as transformações só existe depois da geração. O embed arredonda os limites para segundos inteiros e o navegador pode exigir um segundo clique no player se bloquear autoplay.

# Limitações — Correção intermediária do painel

- Legendas queimadas permanecem indisponíveis. Tema e posição não podem ser
  alterados enquanto não houver asset de legenda ligado à versão do plano.
- Narração externa e TTS permanecem indisponíveis. Nenhum caminho de áudio é
  aceito sem um fluxo de upload e validação de direitos dedicado.
- `split_blur` e templates `variant_news`/`variant_impact` são recusados porque
  ainda não produzem uma composição física distinta.
- O preview usa resolução e parâmetros de encoder reduzidos; a intenção
  editorial e os recursos aplicados são os mesmos do render final.
- WebKit no Playwright aproxima o motor do Safari, mas não substitui uma rodada
  manual em hardware Apple para homologação final.
- A reconciliação considera jobs locais de processos anteriores irrecuperáveis;
  ela não tenta reanexar a um FFmpeg iniciado por outro host.
- Runs auditáveis continuam imutáveis. Limpeza do workspace e retenção de mídia
  exigem ação explícita do operador.
