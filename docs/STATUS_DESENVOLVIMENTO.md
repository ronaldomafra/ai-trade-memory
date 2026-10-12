# Progresso da V1

**Estado 12/10/2026:** núcleo contábil e motor contínuo implementados/testados; JEV integrado com validação offline. Transferência, REST/auth e WS implementados; TUI integrada e testada localmente. Aceite externo/24h pendente. Artefato preexistente de MCP não é suíte do bot.
[Plano](PLANO_DESENVOLVIMENTO_V1.md) · [Contrato](SPEC.md).

| Etapa | Estado | Evidência |
| --- | --- | --- |
| E00 Preparação | Concluído | Projeto/lock/config/CLI/lint/testes; [evidência](relatorios/VALIDACAO_E00_E01.md). |
| E01 Marco 1 | Concluído | Broker/risco/SQLite/ledger/restore/locks/projeções; 55 testes. |
| E02 Marco 2 | Concluído | WS/REST real, ciclos/risco, retomada Docker e 79 testes; ver relatório E02. |
| E03 Marco 3 | Em andamento | Adaptador/orçamento/projeções integrados; 98 testes. Smoke real respondeu 401; sucesso autenticado pendente. |
| E04 Marco 4 | Concluído | Labels/90s, dedupe/origens, memória 30/50/60d, dataset opcional/atomicidade/restore; 110 testes. |
| E05 Marco 5 | Em andamento | Filtros, associação conservadora, seleção após qualidade, deltas e janela configurada testados; ver revisão E05/E11. Unidades Gamma e semântica real pendentes. |
| E06 Docker | Concluído | Lifecycle validado, Docker BTC/ETH, reinício/volume, backup/restore consistente; 130 testes. |
| E07 Transferência | Concluído | Catálogo/outbox, normalização relativa, sombras prospectivas, gates/score/restore; 137 testes. |
| E08 REST/auth | Concluído | Gateway/Argon2/TOTP/tokens/escopos/REST/datasets/Docker; ensaio local real e relatório E08/E09. |
| E09 WebSocket | Concluído | Auth/replay/seq/limites/resync, cliente com backoff/refresh; WS real/revogação testados. |
| E10 TUI | Concluído | Login/wizard/dashboard/datasets/resize, criação ETH e import/export reais; relatório E10. |
| E11 Integração/24h | Em andamento | 191 testes; smoke integral, wheel/Docker, retomada, backup/restore e dataset real. Observação final 24h iniciada; relatório E05/E11. |

Estados: Pendente, Em andamento, Concluído, Bloqueado externo. Concluído exige entregáveis/testes; aceite obrigatório faltante mantém etapa aberta, mesmo com código pronto.

## Registro por etapa

Acrescentar data/versão, arquivos, comandos/resultados, testes, artefatos, pendências e próxima ação. Não colocar credenciais, aprovação presumida ou evidência fictícia.

## Pendências reais

- JEV autenticado: chave do ensaio rejeitada (401); Marketaux adiado pelo usuário.
- Polymarket: Gamma/CLOB/Data acessíveis; seleção/associação conservadora testadas. Unidades monetárias Gamma e classificação com resposta JEV válida ainda em validação E05.
- Hospedagem pública/TLS real não realizada; integração >=24h iniciada, ainda não concluída (E11).
- Transferência: fixtures prospectivas passam; ACTIVE/rentabilidade real exigem dados posteriores suficientes.

Espera por dados não justifica labels fabricados. Testes offline não são integração autenticada.

## 12/10/2026 — E00/E01

Implementados projeto/lockfile, configuração imutável/paper-only, portas/bootstrap, broker Decimal, risco diário persistido, SQLite/UoW/migration, sessões/lease, CLI offline e projeções. Testes escritos antes dos módulos críticos: 55 passam, incluindo crash transacional, disputa de duas conexões, retomada, proteção pendente, BTC/ETH e JSONL truncado. Lint/formatação e build verificados. Leitura real de exchangeInfo BTCUSDT sem autenticação; nenhuma inferência OpenRouter ou ordem real.

Próxima ação: E02, indicadores Wilder/EMA/MACD/ATR/volume com cutoff, candles/quotes WS-REST, estratégia A e ciclos/restart. Dataset inicial selecionado permanece bloqueado até importer E04; motor/run ainda não disponível. Escopo de smoke atual: E01_ACCOUNTING, explícito e sintético.

## 12/10/2026 — E02 parcial

