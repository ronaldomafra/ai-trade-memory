# Progresso da V1

**Estado 14/10/2026 — D060/SPEC 1.58:** cadastro genérico de perfis, motor parametrizado, aprendizado V2 e TUI disponíveis. D058: instruções JEV em inglês; D059: orçamento por bot; D060: prazo SCALPING aceita até 15s. **303 testes completos passando.** Perfil `scalping_zec_v1` revisão 2 publicado com janela 15s e timeout 6s; nova sessão **`zec-scalping-02` RUNNING desde 21:45:58 UTC (18:45:58 Brasília)**. Sessões ZEC anterior e `eth-01` paradas, histórico e backups preservados. P09 ainda depende de decisões/operações reais e medições de latência/cobertura; testes não provam eficácia financeira. [Guia](GUIA_PERFIS_BOTS.md). D054 mantém a duração da amostragem sob controle do usuário. O histórico abaixo preserva estados anteriores com suas datas.
[Plano](PLANO_DESENVOLVIMENTO_V1.md) · [Contrato](SPEC.md).

| Etapa | Estado | Evidência |
| --- | --- | --- |
| E00 Preparação | Concluído | Projeto/lock/config/CLI/lint/testes; [evidência](relatorios/VALIDACAO_E00_E01.md). |
| E01 Marco 1 | Concluído | Broker/risco/SQLite/ledger/restore/locks/projeções; 55 testes. |
| E02 Marco 2 | Concluído | WS/REST real, ciclos/risco, retomada Docker e 79 testes; ver relatório E02. |
| E03 Marco 3 | Concluído | Adaptador/orçamento/projeções e decisões estruturadas; smoke real válido em 13/10, modelo/ID/usage.cost auditados. Atualização da sessão ETH e aceite prolongado seguem E11. |
| E04 Marco 4 | Concluído | Labels/90s, dedupe/origens, memória 30/50/60d, dataset opcional/atomicidade/restore; 110 testes. |
| E05 Marco 5 | Concluído | Notícias e quatro fatores Polymarket reais na ETH; descoberta por moeda, unidade Gamma v1 verificada, associação/cutoff/seleção conservadores e testes. Cobertura parcial explícita; acompanhamento prolongado em E11. |
| E06 Docker | Concluído | Lifecycle validado, Docker BTC/ETH, reinício/volume, backup/restore consistente; 130 testes. |
| E07 Transferência | Concluído | Catálogo/outbox, normalização relativa, sombras prospectivas, gates/score/restore; 137 testes. |
| E08 REST/auth | Concluído | Gateway/Argon2/TOTP/tokens/escopos/REST/datasets/Docker; ensaio local real e relatório E08/E09. |
| E09 WebSocket | Concluído | Auth/replay/seq/limites/resync, cliente com backoff/refresh; WS real/revogação testados. |
| E10 TUI | Concluído | Login/wizard/dashboard/datasets/resize, criação ETH e import/export reais; relatório E10. |
| E11 Integração/amostragem | Em andamento | Integrações JEV/notícias/Polymarket reais, Docker/retomada, backup/auditoria. D054: revisão do período escolhido pelo usuário, sem mínimo de 24h. Histórico do observador abaixo. |

Estados: Pendente, Em andamento, Concluído, Bloqueado externo. Concluído exige entregáveis/testes; aceite obrigatório faltante mantém etapa aberta, mesmo com código pronto.

## Registro por etapa

Acrescentar data/versão, arquivos, comandos/resultados, testes, artefatos, pendências e próxima ação. Não colocar credenciais, aprovação presumida ou evidência fictícia.

## Pendências reais

- Escolher/configurar/publicar um perfil e iniciar nova sessão com o usuário; medir latência real, cobertura das fontes e execução de entradas/saídas. Templates não comprovam rentabilidade ou vantagem de C sobre A/B.
- Revisar amostras no período escolhido pelo usuário, cobertura, custos e invariantes, distinguindo versões/lacunas. Primeiro candle com notícias e Polymarket confirmado às 22:30 UTC: B/C HOLD/JEV_CHOICE, HTTP 200 e chamada física compartilhada.
- Cobertura Polymarket parcial por teto/temas; grupos ambíguos e dados fora dos filtros continuam excluídos. Não há obrigação de produzir fator em toda coleta.
- Hospedagem pública/TLS real não realizada (E11); duração da observação definida pelo usuário, sem espera mínima.
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

## 13/10/2026 — operação inicial e colagem TOTP

Após reset solicitado, bancos/artefatos operacionais e containers anteriores foram removidos; o ensaio de 24h anterior não foi concluído. Usuário preparou/iniciou eth-01/ETHUSDT e cadastrou o proprietário. Motor confirmado com WS ativo, quote fresca, clock VERIFIED e auditoria OK. Login da TUI passou à etapa 2FA após iniciar o controle.

