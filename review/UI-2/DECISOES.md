# Decisões — UI-2

1. O preview é um asset de domínio, não um arquivo temporário servido por nome.
2. O endpoint de geração é modelado como job mesmo enquanto a execução ainda é
   síncrona; isso preserva identidade e permite mover o trabalho para fila sem
   quebrar o contrato HTTP de consulta.
3. Preview e render final compartilham o compilador
   `build_render_filtergraph`. Não foi criada uma segunda implementação de
   crop, blur ou overlay.
4. A URL inclui versão e os assets antigos não são sobrescritos. Cache longo e
   imutável é seguro porque uma edição produz uma URL nova.
5. A leitura valida SHA-256 antes de servir. A escolha privilegia a detecção de
   mutação/cross-wire no estágio intermediário; otimização por verificação
   antecipada ou armazenamento somente-leitura pode vir depois.
6. Alteração em qualquer seção visual/sonora do `edit_plan` invalida preview e
   poster. Estado e título não alteram a imagem e, portanto, não invalidam.
7. A API pública expõe assets válidos mais recentes diretamente no corte por
   `preview_url`, `poster_url`, `preview_asset`, `poster_asset` e
   `preview_status`.
