# Limitações e Bloqueios — T1

1. **Fontes**: `fc-list | grep -ci "inter|roboto|noto"` retornou `0` e exit code
   `1` nas tentativas 1 e 2, mesmo após a instalação registrada de
   `fonts-noto-core`.
2. **Disco**: o comando literal retornou `19 GiB` nas duas tentativas; o mínimo
   exigido é `20 GiB`.
3. **Run não aprovado**: o resultado final é 6/8. Não existe run golden T1.
4. **Integridade temporal do run preservado**: a verificação estrutural detecta
   que o evento final do decorator possui timestamp anterior aos comandos
   internos. O código foi corrigido, mas o run falho não foi reescrito.
5. **Instalação no host**: `python3-soundfile`, `fonts-noto-core` e dependências
   foram instalados no sistema. `soundfile` passou na segunda tentativa.
6. **CI remoto**: ainda não havia execução do GitHub Actions no momento da
   construção deste pacote; a suíte foi executada localmente em checkout limpo.

Próxima ação necessária: recuperar pelo menos 1 GiB adicional sem excluir dados
do projeto e diagnosticar o fontconfig. Depois disso, executar um novo run T1;
não reutilizar nem editar o run atual.
