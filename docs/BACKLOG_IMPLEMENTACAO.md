# Backlog da V1 — implementação e evidências

**D051/D052 · SPEC 1.50.** O [plano E00–E11](PLANO_DESENVOLVIMENTO_V1.md) é a sequência executável; [status](STATUS_DESENVOLVIMENTO.md) acompanha entregas. Nenhum item declarado implementado.

| Referência | Trabalho |
| --- | --- |
| E00–E01 / Marco 1 | Projeto/portas/config/Decimal/SQLite/UoW/broker/perfis/isolamento e smoke offline. |
| E02 / Marco 2 | Binance público WS/REST, indicadores/A/ciclos/risco/gaps/retomada. |
| E03 / Marco 3 | Decisions API/globalbudget/concorrência/rollover/retry/custo/unknown/crash. |
| E04 / Marco 4 | Labels/local/dataset, maturação/compatibilidade/dedupe/no-look-ahead. |
| E05 / Marco 5 | Marketaux/RSS/Poly/fatores, contratos/quotas/unidades/cobertura/exports/relatórios. |
| E06 | Docker/runtime server-side/volumes/locks/health/backup/restore. |
| E07 / P014 | Catálogo/normalização/sombra/ativação/suspensão/transferência C, proveniência e falha segura. |
| E08 | REST remoto/auth/2FA/token/escopos/lifecycle idempotente/import-export. |
| E09 | WS autorizado/snapshot/cursor/replay/resync/backpressure. |
| E10 / P007 | Textual/login/wizard/dashboard/gráficos/memória/custos/eventos/resize. |
| E11 / P015–P016 | Integração/duas sessões/TLS/crash/24h/README/evidências/homologação posterior. |

Defaults conservadores: dado essencial não verificável não sustenta fator/compra; vazio exige recorte/coleta válidos. Nenhum timestamp/neutralidade fictício. Transferência insuficiente aguarda; local permanece.

Sem TODO/mock essencial em produção. Credenciais/acesso ausentes exigem mocks offline identificados e pendência de teste real. Registrar detalhes no módulo/testes/README, sem rodada nova de microaprovações.
