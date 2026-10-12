# E06 — Docker/lifecycle/backup, 12/10/2026

130 testes passaram; lint limpo. Testes incluem runtime sem shell/injeção, identidade de container, env sem valores secretos no argv, idempotência start/stop, backup/restore/ledger/corrupção e bloqueio conservador de chamadas com contadores restaurados.

Imagem ai-trade-memory:0.1.0, SHA ec1ce128e157..., construída. Dois containers Compose sem portas públicas: session-btc e session-eth, WS Binance conectado e quotes frescas/clock VERIFIED. ETH reiniciou restaurando banco. Ambos processaram candle real com fechamento em 17:15 UTC, três decisões/ciclo, zero fills, auditoria sem erros. Limite/circuito de IA compartilhado preservado; ausência de contexto válido impediu compras B/C.

Runtime dinâmico verification-runtime iniciou e parou; endpoint alocado só em 127.0.0.1. Backup online durante operação em data/backups/e06-session-btc; restauração isolada em /tmp/poc-e06-restored com ledger OK e contadores IA bloqueados conservadoramente no dia UTC da recuperação. Originais/volumes não foram apagados.

Esta evidência cobre operações curtas e um candle. Estabilidade >=24h está em E11; sem afirmação de integração JEV válida, Marketaux autenticada ou eficácia preditiva. Novas migrações/imagens exigem parar os motores de ensaio antes da atualização.
