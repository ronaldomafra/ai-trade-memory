# Contexto de execução — desenho fechado

**D051/D052/SPEC 1.50:** motor, controle REST/WS e TUI implementados/testados localmente; aceite externo/24h permanece no [status](STATUS_DESENVOLVIMENTO.md). Comandos e configuração no [guia de execução](GUIA_CONFIGURACAO_EXECUCAO.md). [Escopo](ESCOPO_POC_V1.md) · [Backlog](BACKLOG_IMPLEMENTACAO.md).

## Sessão

Par Spot USDT público/perfil implementado inicial trend_15m_v1, template/ajustes validados, run_id/SQLite exclusivos e A/B/C de 100 USDT cada. Dataset opcional inicial alimenta só C compatível. Restore conserva configuração/estado/memória, sem reset/reimportação/retrotrades.

Docker Compose com motor/volume por sessão, controle REST/WSS autenticado e TUI local/remota. Lifecycle no servidor; cliente prepara/inicia/restaura pela API e acompanha eventos. Fechar TUI mantém motores. CLI/systemd alternativas, sem supervisores concorrentes do mesmo banco.

| Condição | Operação |
| --- | --- |
| Candle fechado/contexto válido | Avaliar A/B/C, validar risco/preço/prazo e registrar fill virtual. |
| Fonte parcial com fator válido ou recorte validamente sem item relevante | Avaliar conforme D046/D048 com limitação explícita, sem compra automática. |
| Nenhum fator utilizável por falha/pendência ou compra por premissa/conflito não verificável | Bloquear compra afetada e registrar motivo; A/risco preservados. |
| JEV inválido/timeout/orçamento sem capacidade | HOLD nas variantes afetadas; risco ativo. |
| Cotação/features inválidos/vencidos ou decisão antiga | Não abrir/fabricar fill; proteção pendente quando aplicável. |
| Stop/trava/take/duração/SELL elegível | Saída conforme precedência/cotação válida, único fill. |
| Perda diária >=5% | Encerrar com cotação fresca e bloquear BUY da carteira até próximo UTC, com latch/pendência persistidos. |
| Restart/crash | Reconciliar/restaurar tentativas/custos/eventos/lock sem duplicação/reset. |

USDT financeiro separado de USD/unknown IA. Orçamento global 240 chamadas físicas e US$ 0,05 observado/dia UTC, inclusive retries/classificação, sem subcotas fixas inicialmente. Duas sessões não dobram capacidade; reportar cobertura/HOLD por falta de orçamento.

TUI mostra identidade/horários/saúde, carteira/posições/fills/curvas, decisão/gates, memória/custos e eventos. Desconexão/estado antigo explícitos, sem inferência por renderização. SQLite canônico; JSONL/exports reconstruíveis, registro de endereços sem saldos.

Validar offline, integrações disponíveis, backup/restore, SIGTERM/crash/container, duas sessões/limites e 24h antes de uso desassistido. Homologação após evidências; não alegar conexões/testes não feitos. Outros estilos/HTML são evolução. Transferência automática integra V1, separada da memória local e validada conforme [contrato](TRANSFERENCIA_APRENDIZADO.md).

Acesso remoto por HTTPS/WSS com token/2FA; perda de conexão/expiração de token não para motor. Publicação automática no catálogo mantém proveniência/cutoff; insuficiência/falha deixa transferência inativa, sem perder memória local. Ver [plano](PLANO_DESENVOLVIMENTO_V1.md) e [status](STATUS_DESENVOLVIMENTO.md).
