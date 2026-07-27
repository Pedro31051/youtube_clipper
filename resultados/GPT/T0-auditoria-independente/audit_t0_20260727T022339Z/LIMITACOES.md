# Limitações

- Nenhum vídeo de terceiros foi baixado e nenhum endpoint do YouTube foi acessado.
- Google Drive, credenciais OAuth/service account e uploads reais não foram exercitados.
- Whisper e transcrição real não foram exercitados.
- O dashboard vivo foi restrito a `127.0.0.1` e porta efêmera; nenhuma porta pública foi aberta.
- A prova de portabilidade usou o contêiner local `t0-audit-clean:1`, sem rede e sem montagem de `/home`.
- A suíte contém mocks; seus 462 resultados não provam integrações externas reais.
- O `gh` confirmou ausência de checks/statuses e listou PRs, mas não há política de proteção de branch registrada no pacote.
