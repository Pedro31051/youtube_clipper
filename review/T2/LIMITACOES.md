# Limitações — T2

- O espaço livre observado ao final ficou em aproximadamente 15 GiB, abaixo da
  pré-condição histórica de 20 GiB. A suíte e o golden concluíram, mas uma nova
  execução deve liberar espaço antes de começar.
- As dependências CUDA adicionadas são condicionadas a Linux x86_64. Outros
  ambientes devem solicitar `device=cpu` explicitamente ou fornecer seu próprio
  runtime CUDA compatível.
- O golden usa fala sintetizada localmente. Ele prova a mecânica técnica, não a
  qualidade editorial ou monetização, que pertencem a fases posteriores.
- O filtro de FPS constante compara `r_frame_rate` e `avg_frame_rate` medidos
  por ffprobe. Ele detecta divergência nominal/média, mas não faz análise
  frame-a-frame de cadence irregular.
- Nenhum upload, publicação, credencial Google ou configuração de faturamento
  foi tocado.
- A branch foi criada localmente, mas não foi commitada nem enviada ao GitHub
  nesta execução.

