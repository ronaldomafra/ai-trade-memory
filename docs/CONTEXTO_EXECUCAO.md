# Contexto de execução — desenho fechado

**Atualização D060/SPEC 1.58:** o teste ZEC com janela 8s não consultou JEV no
ciclo admitido por faltar espaço para timeout 6s após a preparação. SCALPING
agora aceita até 15s; revisão 2 de `scalping_zec_v1` usa esse prazo, mantendo
1m/5m, timeout 6s e demais parâmetros. Sessão `zec-scalping-02` iniciada a pedido
do usuário; anterior parada e preservada. Não mudar snapshots ao restaurar.

**D051–D054/SPEC 1.52:** motor, controle REST/WS e TUI implementados/testados localmente; aceite externo permanece no [status](STATUS_DESENVOLVIMENTO.md). Duração da amostragem definida pelo usuário, sem mínimo de 24h. Comandos e configuração no [guia de execução](GUIA_CONFIGURACAO_EXECUCAO.md). [Escopo](ESCOPO_POC_V1.md) · [Backlog](BACKLOG_IMPLEMENTACAO.md).

## Sessão

D056/SPEC 1.54 planeja a próxima etapa de perfis cadastráveis swing/scalping/day
trade, após revisão do core atual; hold adiado. Os templates completos são apenas
contratos futuros e não alteram `eth-01`. Seguir o
[plano P00–P09](PLANO_PERFIS_ESTRATEGIA.md); depois homologar o perfil escolhido
antes de criar outra sessão para o experimento de aproximadamente um mês.

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

USDT financeiro separado de USD/unknown IA. D059/SPEC 1.57: orçamento JEV por bot nos perfis cadastráveis, com defaults editáveis de 240 chamadas e US$ 0,05/dia UTC. Decisão/classificação/retries entram no pagador, cache não cobra novamente. Contadores independentes; total agregado é relatório, sem teto global oculto. Configurar `ai` no perfil/criação; consultar `ai-budget --run-id ID`. Restore antigo mantém contrato/hash anteriores e não muda para SESSION silenciosamente. D053 é compatibilidade legada. Atualizar imagens antes de usar os novos campos; reportar cobertura/HOLD por limite e preservar dados, sem espera obrigatória D054.

TUI mostra identidade/horários/saúde, carteira/posições/fills/curvas, decisão/gates, memória/custos e eventos. Desconexão/estado antigo explícitos, sem inferência por renderização. SQLite canônico; JSONL/exports reconstruíveis, registro de endereços sem saldos.

Validar offline, integrações disponíveis, backup/restore, SIGTERM/crash/container e duas sessões/limites. D054: usuário define a duração da amostragem e solicita análises; atualizações não exigem esperar ou recomeçar 24h. Preservar histórico e distinguir versões, reinícios, lacunas e cobertura nas análises. O observador é opcional e não supervisiona o motor. Homologação após evidências; não alegar conexões/testes não feitos. D056 planeja swing/scalping/day trade após revisar o core; hold e HTML ficam para depois. Transferência automática integra V1, separada da memória local e validada conforme [contrato](TRANSFERENCIA_APRENDIZADO.md).

Acesso remoto por HTTPS/WSS com token/2FA; perda de conexão/expiração de token não para motor. Publicação automática no catálogo mantém proveniência/cutoff; insuficiência/falha deixa transferência inativa, sem perder memória local. Ver [plano](PLANO_DESENVOLVIMENTO_V1.md) e [status](STATUS_DESENVOLVIMENTO.md).
