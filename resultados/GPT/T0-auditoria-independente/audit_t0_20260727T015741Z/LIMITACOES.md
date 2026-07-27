# Limitações da Auditoria Independente T0 — run `audit_t0_20260727T015741Z`

1. **Nenhum acesso ao YouTube.** Em cumprimento à regra 13 do plano, nenhum
   vídeo de terceiros foi baixado. A mídia usada em H05 foi gerada localmente
   com `ffmpeg lavfi` (`testsrc` + `sine`, 30 s). O downloader foi substituído
   por um dublê; a URL do YouTube presente na evidência nunca foi acessada em
   rede.

2. **Nenhuma credencial lida.** Em cumprimento à regra 12, nenhum cookie,
   token, chave, arquivo OAuth ou variável secreta foi lido, copiado ou
   registrado. Em H06, `upload_clip_to_gdrive` foi substituído por um dublê
   que apenas registra o caminho recebido: **nenhum envio real ao Google Drive
   ocorreu**. O caminho `/etc/passwd` foi usado como sonda porque existe em
   qualquer host Linux; seu conteúdo não foi lido nem versionado.

3. **Dashboard restrito a loopback.** Em cumprimento à regra 14, o servidor de
   teste foi preso a `127.0.0.1` numa porta efêmera e encerrado ao fim do
   ensaio. O bind padrão em todas as interfaces (`server_address = ('', port)`)
   foi determinado por leitura de AST e pela semântica de socket medida, não
   por exposição real.

4. **A "máquina limpa" é um contêiner local.** O teste de portabilidade em
   ambiente sem os caminhos originais usa um contêiner Docker sem acesso a
   `/home`, com um clone contendo apenas arquivos versionados. Isso demonstra a
   dependência dos caminhos da máquina original, mas não substitui validação em
   hardware de terceiros. A conclusão é reforçada por uma segunda prova
   independente, que não depende de contêiner: destruir os artefatos da própria
   cópia relocada não altera o resultado da verificação.

5. **Testes com mock não são prova de execução real.** Os 462 testes da suíte
   exercitam FFmpeg, ffprobe, Whisper, YouTube e Google Drive majoritariamente
   sob mock. O resultado verde não comprova integração real com esses serviços,
   e não foi tratado como se comprovasse.

6. **Escopo declaradamente documental.** Nenhuma correção de código foi
   implementada, conforme a regra 14 da seção 1 do plano. Os onze achados
   permanecem apenas documentados nesta branch.

7. **Efeito colateral inevitável da reprodução da suíte.** Executar `pytest`
   cria diretórios sob `runs/`, que não é versionado. Isso é comportamento do
   próprio projeto, foi medido e não afetou nenhuma área versionada:
   `REVIEW_T0_INTACTO_APOS_PYTEST=SIM` e `git status` limpo em `review/` e
   `runs/`.

8. **Duas execuções repetidas de slot.** Os slots `09-verificador-readonly`,
   `10-corte-duplo`, `11-dashboard-superficie`, `12-ci-e-branches` e
   `14-mutacao-cobertura` têm mais de uma tentativa registrada. Todas estão
   preservadas em arquivos próprios, incluindo a tentativa `#0015` que terminou
   com exit 1. Nenhuma foi sobrescrita, editada ou removida. Onde as tentativas
   diferem, o relatório cita a mais completa e o `VEREDITO.json` lista ambas.