Campo TOTP agora aceita colagem de um código completo, normaliza espaços/quebras de linha e preserva zeros iniciais, substituindo a tentativa anterior. Rejeita comprimento inválido, texto misturado, dois códigos ou dígitos não ASCII; desabilitado antes do login. Senha/código continuam ocultos e são limpos após envio. Interface/guia informam Ctrl+Shift+V para a colagem externa do terminal; Ctrl+V do Textual usa clipboard interno. Nenhuma leitura de seed ou geração automática de 2FA pelo cliente.

192 testes passaram, ruff/format limpos. Teste de evento Paste/clipboard/login cobre as duas fases, normalização/rejeições, substituição e limpeza, sem comandos de motor. Atualização usa o cliente nativo do checkout; reabrir a TUI carrega a correção. Sem necessidade de reiniciar motor/controle para esse ajuste do cliente. Pendências de integração/aceite permanecem explícitas; screenshot de Chat Completions não valida Decisions JEV.

Após nova tentativa, usuário confirmou código de seis números e Ctrl+Shift+V.
Diagnóstico somente leitura confirmou controle acessível e últimos desafios
vencidos, sem 2FA bem-sucedido; não comprova causa da falha de colagem no terminal.
TUI passou a respeitar expires_at do desafio, retornar à senha quando expira e
recusar envio de código vazio/incompleto sem consumir tentativa no servidor.
Feedback mostra apenas quantidade de números recebidos; rejeições de colagem
têm orientação específica.

Botão Colar código oferece alternativa ao terminal: leitura explícita local via
Tk em subprocesso isolado/limitado, sem shell, persistência, log ou leitura de
seed. Conteúdo diferente de um único código ASCII de seis números não é devolvido
ao cliente; desktop/Tk ausentes mantêm alternativa pelo terminal. Tk iniciou
localmente sem leitura da área real. Testes usam clipboard sintético e cobrem
botão, falha, zeros iniciais, cancelamento do subprocesso e prazo informado pelo
servidor; colagem real do usuário ainda depende da próxima tentativa.
Suíte completa: 200 testes em 25,32s, ruff/format limpos; aviso de depreciação da
dependência Starlette/TestClient. Motor ETH e controle permaneceram em execução.

## 13/10/2026 — correção de contexto e autenticação JEV

Sessão eth-01 produzia HOLD B/C com AI_CONTEXT_TOO_LARGE antes do envio:
Orchestrator carregava o snapshot de auditoria inteiro, inclusive centenas de
mercados rejeitados, no state do JEV. compact_trade_state mantém todos os fatores
selecionados/evidência/conflitos/tempos/fundamentos, estados de fontes e cobertura;
listas de pendências/classificações falhas viram contagens por motivo. Auditoria
e gates locais conservam snapshot completo. B/C equivalentes continuam com uma
chamada compartilhada; bounds 30/32 KB e critérios de BUY permanecem.

Snapshot real histórico com 321 pendências: state de 56.949 bytes passou a gerar
payload de 3.205 bytes, calculado offline sem inferência retroativa. Testes com
500 candidatos comprovam envio compacto, conservação da evidência, ausência de
mutação, compartilhamento/custo único e veto de BUY sem cobertura.

Chaves anteriores do arquivo/container devolveram 401; ambientes divergiam.
Credencial fornecida pelo usuário salva apenas no .env local (0600), sem valores
nos artefatos. GET /api/v1/key retornou 200. Novo CLI check-openrouter consulta a
autenticação sem inferência; --recover-auth só remove 401 anterior da mesma chave
após sucesso, preservando orçamento/histórico, outros circuitos e falhas mais novas.

Uma chamada real smoke-openrouter sem broker retornou error_code=null,
validation=JEV_CHOICE, modelo typesafe/jev-1.13-20260917,
provider_generation_id=gen-dec-1791907407-VRum5b9v8rvZstjz9poc,
ai_call_id=3866057f07c16d0dcbd8147ec6001186b33c1682d2b98ff0f21a502921da4ff1.
usage.cost=0.000029652 USD; 706 tokens de entrada/102 saída. Reserva/custo/modelo/ID
persistidos no orçamento operacional. Um erro antigo continua com custo desconhecido;
não foi apagado nem convertido em zero. Validar classificação/ciclos reais após atualizar.

Dashboard distingue quantidade de chamadas JEV/motivo B/C, última coleta e número
de fatores utilizáveis: coleta bem-sucedida pode coexistir com unavailable.
210 testes passaram em 25,29s; ruff/format/diff limpos. Auditoria atual ETH OK/zero
fills. Imagens construídas: core 2bf92d96f962 e controle 1ec4ea31dbda; config-check
e CLI da imagem verificados sem rede. Containers em execução continuam anteriores:
usuário executará backup/parada/recriação/retomada conforme guia, preservando dados.
E03 validado; E05 Gamma/classificação de fatores e E11 24h/TLS continuam pendentes.

## 13/10/2026 — reparo aplicado à sessão ETH e retomada real

Às 21:16 UTC, motor atualizado estava em reinício automático com Conflicting
finalized candle e credencial diferente do .env. Comparação pública de 800 barras
identificou uma divergência: ETHUSDT/15m, abertura 15:00 UTC, mesmos OHLC e janela;
volume original 1639.901, recebido às 15:15:01.485617 UTC, contra revisão REST
1641.2727. Motor parado explicitamente; backup íntegro em
data/backups/eth-01-repair-20261013-1827 (auditoria OK).

