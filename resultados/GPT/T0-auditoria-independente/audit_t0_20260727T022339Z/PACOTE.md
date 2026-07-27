# Pacote da repetição da auditoria T0

- **Repositório:** `Pedro31051/youtube_clipper`
- **Baseline:** `fbe8cc5462537dbcaa44ddf6c9182ac218b22c25`
- **Branch:** `agent/refazer-auditoria-independente-t0`
- **Run ID:** `audit_t0_20260727T022339Z`
- **Veredito do executor:** `NAO_APTA_PARA_T1`
- **Suíte:** 462/462 testes aprovados
- **Findings:** 1 crítico, 5 altos, 3 médios, 0 baixos

## Conteúdo

O pacote contém relatório, veredito JSON, hipóteses CSV, inventário, limitações,
log global de comandos, manifesto SHA-256, evidências `00` a `13`, JUnit XML e
scripts de reprodução em `scratch/`.

## Reprodução

Use um checkout limpo desta branch. Consulte `COMANDOS.jsonl` e execute os
comandos na ordem de `seq`. Valide a integridade com:

```bash
cd resultados/GPT/T0-auditoria-independente/audit_t0_20260727T022339Z
sha256sum -c MANIFESTO_SHA256.txt
```

O resultado literal dessa validação após checkout limpo fica em
`evidencias/14-manifesto-checkout-limpo.txt`.

## Limitações

Consulte `LIMITACOES.md`. Nenhuma correção produtiva, credencial, upload, merge
ou avanço para T1 faz parte deste pacote.
