# Limitações Identificadas — Fase T0 (Remediado)

1. **Ausência de Pacote de Fontes Locais (Fase T1)**: A verificação atual não inclui validação visual de renderização de fontes customizadas (Inter/Roboto), a ser coberta na Fase T1.
2. **Uso de Mídia Sintética na Fundação**: Mídia sintética gerada por `ffmpeg lavfi` é usada na Fase T0 para validar a fundação de evidência. Na Fase T2, mídia real do YouTube será integrada.
3. **Locking POSIX Local (`fcntl.flock`)**: Locking é exclusivo ao sistema de arquivos local POSIX.