save_candle conserva a primeira observação/janela/available_at. Revisões apenas
de volume geram CANDLE_VOLUME_REVISION_IGNORED idempotente e retornam duplicata,
sem novo ciclo/inferência/fill. Conflitos de OHLC/janela continuam rejeitados;
não existe tolerância numérica arbitrária nem atualização retroativa de features.
Limitação: volume revisado não substitui o originalmente recebido nessa V1.

Credenciais de provedores no .env local agora prevalecem sobre exports antigos;
ambiente continua disponível quando não há arquivo. POC_DATA_DIR mantém override
explícito para volumes/restore. POC_ENV_FILE permite arquivo próprio, com falha
se ausente. Compose carrega .env montado readonly, impedindo que interpolação de
uma chave antiga do terminal configure o controle. Motores dinâmicos continuam
recebendo somente valores carregados pelo servidor, sem segredo em argv.

215 testes passaram em 28,73s; ruff/format/Compose/diff limpos. Casos novos cobrem
retomada/revisão de volume, evento único, preços conflitantes, ausência de replay,
arquivo versus export, caminho explícito e falha se o arquivo faltar.
Imagens construídas/aplicadas: core 63126db6d2eb, controle 2b242ef9a0bc.
eth-01 retomou às 21:34 UTC; controle recriado na porta 18080, auth/bancos preservados.
Uma reinicialização controlada às 21:35 UTC passou: RUNNING, WS conectado, clock
VERIFIED, quote fresca, last_error=null, zero reinícios automáticos. Candle original
e um único evento de revisão preservados. Hashes/contagens de ledger (3), fills (0)
e decisões (69) iguais aos anteriores; auditoria OK, cada carteira mantém 100 USDT.

Cinco chamadas context_classification reais da eth-01 retornaram HTTP 200, modelo
JEV, custo total observado 0.000553140 USD, sem custo desconhecido. Quatro fatores
de notícias utilizáveis; um candidato permanece com relação ao ativo indeterminada.
Marketaux PARTIAL/free plan e RSS Cointelegraph COMPLETE responderam; CoinDesk 308.
Nessa correção, Polymarket ainda estava unavailable/descoberta parcial, sem fatores
elegíveis e sem liberação das métricas Gamma. Posteriormente, candles reais às
21:45/22:00/22:15 UTC retornaram HTTP 200 e HOLD/JEV_CHOICE para B/C, com chamada
física compartilhada; sem trades retroativos. A correção Polymarket está abaixo.

## 13/10/2026 — Polymarket utilizável e novo ensaio de 24h

[Relatório técnico](relatorios/VALIDACAO_POLYMARKET_20261013.md). Descoberta por
tags da moeda e juros, incluindo essas leituras no teto de cinco. Gamma v1 usa
liquidityNum/volume24hr com escala monetária sustentada nas referências oficiais;
aliases CLOB sem contrato continuam excluídos. Associação de faixas exige regras
completas idênticas, ativo e objeto/período/prazo correspondentes. Corrigido cutoff
anterior à resposta que descartava registros recém-coletados, sem backdating.
Pisos de qualidade/orçamento e configuração original permanecem inalterados.
Expiração considera também horário original do livro e recência do último negócio.

230 testes passaram em 28,58s; Ruff/format/diff limpos. Backup online em
data/backups/eth-01-before-poly-20261013-2222. Imagens finais: core 66138fae36c8,
controle 720e65543765, aplicadas às 22:28 UTC. Comparação de hashes confirmou
ledger (3), fills (0), decisões (78) e ciclos (26) preservados; config_hash igual.
Auditoria/invariantes OK, quote fresca, WS conectado, clock VERIFIED,
last_error=null e zero reinícios automáticos.

Descoberta: 227 mercados brutos, 222 candidatos por ativo/temas; quatro
classificações Polymarket JEV reais HTTP 200, três fatores selecionados:
5407319 e 5407322 (ETH acima de 2.400/2.500 em 14/10), 5432687 (acima de 2.300
em 15/10). Ambos os lados dos livros passaram em profundidade, spreads <=2 pp
e negócios recentes; duas faixas da mesma ocorrência, dentro do teto aprovado.
Confiança/direção/intensidade indeterminadas permanecem explícitas, sem inventar
sinal favorável. Quatro fatores de notícias também disponíveis. Cobertura parcial
não comprova ausência global; deltas começam UNAVAILABLE sem histórico suficiente.
Na revisão final, quatro fatores: 5407308/5407319 (14/10) e 5432687/5432689
(15/10), no máximo duas faixas por ocorrência. Seleção varia com os livros;
não é uma whitelist. Custo observado da sessão: 0.001601334 USD, 13 chamadas
físicas, zero custos desconhecidos; orçamento global preservado.