Implementados Candle/intervalos/validação, filtros de fechamento/disponibilidade e gaps; EMA, RSI/ATR Wilder, MACD, volume relativo e retornos 1/4/16; tendência em 1h fechada; tercis ATR% sobre até 200 observações anteriores. Estratégia A reproduz regras/limiares da SPEC. Convenção explícita para série RSI constante: 50. Casos conhecidos de Wilder e referência independente pandas passaram. Proteção adicional: prazo de entrada conta desde o fechamento do candle, não desde uma inferência iniciada tarde.

Verificação atual: 67 testes passaram; ruff check/format limpos. E02 permanece aberta: faltam REST klines/bookTicker, parser/stream WebSocket, armazenamento/ciclos/orquestrador/scheduler, run/retomada e Docker. Próxima ação concreta: completar transporte público e migration de candles/snapshots/decision_cycles, conectando FeatureEngine/TechnicalStrategy ao motor com risco concorrente. Sem B/C mockados em execução de produção; até E03, manter HOLD explícito por IA indisponível.

## 12/10/2026 — E02 e E03

E02: dados públicos Binance REST/WS reais, engine independente do cliente, ciclos/decisões persistidos, proteção durante inferência, fallback/recovery, CLI run/backfill/API privada. Docker construído e engine_btc iniciou/restaurou/encerrou preservando a auditoria (zero fills durante janela curta). Corrigido diagnóstico espúrio em SIGTERM. 24h permanece em E11.

E03: Decisions estruturada, probabilidades/confidence separados, duas tentativas transitórias, reserva compartilhada SQLite, custos Decimal/unknown, circuito de credencial persistido, conciliação local/global e compartilhamento B/C. 98 testes passaram. Chamada explícita real em 12/10/2026 respondeu HTTP 401, custo desconhecido: não afirmar integração autenticada válida. Credencial disponível foi rejeitada; manter circuito fechado até troca local. Marketaux fica para preenchimento posterior pelo usuário; testes offline não dependem do token.

## 12/10/2026 — E04

Outcome Evaluator integrado ao engine/risco e ao ciclo, famílias de entrada/manter-vender 4/16, primeiro bid real em até 90s, UNAVAILABLE sem interpolação, disponibilidade estrita por origem e deduplicação A/B/C. Memória local com hierarquia 30/50, 60 dias, Beta(1,1), Wilson/hipótese de independência, três padrões no máximo e B sem histórico. Dataset JSONL schema/hash/protocolo/origens, arquivo acumulativo imutável, importação atômica somente antes da primeira decisão, arquivo aceito não relido na retomada; import não altera carteiras. Fixtures não entram no acervo reutilizável/estatísticas operacionais. Comandos import-learning/export-learning/evaluate-outcomes e diagnósticos adicionados. 110 testes passaram. Ainda não há labels reais maduros nesta janela curta. Transferência automática/catálogo é E07; fonte estrangeira fica no acervo, fora da memória local.

## 12/10/2026 — E05 parcial

121 testes passaram, lint e build limpos. Implementados sanitização/URLs/candidatos por ativo, adaptadores Marketaux/RSS, reserva/cache/quota compartilhada (100 requests/dia; três itens/primeira página da conta gratuita, conforme documentação oficial), versões/datas e classificação com cutoff no cache. Parser Gamma/resultados/tokens/evento, livro CLOB Decimal, spread/profundidade, filtros temporais/limites e descoberta persistida em até cinco páginas, sem trading SDK/credenciais financeiras. Ainda falta orquestrar coleta/classificação e fatores no motor, gates completos e relatórios.

Proxy local funcionou: documentação oficial, Gamma, CLOB /book e Data API v2 /trades retornaram HTTP 200. API v2 documenta size/volume bare em cotas e campos _usdc em USD. Gamma bare liquidityClob/volume24hrClob não têm unidade monetária suficientemente explícita nas referências lidas; o parser mantém GAMMA_METRIC_UNITS_UNVERIFIED para impedir filtro USD indevido. Concluir verificação do contrato de unidade antes de habilitar sinais quantitativos; não presumir dinheiro/cotas intercambiáveis. RSS Cointelegraph retornou 30 itens válidos; CoinDesk ficou indisponível. Marketaux autenticada adiada a pedido do usuário. Proxy está somente no .env local ignorado pelo Git, sem valores em código/docs/logs.

## 12/10/2026 — E05 integração ao motor

