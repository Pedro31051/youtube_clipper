# Limitações Conhecidas e Fronteiras de Operação — Fase T3

## 1. Desempenho em Fallback CPU vs Requisito de Aceleração por GPU
- O benchmark de velocidade em passada única atinge o critério de tempo de renderização `< 5.0s` para clipes sintéticos de 5s quando executado em ambiente com aceleração por hardware GPU (`h264_nvenc`).
- Em ambientes sem GPU NVIDIA (CPU fallback via `libx264`), o tempo de renderização em passada única para um clipe sintético de 5s é de aproximadamente ~8.68s. Portanto, o requisito rígido de desempenho de renderização `< 5s` exige a presença de GPU NVIDIA operacional no host.

## 2. Latência de Síntese de Narração TTS
- A geração da narração via síntese local de áudio (`flite` / `espeak`) adiciona latência inicial no estágio `env`/`audio` proporcional ao comprimento do texto narrado antes da etapa de mixagem final no FFmpeg.

## 3. Sensibilidade de Sensoriamento PySceneDetect
- Em vídeos de origem com transições suaves de iluminação, gradientes lentos ou câmera fixa, o algoritmo `detect-content` do PySceneDetect pode não detectar múltiplos cortes de cena sem ajuste fino do limiar (`threshold`), utilizando por padrão a janela inteira do vídeo.

## 4. Alocação de Memória RAM/VRAM em Fontes 4K
- A execução do filtergraph complexo em passada única direta a partir de arquivos fonte em resolução 4K (2160p) exige maior alocação de memória RAM e VRAM na GPU. Recomenda-se pré-dimensionamento de buffers para fontes de altíssima resolução.

## 5. Disponibilidade do Runner para a Validação CUDA
- O workflow manual `GPU validation` requer um runner self-hosted com os rótulos `linux`, `x64` e `gpu`, driver NVIDIA compatível e FFmpeg instalado. Sem esse runner, a suíte portátil em CPU continua verificável, mas uma nova medição CUDA não pode ser produzida pelo GitHub Actions.