Observador detached PID 3976866, somente leitura, amostras a cada 60s:
data/acceptance/eth-poly-20261013T222907Z. Início exato 13/10/2026 22:29:07 UTC
(19:29:07 Brasília); término previsto 14/10/2026 no mesmo horário. Arquivos
observation.json, samples.jsonl e validation-at-start.json documentam progresso,
fatores/IDs/custos e baseline. Primeira amostra sem violações, indisponibilidade
ou degradação. Fechar TUI não para bot/observador; manter máquina e Docker ativos.
Não declarar o teste concluído antes do prazo e da revisão da evidência.
A coleta preparatória em eth-poly-20261013T222513Z foi interrompida para aplicar
a expiração final; suas três amostras não contam como execução de 24h.

Primeiro fechamento após a versão final: 22:30 UTC, ciclo COMPLETED e três
decisões novas, sem replay. Requisição real incluiu quatro notícias e quatro
fatores Polymarket; HTTP 200, modelo typesafe/jev-1.13-20260917, custo 0.000417228
USD. B/C compartilharam chamada e retornaram HOLD/JEV_CHOICE; A HOLD técnico.
Payload 20.589 bytes, dentro do limite; auditoria OK/zero fills. Evidência em
first-candle.json no diretório do ensaio. Duas amostras do observador sem
violações, indisponibilidade ou degradação; 24h ainda em andamento.

## 14/10/2026 — retomada da janela contínua de 24h

Verificação somente leitura encontrou motor/controle ativos, sem reinícios;
WS conectado, clock VERIFIED, cotação fresca, auditoria/invariantes OK.
Kernel confirmou suspensão do host de 13/10 às 20:53:49 até 14/10 às 07:14:27
de Brasília. A lacuna entre amostras foi de 37.297s; isso não comprova operação
contínua, mesmo com contadores antigos sem degradação. O observador antigo
usava CLOCK_MONOTONIC, que não conta suspensão Linux.

Observador nativo corrigido para medir duração UTC e interromper, sem parar o
motor, se uma lacuna exceder max(120s, duas cadências) ou o relógio retroceder.
Esses casos não terminam como COMPLETED. 232 testes passaram em 27,16s;
Ruff/format limpos, incluindo suspensão de 25h e salto de relógio para trás,
sem alteração do banco. Nenhuma regra financeira, configuração ou imagem dos
motores foi modificada nesta etapa.

Novo observador independente PID 4046287 em
data/acceptance/eth-24h-20261014T112850Z, amostragem 60s, iniciado em
14/10/2026 11:28:50 UTC (08:28:50 Brasília); término previsto 15/10 no mesmo
horário. systemd-inhibit mantém sleep:idle em modo block durante sua vida;
aquisição confirmada no sistema, sem mudança permanente da configuração.
Fechar TUI/terminal não encerra o observador. Manter host ligado e Docker ativo;
o inibidor não protege contra desligamento forçado ou falta de energia.

O observador anterior PID 3976866 foi encerrado explicitamente, preservando
todos os artefatos como INTERRUPTED. Bot eth-01 permaneceu rodando, banco,
histórico e carteiras preservados. Primeira amostra nova: auditoria/invariantes
e feed OK, notícias com quatro fatores e Polymarket com dois, ambos available.
observation.json/samples.jsonl registram progresso; validation-at-start.json
registra início/prazo, proteção, baseline e limites. COMPLETED indica apenas
tempo decorrido; ainda é preciso revisar fontes/custos/invariantes para aceite.

## 14/10/2026 — Dashboard TUI, alteração exclusiva de apresentação

Gráfico em largura total; marcadores de avaliação e fills confirmados, faixas
por carteira, coincidências e eventos após último candle fechado separados.
Seletor/clique consulta resumo do ciclo, sem misturar carteiras pendentes com
outro ciclo. Motivos/proposta/execução/probabilidades/confiança/memória e
indicadores vêm dos registros existentes. Notícias/Polymarket mostram o último
registro recebido da API, independente da decisão selecionada, com datas,
classificação e histórico/vencimento explícitos. Troca de sessão limpa tudo.

Somente src/poc/adapters/inbound/tui.py, tui_charts.py e novo tui_presenters.py
foram alterados em código nesta tarefa; testes e documentação acompanham.
Nenhuma alteração em core, modelo, questionário, API, schema, config financeira,
coletas ou serviços Docker. Usar contexto recente não demonstra influência
causal do item sobre a decisão. Recorte da API (20 decisões/20 fills) continua
limitando a cobertura histórica, sem afirmar ausência de operação fora dele.

Testes de TUI verificam proposta bloqueada sem marcador de compra, operações
coincidentes por carteira, eventos após fechamento, seleção/atualização de
histórico, ciclo parcial, RSI histórico versus fonte recente, reset entre
símbolos e terminais 150/70 colunas, sem comandos de gestão. Prévia offline com
snapshot real somente leitura em data/diagnostics/tui-20261014T115808Z:
dashboard.svg/png e dashboard-narrow.svg/png; não é teste de autenticação real
nem nova chamada ao modelo. Atualizar apenas fechando/reabrindo a TUI, conforme
guia; o ensaio de 24h e os containers existentes permanecem em execução.

