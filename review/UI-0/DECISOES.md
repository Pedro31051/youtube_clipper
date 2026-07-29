# Decisões — Fase UI-0

## 1. Baseline antes do redesign

- **Decisão:** congelar contratos, screenshots e métricas antes de alterar CSS
  ou extrair o frontend.
- **Alternativa descartada:** iniciar diretamente o redesign Graphite/Cobalt.
- **Por quê:** uma interface nova poderia preservar a identidade instável e os
  previews não versionados, tornando o defeito mais difícil de isolar.

## 2. Fixture totalmente sintética

- **Decisão:** usar vídeo gerado por FFmpeg com três cores, contagens de barras
  e frequências distintas.
- **Alternativa descartada:** usar um vídeo do YouTube ou outra mídia externa.
- **Por quê:** elimina dependência de rede, copyright e interpretação subjetiva
  na correspondência entre card e intervalo.

## 3. Verificação física sem mocks

- **Decisão:** o contrato da fixture executa ffprobe e extrai frames reais por
  FFmpeg.
- **Alternativa descartada:** verificar apenas strings do template ou metadados
  fabricados.
- **Por quê:** o gate precisa detectar arquivo ausente, intervalo errado ou
  mídia fisicamente indistinguível.

## 4. Migração incremental

- **Decisão:** preservar os endpoints existentes durante UI-1/UI-3 por meio de
  adaptadores.
- **Alternativa descartada:** substituir `ThreadingHTTPServer` e a interface
  inteira em uma única mudança.
- **Por quê:** o repositório já possui contratos e evidências úteis; uma
  migração incremental reduz a superfície de regressão.

## 5. Branch dedicada

- **Decisão:** iniciar em `agent/ui-0-panel-baseline`.
- **Alternativa descartada:** alterar ou commitar diretamente na `main`.
- **Por quê:** `agents.md` proíbe commit na `main` sem autorização humana
  explícita e o checkout já continha evidências não rastreadas que devem ser
  preservadas.
