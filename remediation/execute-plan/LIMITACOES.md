# Limitações — execução do plano de melhorias

## Baseline conhecido

- A suíte completa anterior teve 647 testes aprovados e 7 falhas: cinco causadas pela
  ausência de `faster-whisper` no ambiente parcial e duas por um limite de desempenho
  NVENC inferior a cinco segundos.
- Downloads reais do YouTube dependem de condições externas, botguard e cookies
  válidos; os testes automatizados não substituem uma validação real com credencial
  fornecida pelo operador.
- Upload real no Google Drive continua sujeito a quota e permissões da identidade; a
  execução não cria nem modifica credenciais.
- Benchmarks de GPU dependem do hardware e não devem ser tratados como testes
  funcionais determinísticos.

## Fase 1

- `ffprobe` precisa estar instalado para validar fisicamente uma saída.
- A checagem de resolução é estrita quando dimensões esperadas são informadas.

## Fase 2

- A leitura de `YOUTUBE_COOKIES_FILE` permanece como compatibilidade legada quando não
  há cookies explícitos; chamadas novas devem preferir o argumento por requisição.
- Um caminho inexistente de cookies é encaminhado ao `yt-dlp`, que produz o diagnóstico
  operacional; ele não é criado nem lido antecipadamente pelo projeto.

## Fase 3

- `drive.file` pode exigir que a pasta/arquivo esteja acessível à identidade da aplicação;
  Service Accounts continuam sujeitas à política de quota do Google.
- O semáforo é local ao processo. Múltiplas instâncias do dashboard precisam de um
  limitador distribuído para compartilhar uma mesma GPU com garantia global.
- O servidor HTTP embutido é adequado à operação local; exposição pública ainda deve
  usar proxy TLS, autenticação e limites de borda.

## Fase 4

- O extra `gpu` instala bibliotecas CUDA Python, mas o host ainda precisa de driver NVIDIA
  compatível, FFmpeg e acesso real à GPU.
- Benchmarks `performance` não rodam na CI comum; regressões de tempo são responsabilidade
  do workflow manual em runner NVIDIA.
- Python 3.10 é coberto pela CI declarada, mas esta execução local usa Python 3.12.

## Próximo ciclo recomendado pelo caderno

### Bloqueios operacionais externos

- YouTube em IP de datacenter ainda pode exigir cookies válidos, PO Token externo ou
  proxy residencial; a execução não cria essas credenciais.
- A Service Account atual do Drive pode continuar com quota zero; a solução operacional
  é OAuth de usuário, Shared Drive compatível ou rclone já autorizado.
- Expiração/revogação de cookies ainda merece uma exceção específica e diagnóstico de
  pré-voo, além das mensagens acionáveis já presentes no analisador.

### Evoluções de produto

- Migrar jobs longos para fila/worker persistente, API tipada e progresso por SSE.
- Integrar análise e render com `--auto-clips N`.
- Evoluir o painel para cards com identidade estável, previews individuais, HTTP Range,
  timeline/waveform e testes reais de navegador.