ContextService paralelo ao risco publica versões imutáveis no SQLite; coletas compartilhadas/cache/quota, classificação Decisions por conteúdo/destino/perfil/critérios, fatores compactos B/C e snapshots por cutoff. Gates distinguem vazio verificável, falha/pendência/truncamento, premissa conflitante/incerta e fundamento técnico independente. Proposta original JEV permanece BUY mesmo quando validação resulta HOLD; saída financeira/proteção continuam separadas. Relatórios incluem C−B/B−A, cobertura/memória, chamadas associadas sem duplicar cobrança e estados externos. 127 testes passam, incluindo descoberta de 500 mercados em cinco solicitações compartilhadas entre pares após reabertura do cache.

Execução nativa de 35s com coleta ativa: quote fresca, clock VERIFIED, auditoria OK/zero fills, parada limpa. Não ocorreu candle novo. Credencial JEV rejeitada mantém classificações indisponíveis; nenhuma compra B/C é permitida sem contexto elegível. Gamma/CLOB/Data acessíveis pelo proxy, mas unidade monetária Gamma bare ainda não verificada e excluída. Não marcar interpretação/predição real como validada. Próxima ação: consolidar E05 e completar E06 lifecycle/backup/Docker paralelo, preservando essas limitações e validações pendentes.

## 12/10/2026 — E06

DockerRuntime server-side com identidade/labels validados, argumentos fixos sem shell, imagem comum, env whitelist, endpoint privado loopback, start/stop idempotentes. CLI start-engine/stop-engine/engine-status/backup/restore-backup. Backup online SQLite e hashes/ledger, artefatos reconstruíveis e arquivos operacionais individualmente consistentes; nunca presumir atomicidade entre bancos. Restauração não sobrescreve sessão ou orçamento existente; recuperação operacional incerta bloqueia IA/Marketaux no dia UTC corrente.

130 testes passaram. Imagem ec1ce128e157 construída. Compose session-btc e session-eth ficaram healthy com WS/quotes reais; engine_eth reiniciou sem reset. Em 17:15 UTC processaram um candle real e três decisões cada, sem fills, auditoria OK, orçamento global preservado. Runtime dinâmico verification-runtime iniciou com REST somente loopback e foi parado limpo. Backup online session-btc em data/backups/e06-session-btc, restaurado isoladamente em /tmp/poc-e06-restored com auditoria OK. São ensaios curtos, não 24h. Motores de verificação serão parados antes de atualizar schema/imagem de E07; observação final 24h usa sessões próprias/versionadas em E11.

## 12/10/2026 — E07

Catálogo estatístico independente, publicação incremental/outbox/ack e reconciliação idempotente sem backdating; fixtures/futuro rejeitados. Normalizador preço/EMA, RSI, ATR% e volume relativo; seleção determinística em rodadas por símbolo, 50 não neutros e até 200, sem escolher vencedores. Fonte estrangeira não altera contagens locais. Sombras C por ciclo/família/horizonte, p e baseline congelados antes de outcome, validação regional nas últimas 30 não neutras com intervalos não sobrepostos/60d, Brier estritamente melhor. Estados/gates/erros persistidos, locais prioritários/três padrões totais, nenhuma chamada JEV por publicação/score.

137 testes passaram; fixtures demonstram NO_SOURCES/VALIDATING/ACTIVE/SUSPENDED/UNAVAILABLE, prioridade local, cutoff, choque de catálogo/replay e recuperação sem disponibilidade histórica fabricada. Testes usam dados sintéticos exclusivamente em temporários pytest; não há prova de transferência rentável ou ACTIVE real. Execução nativa com catálogo vazio e Binance real por 12s: auditoria OK/zero fills, parada limpa, clock/quotes válidos. CLI transfer-status e CSV de sombras/estados disponíveis. Outcome UNAVAILABLE agora guarda evaluated_at e mantém matured_at NULL. Próxima etapa E08, preservando módulos completos e validações externas pendentes.

## 12/10/2026 — E08/E09 e TUI parcial

REST/auth/datasets/lifecycle, banco readonly, WS autenticado com replay/cursor/resync/limites e cliente com backoff/refresh implementados. 162 testes passam; ruff limpo. Gateway nativo real autenticou, iniciou motor Docker e entregou snapshot/live; revogação fechou WS e invalidou REST. SIGTERM do gateway/logout e parada do controle em container preservaram motor. Imagem do controle/socket/GID/mapeamento de volumes e Caddyfile validados localmente; sem hospedagem pública. Relatório E08/E09 e contrato API_CONTROLE_V1 disponíveis.

