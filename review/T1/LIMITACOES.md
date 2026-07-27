# Limitações Identificadas — Fase T1

1. **Bloqueio de Datacenter no YouTube (Botguard)**: O ambiente da VM GCP exige a exportação de `cookies.txt` atualizados de uma sessão autenticada do YouTube para downloads reais via `yt-dlp`. Sem o parâmetro `--cookies` ou a variável `YOUTUBE_COOKIES_FILE`, o YouTube retorna o bloqueio `Sign in to confirm you're not a bot`.
2. **Cota de Armazenamento da Service Account no Google Drive**: A Service Account do GCP possui cota zerada (`storageQuotaExceeded`), exigindo o uso de credenciais OAuth2 de usuário ou o compartilhamento via `rclone`.
3. **Desempenho da Renderização Vertical em CPU**: A renderização com o filtro `boxblur=20:10` em resolução total 1080x1920 sem GPU leva ~3m27s para um trecho de 30s. A otimização de performance (downscaling do blur + aceleração NVENC) está mapeada para a Fase 3.
4. **Isolamento de Testes Offline**: Os testes automatizados em `test_regression_media.py` utilizam fontes sintéticas locais para garantir determinismo e isolamento de rede.