Verificação final: 236 testes passaram em 31,22s; Ruff/format/diff limpos.
Inspeção Docker confirmou as mesmas datas de início e zero reinícios. Observador
ativo com 32 amostras, zero violações/indisponibilidade/degradação; motor RUNNING,
WS conectado, clock VERIFIED e auditoria OK. Não é conclusão de 24h.

Revisão visual posterior: gráfico movido para o topo do Dashboard; Carteiras
A/B/C e Patrimônio A/B/C agora ficam lado a lado imediatamente abaixo, empilhados
em terminal estreito. Apenas TUI/documentação ajustadas. Os 13 testes de TUI
passaram em 21,38s, incluindo ordem/alinhamento dos painéis e resize. Nova prévia
em data/diagnostics/tui-20261014T121440Z (SVG largo/estreito).

## 14/10/2026 — D053, core preparado sem aplicação ao ensaio

Solicitação explícita: implementar configuração/habilitação do limite financeiro
sem executar/aplicar atualização durante a sessão atual. Mantidos containers,
imagens, .env, configuração/capital/ledger/histórico e dados de orçamento reais.

GlobalAICostLimit é uma política operacional separada de Config/hash da sessão:
booleano estrito, Decimal positivo finito e sem teto fixo de cinco centavos na
política explícita. Default legado continua habilitado em US$ 0,05/dia UTC.
SQLite operacional passa a suportar histórico versionado de alterações e recibo
por reserva com política/limites efetivos, lidos dentro da transação global.
Ajustes não zeram gasto/tentativas; desligar custo conserva a guarda de chamadas,
circuito/bloqueios de recuperação e registro de unknown. Reativar abaixo do gasto
já observado impede novos envios. Métodos novos só criarão tabelas quando a
versão futura for inicializada no orçamento; nenhuma migração foi aplicada agora.

CLI ai-budget consulta/ajusta; GET/PUT /v1/ai-budget exige proprietário global,
PUT com manage/2FA e ambos os campos explícitos. Repetição idêntica é idempotente.
Teto de custo saiu dos overrides remotos por sessão; campo legado da configuração
persistida é mantido como fallback para compatibilidade, sem mudar hashes antigos.
Gestão preparada nesta tarefa é CLI/API; não foi aplicado controle financeiro novo
à TUI conectada ao servidor antigo. Atualização posterior deve abranger todos os
motores/controle compatíveis antes de usar a nova configuração global.

251 testes passaram em 30,96s; Ruff/format limpos. Ensaios apenas em bancos
sintéticos temporários e HTTP mock: aumento acima de US$ 0,05, disable/re-enable,
valores inválidos/float, persistência/restart/rollover, concorrência entre sessões,
limite de chamadas, bloqueio pós-restore, recibos/revisões, uso pelo cliente JEV,
permissões globais/401/403/422 e CLI sem rede. Não foi executada inferência real,
comando novo de orçamento nos dados operacionais, build ou lifecycle Docker.

Verificação por leitura durante a tarefa: banco ativo sem ai_cost_policy e sem
ai_budget_policy_receipts; dia UTC 14/10 continua em 240 chamadas/US$ 0,05.
Observador original PID 4046287 RUNNING, iniciado às 11:28:50 UTC, 93 amostras sem
violações/indisponibilidade/degradação no corte das 13:01 UTC. Inspeções de imagem,
início e contagem de reinícios são preservadas; ver confirmação final da tarefa.

Confirmação final às 13:07 UTC: observador RUNNING/99 amostras, todos os contadores
de falha em zero; banco real ainda sem as duas tabelas novas e com 240/US$ 0,05.
Motor continua na imagem 66138fae36c8/início 13/10 22:28:07 UTC; controle
720e65543765/início 22:28:08 UTC. Ambos com zero reinícios, como no início da tarefa.

## 14/10/2026 — D054, duração da amostragem definida pelo usuário

Removido o requisito de completar ou recomeçar uma janela de 24h para avaliar
resultados ou atualizar serviços. O usuário gerencia o tempo de coleta. Análises
devem usar o período solicitado, mantendo histórico, identificação de versões,
cobertura e eventuais lacunas/reinícios. Relatos anteriores de prazo obrigatório
ficam como histórico, substituídos por D054/SPEC 1.52.

Verificado no código: o observador apenas lê e registra amostras; seu prazo
configurado não bloqueia o motor ou atualizações. Nenhuma mudança de código foi
necessária para retirar essa exigência. O observador existente não foi alterado
ou encerrado nesta tarefa. Não foram executados build, reinício, migração ou
configuração de orçamento; D053 continua com implantação pendente.

Contrato, decisão, plano E11, guia, README e contextos operacionais atualizados.
Verificação documental por busca das exigências antigas e git diff --check;
sem novos testes de código, pois não houve alteração executável nesta tarefa.


## 14/10/2026 — D055, otimização do reaproveitamento das notícias

