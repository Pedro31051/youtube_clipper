# REGRAS PERMANENTES — Fábrica de Cortes

## Autoridade
Agentes NÃO declaram sucesso. Produzem artefatos e evidência; um revisor
externo emite veredito. Relatório é saída de script, nunca texto escrito à mão.

## Log
- Todo estágio usa @audited. Toda execução externa passa por run_cmd.
- events.jsonl é append-only, seq crescente sem buracos, schema 1.0.0.
- Afirmação sem evidence.paths é defeito de contrato.
- runs/ é imutável: corrige-se com run novo, nunca editando o anterior.
- Runs que falharam permanecem no histórico.

## Testes
- Sem mock de FFmpeg, ffprobe ou Whisper no caminho crítico.
- verify.py mede do zero; não recebe dado do agente.
- Teste de mutação obrigatório: artefato quebrado DEVE reprovar.

## Produto
- Short < 60 s no piloto.
- Todo Short precisa de camada editorial original (narração ≥ 8 s e/ou overlay
  analítico), verificada por asserção.
- template_variant precisa variar entre renders consecutivos.

## Direitos
- Só material próprio, CC BY verificado ou com autorização escrita registrada.
- Sem download de terceiro. Prova de licença fica junto da fixture.

## Proibido sem autorização humana explícita
Publicar no YouTube · criar/alterar credenciais · habilitar APIs GCP · mexer em
billing · apagar dados · commit na main · declarar fase concluída.

## Documentos obrigatórios por fase
DECISOES.md (decisão + alternativa descartada + porquê) e LIMITACOES.md (o que
não funciona). LIMITACOES.md vazio é sinal de relatório não confiável.
