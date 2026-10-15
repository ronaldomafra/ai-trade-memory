# Contexto de desenvolvimento — desenho fechado

**D059/SPEC 1.57:** limites JEV são editáveis no perfil/criação e aplicados
por bot/sessão (SESSION). Total agregado é somente relatório; contadores, custos
físicos e recibos permanecem transacionais e não são zerados na retomada.
Templates `.3`; exemplos em [GUIA_PERFIS_BOTS.md](GUIA_PERFIS_BOTS.md).

Ler [SPEC.md](SPEC.md) integralmente antes de planejar/editar/executar código. [Escopo](ESCOPO_POC_V1.md) e [backlog](BACKLOG_IMPLEMENTACAO.md) organizam entrega; D050 encerra microaprovações, não software.

Marcos 1–5 na ordem: base/contabilidade offline; mercado/ciclos/Docker; JEV/custo/orçamento; labels/memória/dataset; fontes/fatores/operação/relatórios. Depois runtime/transferência/REST-auth/WS/TUI/aceite conforme [plano E06–E11](PLANO_DESENVOLVIMENTO_V1.md). Catálogo inicial trend_15m_v1, par Spot USDT por sessão, banco/container próprios e A/B/C de 100 USDT cada.

## Invariantes

**Próxima extensão D056/SPEC 1.54:** após observar/corrigir o core atual, seguir
[PLANO_PERFIS_ESTRATEGIA.md](PLANO_PERFIS_ESTRATEGIA.md) P00–P09. Inclui cadastro
de perfis por templates completos e instruções JEV, swing/scalping/day trade,
Config/learning/dataset V2 e compatibilidade legada. Hold posterior. Os YAMLs em
docs/templates/perfis são propostas, não configs aceitas pelo runtime atual.
Não implementar outro estilo alterando somente intervalos ou instruções textuais.

- Hexagonal/portas/bootstrap conforme [arquitetura](ARQUITETURA.md); domínio sem HTTP/SQLite/interface. Commit único fill/ledger/saldo/eventos, JSONL reconstruível; Decimal, cutoff, revalidação de risco e lock.
- Mercado público somente leitura; nenhum cliente capaz de ordens reais, credencial de exchange, short/futuros/alavancagem.
- Perfil/configuração/par imutáveis; criação/restore distintos, sem reset/retrotrade ou sessão nova em erro de restore.
- JEV POST OpenRouter alpha/decisions, typesafe/jev-1.13, perguntas/respostas estruturadas, sem Chat Completions. Duas tentativas, custo observado/unknown e limite global.
- Mesmo contexto B/C antes do cutoff; C acrescenta memória. Classificação de fontes sem resultados das carteiras.
- Labels amadurecidos/compatíveis, hierarquia 30/50, janela 60d/três padrões, equivalência/origens preservadas. Dataset inicial opcional sem saldos; transferência automática separada incluída na V1 conforme D052/10.10.
- Reportar dependência entre candles locais, sem pesos/independência/mínimos locais novos. Validação transferida segue contrato separado 10.10.
- Fatores/gates D037–D049: não promover pendentes, fabricar neutralidade, renovar validade por cache/restart ou comprar por premissa não verificável. Independência exigida não verificável = HOLD.
- Orçamento 8.2.1: reserva idempotente/atômica SQLite operacional local separado das finanças; sem subcotas fixas/limite multiplicado.
- API/TUI reutilizam aplicação/backend; GET não chama IA/gera fill e sair do cliente não para motor.

## Testes e entrega

Testes críticos antes/depois dos módulos, fixtures BTCUSDT/ETHUSDT, mocks quando faltar acesso/credencial e crash/idempotência/look-ahead/concorrência. Sem mock/TODO essencial em produção ou alegação de integração real não testada.

Completar schemas/quotas/unidades/fundamento e apresentação com defaults conservadores documentados/testados no backlog. Sem microaprovações; explicitar mudanças materiais. README com comandos reais, artefatos e limitações. Entrega exige critérios da SPEC, inclusive REST/WSS/auth/2FA/TUI/transferência/aceite operacional; lucro não é presumido.

Ordem executável e entregáveis em [PLANO_DESENVOLVIMENTO_V1.md](PLANO_DESENVOLVIMENTO_V1.md); atualizar [STATUS_DESENVOLVIMENTO.md](STATUS_DESENVOLVIMENTO.md) com evidência e próxima ação. D051 substitui lifecycle Docker no cliente: controle/runtime ficam no servidor. Detalhes da transferência em [TRANSFERENCIA_APRENDIZADO.md](TRANSFERENCIA_APRENDIZADO.md).