Implementados dois caches persistentes usando o SQLite de fontes existente:
interpretação individual news_factors_v3, sem pares, e comparação factual
news_conflicts_v1, com uma chamada estruturada por conjunto de duas a cinco
notícias em ordem canônica. Seleção/classificação usa até 600 caracteres do
resumo já coletado e hash do conteúdo disponível, sem artigo integral.

Teste sintético: cinco artigos novos demandam seis chamadas; trocar um artigo
exige duas chamadas adicionais, em vez de cinco reclassificações completas.
Reordenar, repetir leitura e restaurar o classificador reutilizam resultados.
Correção/hash, ativo/modelo/critérios diferentes invalidam apenas as versões
incompatíveis. O questionário Polymarket external_factors_v2 é preservado.

Falha/schema inválido/orçamento na comparação mantém conflito UNDETERMINED e
cobertura parcial, sem aproveitar NO_CONFLICT de outro conjunto. Interpretações
válidas continuam disponíveis; gates de fundamento impedem entrada baseada em
premissa contestada/não verificável. Processamento falho pode ser recuperado
numa nova janela da coleta configurada, com reserva compartilhada e orçamento/
retries existentes, sem repetição por leitura/renderização.

Versões antigas permanecem imutáveis. Fator composto guarda vínculos das etapas
e só fica disponível depois de ambas; cutoff anterior e rollback do relógio não
aproveitam resposta futura. Publicação/primeira observação/valid_until originais
são preservados. Recibos extras permanecem na auditoria e são removidos do prompt
de negociação, preservando fator/evidência/conflito/status e disponibilidade.

264 testes passaram em 29,11s; Ruff check e format limpos, git diff --check limpo.
Incluídos 13 testes novos: reutilização/reordenação/restart, artigo corrigido,
identidades/versões, falha/schema/orçamento/recuperação, conjunto vazio/isolado/
sem relevância, conflito/indeterminação/gate de fundamento, cutoff, publicação de
proveniência/cobertura parcial/TTL, limites e preservação do contrato Polymarket,
e auditoria sem inflar o contexto de negociação. Ensaios em temporários e cliente
JEV simulado; sem inferência real ou crédito consumido para validar esta alteração.

Sem implantação, build, mudança de .env, migração ou escrita nos bancos reais.
Inspeção final somente leitura: motor 66138fae36c8 iniciado em 13/10 22:28:07 UTC e
controle 720e65543765 iniciado às 22:28:08 UTC, ambos running/zero reinícios.
Aplicação das melhorias depende de atualização posterior dos serviços; não
concluir economia real a partir dos testes sintéticos.


## 14/10/2026 — D056, plano de perfis e pré-configurações completas

Usuário definiu swing, scalping e day trade para a próxima implementação, hold
posterior. A sessão trend_15m_v1 serve primeiro para revisar o core e corrigir
falhas; depois implementar/homologar perfis e escolher uma estratégia para uma
sessão dedicada de aproximadamente um mês. D054 mantém duração de amostragem
sob controle do usuário, sem bloqueio/reinício obrigatório de 24h.

Criados PLANO_PERFIS_ESTRATEGIA.md (P00–P09), PESQUISA_PERFIS_ESTRATEGIA.md
(fontes oficiais/institucionais/autores consultadas em 14/10) e
`docs/templates/perfis/`: README de campos/unidades/validações, template geral
completo e presets independentes daytrade_15m_v1, swing_4h_v1, scalping_1m_v1.
Valores e famílias específicas são propostas experimentais, não calibração nem
funcionalidades habilitadas. O CLI atual não aceita esses documentos como Config.

Plano preserva hexagonal/portas, cadastro em tabelas do SQLite de controle,
REST/WSS/TUI existentes, snapshot/versão imutáveis e Docker por sessão. Mapeados
os pontos fixos de 15m/1h/900s/perfil no código, agenda de fechamento, warmup,
JEV, cache, aprendizado/dataset/transferência e apresentação. Cadastro só usa
famílias implementadas; texto/YAML não executa algoritmos arbitrários.

Scalping de minutos prevê filtro local comum A/B/C e checkpoints limitados, com
até 80 ciclos/dia propostos; não promete HFT nem aumento dos 240 envios globais.
Day trade tem agenda UTC própria, swing tem duração/labels de dias. Proteção não
espera IA; falta de quote gera saída pendente, não fill inventado. Novos perfis
não recebem labels/memória de outro estilo por simples importação.

Verificação documental: quatro YAMLs carregados com parser seguro, mesmas 169
folhas/campos em todos, cobertura explícita dos 93 campos folha de Config atual,
strings Decimal financeiras finitas, intervalos/durações/horizontes/timeout/agenda
coerentes, vínculos locais válidos e git diff --check limpo. Isso não valida o
schema V2 de produção, que ainda será implementado. Não foram criados testes de
código nem repetida a suíte, pois a tarefa só modifica documentação/templates.

Nenhum código de runtime, configuração ativa, .env, container, observador ou banco
operacional foi alterado; nenhuma chamada a JEV/Marketaux/Polymarket foi feita
para pesquisar ou validar o plano. A pesquisa pública não habilitou novos perfis.

