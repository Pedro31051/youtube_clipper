# Contrato do editor compacto — UI-5

## Unidade de execução

O `edit_plan` persistido no SQLite é a única fonte para preview e render final.
O frontend envia `expected_plan_version`; gravações concorrentes com versão
antiga recebem `409`, e cada alteração estrutural invalida somente os assets do
próprio `clip_id`.

## Superfície

- coluna esquerda com identidade e estado do candidato;
- player central com o último preview físico e safe area;
- inspetor com Corte, Layout, Legendas, Áudio, Editorial e Saída;
- waveform do preview com região redimensionável;
- indicador permanente de pendência, salvamento, sincronização ou erro;
- undo/redo local isolado por `clip_id`, também acessível por teclado;
- regeneração de preview e render final como jobs assíncronos reais.

## Campos executados fisicamente

- início/fim e duração;
- crop central ou fundo desfocado, foco e sigma;
- inclusão do áudio original e normalização;
- overlay analítico e texto;
- proporção e resolução de saída.

Legendas e template são persistidos no contrato para evolução do compilador. A
interface informa quando falta o asset físico necessário. Narração e TTS não
são apresentados como funcionais sem upload ou arquivo de áudio real.

## Gate verificável

1. Um save incrementa a versão e torna o preview anterior `stale`.
2. Undo restaura o snapshot anterior e agenda novo autosave.
3. O preview regenerado recebe nova URL versionada.
4. O render final só parte de preview atual e decisão aprovada.
5. Teste físico confirma que preview e render usam o mesmo intervalo, layout e
   plano, sem mocks de FFmpeg ou ffprobe.

Essas evidências são submetidas à revisão externa; o agente não aprova a fase.
