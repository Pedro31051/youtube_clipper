# Decisões — UI-3

1. **FastAPI é a nova entrada principal.** O `ThreadingHTTPServer` permanece
   como adaptador legado executável separadamente, não como dependência do
   frontend React.
2. **A API continua em `/api/v1`.** Criar `/api/v2` sem quebra contratual
   produziria duas identidades para o mesmo domínio. A versão muda quando
   existir incompatibilidade real.
3. **O domínio não foi duplicado.** FastAPI injeta e reutiliza `ProjectStore`,
   `generate_clip_preview` e assets da UI-1/UI-2.
4. **Preview sai da thread HTTP.** Um worker local com duas threads devolve 202
   imediatamente e publica eventos reais do job.
5. **Mudança concorrente do plano reprova o resultado.** O worker captura
   `plan_version` e não registra um preview obsoleto se o corte mudar durante o
   FFmpeg.
6. **SSE possui replay na vida do processo.** `Last-Event-ID` e sequência por
   job evitam repetição durante reconexões.
7. **OpenAPI é fonte do cliente.** O schema e os tipos gerados são versionados;
   o build sempre os regenera.
8. **TanStack Query gerencia estado de servidor.** Não foi introduzido Zustand
   porque a UI-3 ainda não possui estado temporário de editor.
9. **Templates legados saíram do Python.** A alternativa de manter grandes
   strings foi descartada porque violava diretamente o gate da fase.
10. **Sem antecipar UI-4/UI-5.** A lista de projetos é somente leitura e o
    inspetor é estrutural; cards, aprovação, player e timeline permanecem nas
    fases próprias.
