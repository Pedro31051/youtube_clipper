# Instruções Obrigatórias para Refazer a Auditoria T0

## Destinatário

Antigravity ou outro agente executor independente.

## Motivo

A auditoria `audit_t0_20260726T234421Z` foi reprovada pela fiscalização
ChatGPT. Ela deve ser preservada integralmente como tentativa fracassada e não
pode ser editada, corrigida, apagada ou substituída.

Parecer de referência:

`resultados/GPT/fiscalizacao-chatgpt/PARECER_FISCALIZACAO_T0_20260726.md`

## Ordem obrigatória

1. Trabalhe no repositório privado `Pedro31051/youtube_clipper`.
2. Leia integralmente o parecer fiscalizatório antes de executar qualquer
   comando.
3. Preserve sem alterações:
   `resultados/GPT/T0-auditoria-independente/audit_t0_20260726T234421Z/`.
4. Parta da baseline que será indicada pela fiscalização no momento da
   execução.
5. Crie uma nova branch:
   `agent/refazer-auditoria-independente-t0`.
6. Crie um novo `RUN_ID` UTC. Não reutilize
   `audit_t0_20260726T234421Z`.
7. Salve toda a nova execução somente em:
   `resultados/GPT/T0-auditoria-independente/<NOVO_RUN_ID>/`.
8. Não modifique `review/T0/`, `runs/`, `src/`, `tests/` ou qualquer pacote
   anterior.

## Correções obrigatórias do método

### 1. Runner e evidências

- Use sequência global `1..N`, sem reinício.
- Dê um ID único a cada comando.
- Grave cada tentativa em arquivo próprio.
- Nunca abra evidência anterior com modo de sobrescrita.
- Preserve stdout, stderr, código de saída e duração de todas as tentativas,
  inclusive as fracassadas.
- Faça `reproduction_command_ids` apontar para IDs inequívocos.

### 2. Manifesto

- Inclua apenas arquivos presentes no commit.
- Exclua `__pycache__`, `.pyc` e temporários.
- Gere o manifesto depois de finalizar o pacote.
- Valide `sha256sum -c` em checkout limpo da branch.
- Salve a saída literal dessa validação.

### 3. Teste H03 — Portabilidade

- Exporte o pacote para ambiente temporário isolado.
- Remova o acesso aos caminhos absolutos originais.
- Não use o ambiente virtual por caminho absoluto da máquina de origem.
- Demonstre o resultado em checkout limpo.
- Registre separadamente cada tentativa.

### 4. Teste H04 — Read-only

- Trabalhe somente sobre uma cópia temporária do run oficial.
- Calcule hashes antes e depois.
- Não execute `verify.py` diretamente dentro de `review/T0/`.
- Falhe a auditoria se qualquer arquivo da cópia for alterado sem saída
  explicitamente autorizada.

### 5. Teste H05 — Corte duplo

- Teste `run_pipeline`, não apenas `FFmpegProcessor.cut_media`.
- Simule `download_segment()` devolvendo um vídeo já recortado que começa em
  `t=0`.
- Use mídia sintética local.
- Solicite um intervalo absoluto como 60–90 segundos para um segmento retornado
  de 30 segundos.
- Capture as duas chamadas: download e corte.
- Execute FFmpeg.
- Meça existência, bytes, streams e duração do resultado com ffprobe.
- Classifique H05 com base na execução, não na leitura parcial de uma função.

### 6. Teste H06 — Dashboard

- Não imprima conclusões pré-escritas.
- Inspecione programaticamente bind, autenticação, rotas, diretórios
  permitidos e mutação de variáveis globais.
- Se executar o servidor, use somente ambiente isolado e loopback.
- Não acesse Google Drive e não exponha portas públicas.

### 7. Findings e veredito

- Transforme toda hipótese confirmada em finding formal.
- Não omita achados para reduzir a contagem.
- Faça o veredito derivar automaticamente dos portões do plano.
- Se qualquer portão de bloqueio ocorrer, use:
  `NAO_APTA_PARA_T1`.
- O executor não possui autoridade para declarar a T0 concluída.

## Validações finais

Antes do commit:

1. `git status --short` deve mostrar apenas o novo pacote.
2. Nenhum arquivo fora de `resultados/GPT/` pode estar modificado.
3. Todos os caminhos citados no relatório devem existir.
4. Todos os hashes devem validar em checkout limpo.
5. Todas as tentativas fracassadas devem permanecer disponíveis.
6. O pacote anterior deve permanecer byte a byte inalterado.

## Salvamento obrigatório no GitHub

1. Adicione explicitamente apenas o novo diretório do run.
2. Faça commit com mensagem clara de nova tentativa.
3. Faça push da branch
   `agent/refazer-auditoria-independente-t0`.
4. Não faça merge.
5. Na resposta final, informe:
   - repositório;
   - branch;
   - novo `RUN_ID`;
   - caminho do pacote;
   - SHA do commit;
   - link do GitHub;
   - veredito;
   - testes executados;
   - achados por gravidade;
   - bloqueios restantes.

## Proibição de encerramento enganoso

Não use expressões como “concluído”, “aprovado”, “100% comprovado” ou “pronto
para T1” enquanto os portões objetivos não estiverem satisfeitos e um
fiscalizador externo não emitir o veredito final.
