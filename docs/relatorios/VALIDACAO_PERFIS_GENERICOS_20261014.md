# Validação dos perfis genéricos — D057

14/10/2026 · SPEC 1.55. Entrega autorizada: infraestrutura genérica de perfis
e criação de bots pela TUI; parar o motor atual para evitar novos custos.

## Entrega

- Schema estrito, templates completos de day trade, swing e scalping, famílias
  determinísticas conhecidas e instruções limitadas para o JEV.
- Catálogo SQLite versionado: DRAFT, READY_FOR_PAPER e ARCHIVED; conteúdo
  imutável por revisão, auditoria, autenticação e comandos idempotentes.
- Sessão fixa revisão, hash, instruções e parâmetros efetivos. Retomada não
  depende de consultar novamente o catálogo; contrato legado preservado.
- Motor comum com intervalos, indicadores, admissão de ciclos, agenda UTC,
  duração de posição, contexto JEV e gates de execução parametrizados.
- Recuperação manual de candles respeita os dois intervalos salvos; não cria
  decisões ou operações retroativas.
- Protocolos de features/labels/datasets V2, maturação por duração efetiva e
  isolamento de memória/transferência por protocolo. Migração 007 preserva
  registros e referências anteriores.
- TUI remota: Perfis/P, duplicação, editor JSON com referência do schema,
  validação/prévia, publicação, escolha da revisão ao criar sessão e Parar.
  Publicação de perfil não inicia motor nem chama IA.

Guia: [GUIA_PERFIS_BOTS.md](../GUIA_PERFIS_BOTS.md).

## Verificações

`uv run pytest -q`: **288 testes passaram, 39,07 s**. Um aviso de depreciação
da dependência Starlette/httpx; nenhum teste falhou.

`uv run ruff check src/poc tests`, `uv run ruff format --check src/poc tests`
e `git diff --check` passaram.

Cobertura adicional: famílias/validações, ausência de look-ahead, hash legado,
migração com preservação de linhas e FKs, catálogo/auth/revisões, pin persistido
após falha de preparação, retomada, filtros sem chamadas IA, spread/desvio/custos,
saída de agenda sem quote, horizontes/maturação/datasets e fluxo TUI. Recuperação
manual de histórico testada nos três estilos, sem decisões/fills retroativos.

Smoke CLI isolado: template → validação → registro → publicação → consulta,
sem sessão operacional. Imagem Docker com `--network none` carregou e validou
os três templates empacotados, com horizontes em segundos:

| Estilo | Horizontes |
| --- | --- |
| Day trade | 3.600 / 14.400 |
| Swing | 86.400 / 604.800 |
| Scalping | 180 / 900 |

## Implantação e preservação

Motor `eth-01` parado, container preservado. Somente o controle foi recriado,
às **17:22:12 UTC**, com resposta HTTP 200 em `/health`, proprietário existente
preservado e novas rotas protegidas por autenticação.

- Imagem do motor pronta: `sha256:e244b4b9b828af61a06a4bc79e8011d6ab75e96bb71a2b5067104bba8128b01d`.
- Imagem do controle em execução: `sha256:25391226eca1542a27818843b5d623d965acf2e9a7ff4a2bb0957bfcd61a403d`.
- Backup: `data/backups/before-generic-profiles-20261014T165613Z/`, permissões
  0700 nos diretórios e 0600 nos arquivos; backups SQLite individuais, sem
  alegação de atomicidade entre bancos.

Comparação somente leitura entre backup e sessão atual: linhas integralmente
iguais em `runs` (1), `decisions` (171), `decision_outcomes` (342), `paper_fills`
(0), `ledger_entries` (3) e `ai_calls` (103). Auditoria contábil OK. ETH continua
no schema 6, aceito para leitura; migração não foi aplicada desnecessariamente
ao banco parado. Próxima abertura gravável aplica a migração transacional.

Catálogo operacional permanece com **zero perfis cadastrados**; nenhum novo bot
foi criado ou iniciado. Nenhuma chamada paga aos provedores foi necessária nos
testes desta implementação. Container alheio ao projeto não foi alterado.

## Limites e próxima validação

Não foi feito login autenticado na TUI operacional pelo agente: testes de
auth/cadastro/TUI usam ambiente isolado. Credenciais do proprietário não foram
alteradas. O observador anterior não foi parado/reiniciado por esta entrega;
seus registros devem distinguir a parada deliberada do motor.

Novos estilos ainda exigem escolha de perfil/moeda, medições reais de latência,
cobertura das fontes e amostras de execução. Publicar configuração não comprova
deadline real, lucro, transferência ACTIVE ou vantagem financeira do JEV.
O editor da POC usa JSON completo, não formulários individuais para cada campo.
Hold continua fora desta entrega. Não há operações financeiras reais.