## 14/10/2026 — D057: perfis genéricos e criação de bots

Implementados catálogo versionado, schema estrito e templates completos,
CLI/REST e TUI para cadastrar/duplicar/validar/publicar perfis. Motor comum
parametrizado por intervalos, famílias, agenda, execução e instruções JEV;
protocolos V2 de features/labels/datasets, isolamento da memória e compatibilidade
legada. Recuperação manual de candles usa os intervalos da sessão, sem trades
retroativos. Editor de parâmetros em JSON com referência do schema na TUI.

**288 testes passaram**; lint, formatação e diff limpos. Smoke CLI isolado e
Docker sem rede validaram os templates. Controle atualizado às 17:22:12 UTC,
HTTP health 200. Sessão ETH permanece parada: 171 decisões, 342 outcomes,
zero fills, três entradas de ledger e 103 chamadas IA, linhas iguais ao backup;
auditoria OK e schema 6 preservado para leitura. Nenhum novo bot iniciado e
nenhum perfil cadastrado no catálogo operacional.

Backup em `data/backups/before-generic-profiles-20261014T165613Z/`.
Próximo: usuário escolher/configurar perfil e moeda, iniciar nova sessão e medir
latência, fontes e execução; não afirmar rentabilidade pela validação offline.
[Guia](GUIA_PERFIS_BOTS.md) ·
[Relatório e evidências](relatorios/VALIDACAO_PERFIS_GENERICOS_20261014.md).

## 14/10/2026 — D058: objetivos e orientações JEV em inglês

Traduzidos os seis campos de `jev_instructions` dos três templates empacotados,
cópias documentais, template genérico e defaults do schema. Versões
`scalping_instructions_en_v2`, `daytrade_instructions_en_v2` e
`swing_instructions_en_v2`, templates `.2`. TUI mantém os rótulos em português e
orienta escrever os textos do JEV em inglês; questionários de negociação e
classificação já eram ingleses e não foram alterados. Sem tradução automática
ou nova inferência por chamada; não impor detector heurístico ao texto livre.
Referências oficiais em D058/DECISIONS e no guia.

**288 testes passaram em 34,87s**, um aviso de depreciação Starlette/httpx.
Ruff check/format e diff limpos. Verificação isolada confirmou os textos no
payload real, igualdade dos sete conjuntos de parâmetros operacionais antes e
depois, paridade entre templates empacotados/documentais e restauração de hashes
com instruções anteriores preservadas. Docker sem rede validou os três estilos.
Nenhuma medição comparativa PT/EN nem ganho financeiro foi alegado.

Controle recriado às **19:01:19 UTC**, health HTTP 200 e três versões inglesas
confirmadas dentro do container. Imagem controle:
`sha256:6e5fd333e7d72ba1a27255812c4062960a7721a1e030e4cbd158ee2bf152f784`;
imagem de novos motores pronta:
`sha256:8bb0846ad37d495ed59880a4bbeafcf7095244f85fea8945000340d03dd84884`.
ETH continua parada: banco igual ao backup D057 em runs/decisions/outcomes/fills/
ledger/ai_calls, 171 decisões, 342 outcomes, zero fills, três lançamentos e 103
chamadas IA; auditoria OK. Catálogo com zero perfis, sem publicação ou nova sessão.
Nenhuma chamada paga nesta atualização.

Próximo passo do usuário: fechar/reabrir Perfis, selecionar novamente o template
Scalping e continuar `scalping_zec_v1` / `zec-scalp-01`; depois SUI/day trade e
UNI/swing, uma sessão por vez. O editor aberto antes da atualização não é
reescrito automaticamente, para preservar alterações ainda não salvas.
[Guia](GUIA_PERFIS_BOTS.md).

## 14/10/2026 — D059: limites JEV próprios por bot

Defaults editáveis no perfil/criação: `budget_scope=SESSION`, chamadas/dia,
habilitação da guarda financeira e valor USD/dia. Contagem diária independente
por run_id; reservas/recibos transacionais no SQLite operacional compartilhado,
sem teto global de 240/US$ 0,05 para SESSION. Cache/reuso B-C não duplicam cobrança;
recusa por orçamento de um pagador não veta outro bot. Histórico/contrato legado
preservados, sem downgrade de escopo para contornar política vinculada.

TUI mostra limites/uso diário e permite edição em `ai`. API/CLI de consulta por
sessão e agregado; escrita global normal retirada (409), ajustes legados exigem
rota/flag explícitos. Perfil ZEC publicado continua intacto; novas sessões dele
recebem a cópia efetiva SESSION, com ajustes registrados, sem recadastramento.

**297 testes completos passaram (37,68s)**; após último ajuste readonly da CLI,
12 direcionados passaram (1,72s). Um aviso Starlette/httpx. Lint/formato/diff
limpos, três templates validados em Docker sem rede. Controle atualizado às
19:37:32 UTC, health 200. ETH parada e auditada; nenhum novo bot iniciado.
Backup `data/backups/before-session-ai-budgets-20261014T193726Z/`; comparação
canônica das linhas históricas de sessão, orçamento e catálogo sem alteração.
[Relatório](relatorios/VALIDACAO_ORCAMENTO_POR_BOT_20261014.md) ·
[Guia de configuração](GUIA_PERFIS_BOTS.md).

