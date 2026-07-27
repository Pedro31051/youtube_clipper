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

## Verificação após bloqueio

Após duas falhas consecutivas, não houve terceira medição ambiental. O
`verify_result.json` consolida deterministicamente as tentativas finais
registradas. Uma reexecução zero-trust deverá ocorrer somente em um novo run,
depois que os bloqueios ambientais forem resolvidos.

## Monotonicidade

Foi corrigido o decorator `@audited`: o evento final agora recebe o horário de
emissão, não o horário de início. Isso impede que comandos internos apareçam
cronologicamente depois do evento final. O run já produzido permanece intacto e
documenta a falha anterior.
