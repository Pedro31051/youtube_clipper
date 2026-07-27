# Decisões Técnicas — T1

## Escopo

A T1 válida é a definição de ambiente presente na `main`. A redefinição
“baseline/corte duplo” existia somente na branch anterior e foi descartada.
As correções de corte duplo já pertencem à `main`.

## Executor

Os oito comandos são constantes literais em `src/cortes/env.py` e passam pelo
único limite autorizado, `cortes.log.run_cmd`. Cada tentativa registra comando,
stdout, código de saída, duração e número da tentativa.

## Instalação

Com `--install-missing`, somente as dependências mapeadas explicitamente podem
ser instaladas: `python3-soundfile` e `fonts-noto-core`. A alternativa de aceitar
pacotes ou comandos arbitrários foi descartada para não criar uma superfície de
execução privilegiada.

## Imutabilidade

O executor recusa qualquer run não vazio. O run falho não foi editado após a
execução. O pacote contém uma cópia para revisão, acrescida apenas dos resultados
derivados e do relatório.

## Verificação após correção

Após duas falhas consecutivas, a run original não foi reutilizada. A correção
foi comprovada numa nova run imutável. O `verify_result.json` consolida os
resultados registrados; `environment_reverify_result.json` repete fisicamente
os oito comandos sem alterar a run.

## Monotonicidade

Foi corrigido o decorator `@audited`: o evento final agora recebe o horário de
emissão, não o horário de início. Isso impede que comandos internos apareçam
cronologicamente depois do evento final. O run já produzido permanece intacto e
documenta a falha anterior.

## Alternância de famílias de fontes

O comando documentado usava `grep -ci "inter|roboto|noto"`, mas em grep básico
o caractere `|` não representa alternância. Foi adotado `grep -Eci` para medir
as alternativas pretendidas sem fabricar uma família ou caminho contendo pipes
literais. Um teste de regressão fixa essa semântica.

## Recuperação de espaço

O critério de 20 GiB foi atendido removendo somente temporários antigos do
pytest, caches APT/npm/uv/pip/Hugging Face, imagens/build cache Docker sem uso,
logs arquivados do journal e uma revisão Snap desativada. Código, runs e
evidências versionadas foram preservados.