## 14/10/2026 — correção da leitura do contexto nos perfis e retomada ZEC

Na sessão `run-4bc235d531dd422e` (ZECUSDT, `scalping_zec_v1`), o ciclo
admitido às 19:52 UTC foi interrompido antes da decisão. `ContextService.snapshot`
aplicava a janela do perfil a todas as chaves do contexto persistido, inclusive
à string `criteria_version`, causando `TypeError: 'str' object is not a mapping`.
A coleta também registrava erros repetidos. Seis chamadas reais de classificação
haviam retornado HTTP 200 (US$ 0,000476910); nenhuma inferência de trade ocorrera.

Correção restrita às seções `news` e `prediction_markets`, conservando metadados,
cutoff, validade e contexto imutável. Teste de regressão reproduziu a falha antes
da correção; depois validou os três estilos com SQLite real, decisão A/B/C,
chamada da porta de política offline, idempotência e auditoria. **300 testes
passaram em 39,54s**, um aviso Starlette/httpx; lint/formato/diff limpos.
Snapshot da sessão real também validado em leitura, sem requisições adicionais.

Backup auditado em `data/backups/zec-before-context-metadata-fix-20261014/`.
Parada limpa, remoção apenas do container parado, rebuild e retomada do mesmo
run_id às **20:21:40 UTC (17:21:40 Brasília)**. Imagem do motor:
`sha256:3c647c4e0e56b3af92eff44592733d5dc6c108365d52161f80970beed0f27609`.
Health inicial RUNNING, WebSocket conectado, preço fresco, relógio VERIFIED,
`last_error=null`; nova versão de contexto persistida às 20:21:42 UTC.
Histórico do ciclo interrompido preservado, sem negociação retroativa ou mudanças
dos parâmetros. Novas inferências de trade dependem de oportunidades admitidas;
a retomada por si só não comprova uma decisão real concluída ou rentabilidade.

## 14/10/2026 — D060: janela de 15s e teste ZEC revisão 2 ativo

O ciclo admitido às 21:22 UTC na sessão ZEC anterior terminou com HOLD A e
`AI_DEADLINE_EXCEEDED` B/C. Preparação até 21:22:02,3 deixava menos que os 6s
de timeout na janela total 8s; nenhuma requisição trade foi enviada. A estava
correta em aguardar (tendência baixa, sem alinhamento completo e volume 1,05x
abaixo de 1,30x). API não estava bloqueada pelo orçamento. `TypeError` anterior
não reapareceu; fontes parciais e erros REST de mercado continuam pendências.

Usuário autorizou alterar prazo, rodar novamente e deixar ativo. Validação
SCALPING permite até 15s; ainda rejeita 16s e timeout maior que deadline.
Presets anteriores conservam seu default 8s. Testes de schema/restore/hash,
validação-publicação-criação pela API e edição TUI cobrem a nova janela.
MockTransport reproduz a preparação 2,3s: janela 8s sem envio, janela 15s
com um envio e uma contabilização, sem requisições pagas nesses testes.
**303 testes passaram em 37,52s**, um aviso Starlette/httpx; lint/formato/diff limpos.

Backup em `data/backups/zec-before-scalping-deadline-cap-20261014/`, incluindo
cópias SQLite de controle/auth. Sessão antiga parada com 2 ciclos (um
interrompido/um concluído), 3 decisões, 6 classificações, zero fills e hash
`7a8e520a998a24fe83553e820535bfcd34510fcdcc3d9d86a1c7fae6cae0b114` intacto.
Publicada `scalping_zec_v1` revisão 2; preparada e iniciada `zec-scalping-02`.
Comparação dos parâmetros efetivos comprova mudança exclusiva de
`app.max_candle_decision_lag_seconds`: **8 → 15**. Conservados timeout 6s,
candles 1m/tendência 5m, admissão/risco e orçamento US$ 0,50/240 chamadas.
Cada sessão mantém banco/custos e capital paper próprios, sem negociação retroativa.

Imagens: motor `sha256:da69935309bac5dded1b7d51fb41ed4da8cdb53b10625a8e981454b5f8e0ee1c`;
controle `sha256:7338168c717a64c177a75646ec6b31cedd268c5519d3c6be904baa31d5b7ef7b`.
Partida às **21:45:58 UTC**; health inicial RUNNING/WS conectado/quote fresca/
clock VERIFIED/sem erro. Apenas o novo motor de paper da POC está ativo.
Evidências/definição/validação/preparação em
`data/diagnostics/scalping-deadline-15s-20261014/`.
Nova sessão aguarda oportunidades; não alegar inferência trade real concluída
somente por esses testes ou pela partida. Na TUI, fechar editor anterior,
pressionar **r** e selecionar **zec-scalping-02**; revisão 2 já está publicada.
