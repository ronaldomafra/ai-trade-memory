# Templates completos de perfis — cadastro D057

**D057 · SPEC 1.55 · 14/10/2026.** Estes YAMLs são aceitos por `profile-validate`
e `profile-register`, com publicação posterior. A TUI/API usam o mesmo schema e
templates empacotados. Não usar como `--config`: perfil é distinto de configuração
do servidor. Publicar não inicia motor. [Guia de uso](../../GUIA_PERFIS_BOTS.md).
Usar junto do [plano](../../PLANO_PERFIS_ESTRATEGIA.md) e da
[pesquisa](../../PESQUISA_PERFIS_ESTRATEGIA.md).

| Arquivo | Ponto de partida |
| --- | --- |
| [perfil.template.yaml](perfil.template.yaml) | Modelo geral completo, preenchido com defaults day trade; alterar identidade e revisar estilo/família antes de cadastrar. |
| [daytrade_15m_v1.yaml](daytrade_15m_v1.yaml) | Rompimento intradiário 15m/1h e encerramento UTC. |
| [swing_4h_v1.yaml](swing_4h_v1.yaml) | Rompimento 4h/1d, dias/semanas, sem encerramento diário. |
| [scalping_1m_v1.yaml](scalping_1m_v1.yaml) | Cruzamento 1m/5m, seleção local e checkpoints JEV, posições de minutos. |

Os documentos são independentes e completos: copiar um arquivo basta para ter
todos os parâmetros propostos. Não dependem de herança ou de outro YAML.
Defaults não são parâmetros otimizados. Hold não está incluído.

## Organização e regras de preenchimento

**D059:** templates `.3` usam orçamento SESSION. Perfil e tela Nova permitem
configurar chamadas, valor diário e habilitação do limite financeiro por bot.
Novas sessões de um perfil antigo também recebem esse contrato na cópia efetiva,
sem reescrever seu cadastro ou os snapshots anteriores.