TUI Textual usa apenas REST/WS: login/2FA, sessões, wizard de defaults/ajustes/dataset/transferência, dashboard/candles/equity/posições/fills/decisões, memória/fontes/transferência, logs/filtro/ajuda/teclado e configuração readonly. Testes de login/resize/troca BTC-ETH/wizard e saída; captura real da sessão gateway-runtime-btc com três carteiras. Concluir percurso integrado de criação/dataset e testes de falhas antes de fechar E10. Aceite 24h segue pendente.

## 12/10/2026 — E10 concluído localmente

TUI/cliente REST-WS e fluxos integrados; criação real ETH sem dataset pelo wizard, Docker iniciado, três carteiras, 800 candles aquecidos/200 na UI, clock/quote válidos e auditoria OK. Import/export real via TUI na sessão ETH preparada preservou carteiras; dataset vazio porque não havia exemplos válidos disponíveis. Capturas SVG e relatório VALIDACAO_E10. Logout/quit não pararam motor. Suíte atual: 166 testes, incluindo rejeição de escrita em conexão readonly, upload chunked limitado antes do parser e falhas REST/WS/identidade na TUI. Atualização da cotação distinguida do recebimento do stream. Próximo: consolidar E05 e iniciar E11/smoke integral/ensaio prolongado; nenhuma conclusão de 24h, JEV válido ou rentabilidade.

## 12/10/2026 — revisão E05 e E11 em execução

191 testes passaram, ruff/format/build limpos. Notícias respeitam a janela configurada na consulta, cache, candidatos, fatores e validade do recorte vazio. Deduplicação preserva aliases/proveniência disponível no cutoff e distingue edições diárias. Datas de ocorrência são selecionadas apenas de evidência explícita com fuso; relação temporal é recalculada localmente, sem inferência por candle. Livros/negócios compartilham slots persistidos; variações de 5/60m exigem referências realmente observadas, sem fabricar zero/histórico.

Evento Polymarket não é associação automática: somente pergunta e regras completas literalmente iguais verificam a mesma proposição; conjuntos amplos ficam pendentes. Conteúdo completo/IDs/evidência/versionamento permanecem no cache. Filtros precedem vagas; seleção final por relevância/tempo/qualidade e tetos é registrada, preços entre revisões não promovem novos IDs. Paginação para quando uma página não avança. Unidades Gamma continuam UNVERIFIED: CLI/SDK oficiais não bastaram para comprovar semântica dos campos CLOB/janela. Não liberar sinais por suposição.

Smoke integral BTC/ETH: oito ciclos, 24 decisões, quatro fills B/C, 45 labels maduros e três UNAVAILABLE, oito ciclos duplicados ignorados e ledger OK; inferência exclusivamente simulada/sem rede. Wheel instalado em venv limpa e executado fora do checkout com YAML explícito. Docker core/controle construídos; Compose válido. Reinícios/recriações de acceptance-v1-btc/eth preservaram hashes financeiros/configuração/27 decisões e watermarks. Backup online restaurado em /tmp/poc-e11-restored com auditoria OK e trava de orçamento recuperado.

Dataset real BTC exportou cinco exemplos maduros/15 origens. Importação inicial em acceptance-v1-import-eth (apenas preparada) manteve cada carteira em 100 USDT; cinco exemplos BTC arquivados, zero exemplos locais ETH. Reexportação preservou a ancestralidade, sem duplicação. Import aceito não equivale a transferência ACTIVE.

Observação preliminar: 130 frames/~2h09, zero falhas contábeis ou amostras indisponíveis; quatro alertas eram diferença entre horário do frame e leitura da segunda sessão, um alerta coincidiu com reinício. Registros preservados em data/acceptance/v1-20261012. Observador corrigido mede idade após leitura; observação final da imagem 5336fbd8c0bd iniciou em **12/10/2026 21:57:09 UTC**, em data/acceptance/v1-20261012-final, com uma amostra inicial de ETH ainda em retomada. Meta mínima **13/10/2026 21:57 UTC (18:57 Brasília)**. O estado COMPLETED indica tempo decorrido e exige revisão das amostras; não conclui automaticamente o aceite. JEV 401/Marketaux adiado/Gamma/TLS público continuam pendências.

Detalhes e caminhos: [VALIDACAO_E05_E11.md](relatorios/VALIDACAO_E05_E11.md). Não marcar E03/E05/E11 ou V1 completa antes das validações faltantes.
