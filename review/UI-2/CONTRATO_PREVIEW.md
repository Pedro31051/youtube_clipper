# Contrato de preview por corte — UI-2

## Identidade

Cada preview e poster pertence a exatamente um `clip_id`. O arquivo físico é
copiado para o workspace imutável do corte e recebe `asset_id`, `version`,
`sha256` e URL própria:

```text
/api/v1/assets/{asset_id}?v={version}
```

O caminho físico nunca aparece na API ou no manifesto público.

## Geração

`POST /api/v1/clips/{clip_id}/preview-jobs`:

1. carrega fonte, intervalo e `edit_plan` persistidos;
2. muda o corte para `previewing`;
3. cria MP4 H.264 360×640 com `faststart`;
4. cria poster JPEG do próprio MP4;
5. registra ambos como assets imutáveis;
6. conclui o job e muda o corte para `ready`.

Preview e render final usam `build_render_filtergraph`. O preview reduz
resolução, qualidade e tempo de codificação, mas conserva intervalo, modo de
layout, foco do crop, desfoque, posição e texto do overlay e decisão de áudio.

## Leitura e seek

`GET /api/v1/assets/{asset_id}?v={version}` exige a versão exata, confirma:

- vínculo do caminho com o workspace do corte;
- validade do asset;
- tamanho;
- SHA-256.

A resposta oferece:

- `Accept-Ranges: bytes`;
- `206 Partial Content` e `Content-Range` para ranges válidos;
- `416` para ranges inválidos;
- `Cache-Control: public, max-age=31536000, immutable`;
- `ETag` derivado do SHA-256.

O corpo é enviado em blocos de até 64 KiB, sem carregar o MP4 inteiro em
memória.

## Invalidação

Qualquer mudança efetiva de timeline, layout, captions, áudio ou editorial:

- incrementa `plan_version`;
- invalida somente previews/posters daquele `clip_id`;
- mantém o arquivo anterior como evidência histórica;
- faz o corte responder `preview_status: stale`;
- gera um novo asset com versão crescente na próxima solicitação.

Mudanças apenas de título ou estado não invalidam a mídia. Repetir uma
configuração idêntica também não cria uma nova versão do plano.

## Evidência física

O teste `tests/test_dashboard_preview_api.py` usa a fixture de 9 segundos com
três intervalos conhecidos: vermelho, verde e azul. Ele gera mídia real com
FFmpeg, mede cor dos frames, compara identidade/hash/URL, exercita seek por
Range, altera apenas o primeiro corte e confirma regeneração `v=2`.