**D058:** objetivos, orientações e restrições de `parameters.jev_instructions`
são escritos em inglês, com versões `*_instructions_en_v2`; templates `.2`.
A [documentação oficial da TypeSafe](https://docs.typesafe.ai/models#language-support)
informa melhor precisão em inglês. Nomes exibidos/TUI/documentação continuam
em português. Textos externos conservam o idioma original, sem tradução por
requisição. Revisões e snapshots existentes não são reescritos.

| Caminho | Tipo/unidade | Regra de configuração |
| --- | --- | --- |
| `document_kind`, `schema_version` | Enum/string de versão | Identificam o contrato; não confundir com Config atual. |
| `profile.profile_id` | String `[a-z][a-z0-9_]{2,63}` | ID estável; customização não sobrescreve um ID/versão existente. |
| `profile.version` | Inteiro >0 | Nova revisão publicada é imutável. |
| `profile.template_version` | String não vazia | Origem da pré-configuração copiada para a sessão. |
| `profile.display_name`, `description`, `documentation_reference` | Texto/referência | Metadados limitados; nunca interpretar como caminho executável. |
| `profile.style` | `SWING`, `SCALPING`, `DAY_TRADE` | Não cadastrar hold nesta entrega. |
| `profile.strategy_family`, `parameters.strategy.algorithm_version` | IDs conhecidos | Devem identificar a mesma implementação/versionamento suportados. |
| `profile.lifecycle_status`, `implementation_status`, `minimum_engine_capability` | Estados/capability | Estado informado no YAML não se autopublica; servidor verifica código e permissões. |
| `profile.research_references` | Lista de IDs R1–R12 | Rastreabilidade; não consome APIs na partida. |
| `session_defaults.symbol` | Par Spot USDT | Default editável na criação; metadados públicos são obrigatórios. |
| `session_defaults.initial_dataset_path` | null protegido | Dataset é escolhido ao criar a sessão pela TUI; importação CLI antes do primeiro ciclo também é possível. Não cadastrar caminho do servidor em um perfil. |
| `parameters.app.instance_name`, `log_level` | Texto/enum | Identificação/logs; INFO é default. Sem credenciais em logs. |
| `parameters.app.poll_seconds` | Inteiro em segundos | Housekeeping do motor; proteção também reage a cotações WS. Não implica REST a cada segundo. |
| `parameters.app.max_candle_decision_lag_seconds` | Inteiro >0, <=90s | Deve caber no horizonte operacional; SCALPING aceita até 15s (D060). Presets anteriores conservam 8s; revisão ZEC 2 testa 15s. |
| `parameters.app.max_quote_age_seconds` | Inteiro >0, <=30s | Idade da cotação, não idade do candle. |
| `parameters.market.provider`, `quote_asset` | Enums protegidos | `binance_public` e `USDT`. |
| `parameters.market.interval`, `trend_interval` | Enum implementado | Conjunto inicial: 1m, 5m, 15m, 1h, 4h, 1d. Tendência deve ser mais lenta e múltipla inteira da decisão. |
| `parameters.market.warmup_candles.decision`, `.trend` | Contagens >0 | Cobrir EMAs/RSI/MACD/ATR/buckets/janelas em cada intervalo; 600 em cada preset. |
| `parameters.market.warmup_max_pages_per_interval` | Inteiro >0 | Limita recuperação; usar páginas REST <=1000 registros e só candles fechados. |
| `parameters.market.rest_fallback_poll_seconds` | Inteiro >0 | Cadência REST em falha de WS, sujeita a rate limits. Não relaxa frescor se houver intervalos sem quote elegível. |
| `parameters.market.min_trade_notional_usdt` | String Decimal >0, USDT | Piso interno combinado com filtros reais do par, nunca os substitui. |
| `parameters.indicators.rsi`, `.atr`, `.relative_volume_window` | Períodos inteiros >0 | Campos neutros de timeframe. O nome público RSI deve identificar o período real, não fixar rsi_14 se editado. |
| `parameters.indicators.ema_short`, `.ema_mid`, `.ema_long` | Períodos inteiros >0 | Curta < média < longa. |
| `parameters.indicators.macd_fast`, `.macd_slow`, `.macd_signal` | Períodos inteiros >0 | Fast < slow; warmup inclui signal. |
| `parameters.indicators.return_horizons_bars` | Lista distinta de inteiros>0 | Retornos passados das features; explicitar duração em segundos e versão do normalizador. Não confundir com horizontes futuros dos labels. |
| `parameters.strategy.max_allocation_pct` | String Decimal em % | >0 e <=100; default20. Código calcula orçamento e taxas. |
| `parameters.strategy.max_positions` | Inteiro fixo1 | Não amplia número de posições na POC. |
| `parameters.strategy.stop_loss_pct`, `.take_profit_pct` | Strings Decimal em % | >0 e <100; validação de viabilidade líquida antes do fill. |
| `parameters.strategy.max_holding_candles` | Inteiro >0 | Converter em segundos pelo intervalo; no V2 contar desde fill. Limites coerentes com estilo. |
| `parameters.strategy.duration_clock` | Enum protegido V2 | `ELAPSED_SINCE_FILL`; adaptação legada é separada, sem alterar seu contrato. |
| `parameters.strategy.daily_loss_guard_pct` | String Decimal em % | (0,100]; trava persistida por carteira/dia UTC. |
| `parameters.strategy.action_probability_threshold`, `.action_margin_threshold` | Números finitos [0,1] | Não confundir com confidence ou probabilidade do Polymarket. |
| `parameters.strategy.require_structural_entry_setup` | Booleano protegido true | BUY de qualquer variante exige setup da família; não exige copiar confirmações completas de A. |
| `parameters.strategy.reentry_cooldown_candles` | Inteiro >=0 | Calculado desde saída da própria carteira; persistir para restart. |
| `parameters.strategy.technical.entry_rule` | Enum da família | `PRIOR_HIGH_BREAKOUT` ou `EMA_CROSS`. Não é expressão executável. |
| `parameters.strategy.technical.rsi_entry_min`, `.rsi_entry_max`, `.rsi_exit` | Números finitos [0,100] | Min <= max; se saída RSI ativa, max < exit. |
| `parameters.strategy.technical.rsi_exit_enabled` | Booleano | false no swing; manter campo rsi_exit explícito mas inativo. |
| `parameters.strategy.technical.min_relative_volume` | Razão finita >0 | Volume atual dividido pela média anterior, excluindo o atual do denominador. |
| `parameters.strategy.technical.require_ema_alignment`, `.require_trend_bullish`, `.require_positive_macd` | Booleanos | Confirmações técnicas A; alterações criam parametrização/protocolo próprios. |
| `parameters.strategy.technical.breakout_lookback_candles` | Inteiro >0 ou null | Obrigatório em rompimento; null em cruzamento. Excluir high do candle atual. |
| `parameters.strategy.technical.breakout_buffer_pct` | String Decimal >=0 ou null | Percentual sobre nível anterior; null em cruzamento. |
| `parameters.strategy.technical.ema_cross_previous_candle_required` | Booleano | true em cruzamento: verificar transição, não apenas alinhamento. |
| `parameters.strategy.technical.exit_on_ema_reversal`, `.exit_on_negative_macd` | Booleanos | Saídas técnicas A. Proteções duras sempre continuam ativas. |
| `parameters.opportunities.mode` | Enum | Todos os candles ou setup/checkpoint local; não é modo de execução real. |
| `parameters.opportunities.minimum_cycle_spacing_seconds` | Inteiro >0 | Intervalo mínimo entre admissões do trio, com estado persistido. |
| `parameters.opportunities.max_cycles_per_day_utc` | Inteiro >0 | Teto de ciclos do trio; distinto de tentativas físicas e orçamento próprio da sessão. |
| `parameters.opportunities.evaluate_all_variants_together` | Booleano protegido true | Mantém oportunidade/coorte comuns A/B/C. |
| `parameters.opportunities.checkpoint_when_any_portfolio_holds` | Booleano protegido true | Posição em uma carteira não pode ficar sem checkpoints por falta de novo setup. Ainda respeita teto de ciclos e risco independente. |
| `parameters.opportunities.candidate_rsi_min`, `.candidate_rsi_max` | Números finitos [0,100] | Faixa ampla de admissão local; usada só no modo seletivo. |
| `parameters.opportunities.candidate_min_relative_volume` | Razão finita >0 | Filtro amplo; não substituir min_relative_volume de A. |
| `parameters.operation_window.enabled` | Booleano | false permite operação contínua sem fechamento diário. |
| `parameters.operation_window.timezone` | Enum protegido UTC | Sem interpretação implícita no fuso do terminal. |
| `parameters.operation_window.start_utc`, `.end_utc`, `.entry_cutoff_utc`, `.flatten_utc` | HH:MM:SS / null documentado | Cutoff e flatten obrigatórios se force_flat ativo; null se inativos. |
| `parameters.operation_window.end_next_day` | Booleano | Distingue janela de 24h start=end de duração zero. |
| `parameters.operation_window.weekdays_utc` | Lista distinta de inteiros0–6 | Segunda=0, domingo=6; presets incluem todos os dias. |
| `parameters.operation_window.force_flat_at_end` | Booleano | true no intradiário; false swing. Não equivale a apagar sessão no fim do dia. |
| `parameters.operation_window.block_new_entries_while_exit_pending` | Booleano protegido true | Pendência de encerramento impede nova entrada até resolver. |
| `parameters.execution_quality.enabled` | Booleano protegido true | Gates do cenário de execução e de atualização do preço. |
| `parameters.execution_quality.max_market_spread_pct` | String Decimal >=0, % | Spread cripto, não spread Poly em pp; normalizar pelo midpoint. |
| `parameters.execution_quality.max_entry_price_drift_pct` | String Decimal >=0, % | Valor absoluto de ask posterior/ask de referência −1; expirar BUY se ultrapassar. |
| `parameters.execution_quality.require_positive_net_target` | Booleano protegido true | Resultado-alvo líquido positivo segundo funções do broker. |
| `parameters.execution_quality.minimum_net_target_to_stop_ratio` | String Decimal >0 | Razão entre cenários líquidos; não probabilidade nem retorno esperado. |
| `parameters.simulation.trading_fee_pct_per_side`, `.slippage_pct_per_side` | Strings Decimal em %, [0,100) | Custos explícitos por lado, iguais nas variantes. |
| `parameters.simulation.fill_price_source` | Enum protegido | `public_book_ticker`, sem fill passivo presumido. |
| `parameters.ai.provider`, `.model` | Enums protegidos | OpenRouter / `typesafe/jev-1.13`. |
| `parameters.ai.timeout_seconds` | Inteiro >0 | <=deadline. Repetição só se couber tempo restante, sem terceira tentativa. |
| `parameters.ai.max_retries` | Inteiro0 ou1 | Budget/timeout ainda podem impedir retry. |
| `parameters.ai.budget_scope` | Enum SESSION | D059: defaults do perfil e contadores separados por bot/sessão. |
| `parameters.ai.max_calls_per_day` | Inteiro positivo | Editável no perfil/criação; tentativas físicas, incluindo classificação/retries. Sem teto global de 240 para SESSION. |
| `parameters.ai.cost_limit_enabled` | Booleano | Liga/desliga somente a guarda financeira desse bot. |
| `parameters.ai.max_observed_cost_usd_per_day` | String Decimal positiva, USD | Limite próprio do bot; default 0,05 editável, sem teto global oculto. |
| `parameters.ai.fail_closed` | Booleano protegido true | Falha não autoriza entrada. |
| `parameters.ai.prompt_version` | ID de contrato implementado | Não torna schema desconhecido executável. |
| `parameters.jev_instructions.version`, `.max_characters` | Versão / inteiro<=4000 | Texto fixado na sessão; renderizador não executa expressões. |
| `parameters.jev_instructions.objective`, `.entry_guidance`, `.exit_guidance`, `.external_context_guidance`, `.memory_guidance`, `.constraints` | Textos limitados, total<=4000 | Perfil orienta JEV; campos numéricos e limites duros do core prevalecem sobre prosa conflitante. |
| `parameters.news.*` | Tipos do contrato atual | Todos explícitos: enabled, provider, API/RSS minutos, lookback<=24h, até5itens e fontes HTTPS sem credenciais. D055 preservado. |
| `parameters.polymarket.*` | Tipos do contrato atual | Todos os 16 parâmetros explícitos; spread/banda em pp, valores USD em strings. Tetos/qualidade/frescor não afrouxados implicitamente por estilo. |
| `parameters.learning.enabled` | Booleano | false impede memória; não permite C usar dados não amadurecidos. |
| `parameters.learning.label_version`, `.feature_version`, `.equivalence_version` | IDs suportados | Fazem parte do protocolo; V1 preservado por adaptador, não pelo rename do arquivo. |
| `parameters.learning.evaluation_horizons_bars` | Lista distinta de inteiros>0 | Validar durações/estilo; não fixar4/16 globalmente. |
| `parameters.learning.primary_horizon_bars` | Um dos horizontes | Identifica comparação principal, não permite somar horizontes. |
| `parameters.learning.outcome_quote_window_seconds` | Inteiro1–90 | Quote pós-maturação; ausência = UNAVAILABLE. |
| `parameters.learning.maturity_anchor` | Enum protegido | Fronteira exclusiva do candle de referência, UTC, mais horizonte×intervalo. |
| `parameters.learning.rolling_lookback_days` | Inteiro fixo60 | Histórico arquivado é diferente da janela ativa. |
| `parameters.learning.min_exact_pattern_samples`, `.min_coarse_pattern_samples` | Inteiros>=30 / >=50 | Contar amostras únicas maduras; não reduzir para fabricar memória. |
| `parameters.learning.max_memory_items` | Inteiro1–3 | Total de locais/transferidos. |
| `parameters.learning.use_only_matured_outcomes` | Booleano protegido true | Sem futuro. |
| `parameters.learning.transfer.*` | Tipos do contrato atual + isolamento | Todos os campos explícitos: enabled, policy/normalizer, min50/max200 fontes, min30 destino; cross_profile_allowed=false, require_same_protocol=true. |
| `platform_bindings.*` | Snapshot de referências protegidas | Exibir/validar no servidor; não permitir override pelo cadastro ou pela sessão remota. Sem valores de credenciais. |

Esta tabela serve de referência; a autoridade dos tipos é
`ProfileDefinition.model_json_schema()`, utilizado pela CLI/API e apresentado
na TUI. A validação do servidor prevalece sobre o conteúdo do editor.

## Validações entre campos

- Contrato de família admite somente estilos/intervalos declarados e implementados.
  Tendência mais lenta; warmup cobre ambas as séries e o cálculo de volatilidade.
  Rejeitar intervalo mensal e outras unidades sem duração UTC fixa neste escopo.
- Duração coerente: scalping de minutos; day trade <=24h e force_flat ativo;
  swing admite dias e não recebe fechamento compulsório por herança. O schema
  codifica limites de cada família, não apenas validar positividade.
- Agenda ordenada: início <= cutoff < flatten < término; tratar corretamente o
  término no dia seguinte, calendário UTC e start=end com end_next_day=true.
- RSI e períodos ordenados; campos de rompimento obrigatórios apenas nessa regra;
  campos incompatíveis null/rejeitados. Custo e timeframe coerentes com deadlines.
- Mesmo snapshot operacional A/B/C, mas posição e memória continuam particulares.
  D059 permite editar os limites JEV do perfil/bot; cotas reais de provedor não mudam.
- Normalizador `profile_relative_features_v2` identifica as durações reais dos
  retornos/features. Adaptador `relative_features_v1` permanece para históricos
  legados; não renomear r4/r16 e reinterpretar seus períodos silenciosamente.
- Preview resolve segundos de horizonte/duração, agenda, custo-cenário e demanda
  potencial de IA sem chamadas ao modelo ou criação de carteiras.

O template não contém chaves de exchange/OpenRouter/Marketaux/proxy, senha/TOTP,
token de acesso, path arbitrário de plugin, expressão Python ou comando de shell.
