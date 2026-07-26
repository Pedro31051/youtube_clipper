# Limitações da Auditoria Independente T0

1. **Sem Acesso Externo ao YouTube**: Em estrito cumprimento à Regra 13 do Plano de Revisão, nenhum download de mídia de terceiros foi realizado via YouTube. Os testes de mídia foram validados utilizando arquivos sintéticos e fixtures locais com `ffmpeg`.
2. **Sem Credenciais Reais de Google Drive / OAuth**: Conforme a Regra 12, nenhuma chave de produção, segredo de cliente ou arquivo OAuth foi lido ou manipulado. As suítes de teste de upload para o Google Drive rodaram com fixtures mockadas.
3. **Serviços Web Isolados**: A verificação de segurança do dashboard web foi realizada via análise estática e invocações locais isoladas (Regra 14), evitando a abertura de portas públicas no servidor.
