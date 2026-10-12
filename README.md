# ai-trade-memory

**Contexto externo aprovado:** notícias e Polymarket com fatores separados e evidência curta, mesma base B/C; critérios e políticas D002/D018–D049 no [contrato vigente](docs/SPEC.md). P012 encerrado para discussão; detalhes técnicos serão resolvidos na implementação, de forma proporcional à POC. Implementação integrada ao motor; validação semântica real e unidades monetárias Gamma ainda pendentes em E05.

**D030 — suporte a outros ativos na V1:** um par Spot configurável com cotação USDT por sessão, selecionado antes de iniciar; BTC é exemplo/default. Banco, trio A/B/C e memória por símbolo permanecem separados. Quantidades, metadados, feeds, prompts e contexto usam o ativo destino. Retomada mantém o par salvo; transferência separada integra V1 conforme D052/SPEC 10.10. [Contrato vigente, seção 4.3](docs/SPEC.md). BTC/ETH validados em sessões e testes independentes.

**Descoberta Polymarket D031:** até 100 registros/página e cinco requisições físicas por revisão inicial/60m, incluindo retries/todos os temas da sessão; até dez mercados acompanhados, mesma seleção B/C. Registrar limites/cobertura parcial e impedir loops. Detalhes e regras posteriores no [contrato vigente](docs/SPEC.md).

**Laboratório de negociação simulada de criptomoedas com IA probabilística e aprendizado contínuo.**

> O mercado fornece os dados. O JEV avalia as decisões. O nosso motor de memória aprende com os resultados.

**Status:** V1 em desenvolvimento; motor, transferência, API REST/WS e TUI disponíveis · **Linguagem:** Python 3.11+ · **Modo:** `PAPER_ONLY`

## Documentação fechada

[Escopo V1](docs/ESCOPO_POC_V1.md) · [SPEC 1.50](docs/SPEC.md) · [Backlog técnico](docs/BACKLOG_IMPLEMENTACAO.md) · [Índice](docs/README.md).

D050–D052 consolidam motores por sessão/Docker, orçamento global e V1 com transferência automática, REST/WSS/token/2FA e TUI remota após núcleo. [Plano ordenado E00–E11](docs/PLANO_DESENVOLVIMENTO_V1.md) · [Status](docs/STATUS_DESENVOLVIMENTO.md). Sem microaprovações; detalhes rotineiros são implementação/testes. Os módulos disponíveis estão na seção de execução atual; validações externas e aceite prolongado permanecem explícitos.

## Instalação e execução disponíveis

Siga o [guia de configuração e execução](docs/GUIA_CONFIGURACAO_EXECUCAO.md)
para preparar .env, Docker, proprietário/2FA, TUI, sessões, datasets e recuperação.

O núcleo offline possui broker Decimal, risco, SQLite/ledger/eventos, sessões isoladas e projeções. Motor, datasets, transferência e controle remoto estão implementados; TUI implementada e testada localmente; aceite integrado E11 pendente; progresso em [STATUS_DESENVOLVIMENTO.md](docs/STATUS_DESENVOLVIMENTO.md).

Instale com uv (Python 3.11+ gerenciado pelo ambiente):

```bash
uv sync --locked
uv run python -m poc --help
uv run python -m poc config-check
uv run pytest -q
uv run ruff check src tests
uv run python -m poc smoke-offline
```

O smoke padrão é V1_OFFLINE_PIPELINE: oito ciclos/24 decisões com indicadores, JEV/budget via transporte simulado, B/C compartilhados, broker/ledger, risco, labels 4/16 e exportação. Usa fixtures identificadas e não faz rede/inferência/cobrança real. Observações amadurecidas de fixture ficam fora da memória operacional, catálogo e dataset reutilizável. O cenário E01_ACCOUNTING permanece em `smoke-offline --scope accounting`. Ambos geram artefatos em sessões próprias, com 100 USDT iniciais por carteira.

```bash
# Prepara sessão somente após validar metadados públicos reais
uv run python -m poc prepare-session --profile trend_15m_v1 --symbol ETHUSDT --run-id minha-sessao
# Consultas identificam explicitamente a sessão
uv run python -m poc status --run-id minha-sessao
uv run python -m poc validate-data --run-id minha-sessao
uv run python -m poc export --run-id minha-sessao --format all
uv run python -m poc export-events --run-id minha-sessao --rebuild
```

.env.example descreve variáveis opcionais; configure segredos só em .env local/ambiente. POC_DATA_DIR muda a raiz dos caminhos padrão. A configuração efetiva/template/alterações/hash ficam na sessão; restaurar preserva o estado aceito. A CLI rejeita perfil desconhecido, run_id inválido, banco ausente e caminhos privados de exchange.

Artefatos: data/sessions/RUN_ID/poc.sqlite3, logs/YYYY-MM-DD/events.jsonl e exports/{dashboard-latest.json,fills.csv,portfolio_equity.csv,ledger.csv}. Campos monetários são texto decimal. Sair da consulta não altera saldos. REST/WS/TUI estão disponíveis; acesso remoto exige proxy TLS. Dataset local está disponível. Engine e Docker estão disponíveis.

## Visão geral

O **ai-trade-memory** é uma prova de conceito (POC) para investigar se um motor próprio de aprendizado contínuo pode melhorar decisões de negociação de criptomoedas.

O sistema observa **dados reais de mercado**, calcula indicadores técnicos, coleta notícias e consulta o **JEV 1.13**, por meio do **OpenRouter**, para avaliar as ações `BUY`, `SELL` ou `HOLD`. As ordens e carteiras são **100% virtuais**: nenhum dinheiro é negociado em corretoras.

Mais do que simular lucro, a POC busca responder:

1. Uma estratégia com JEV, notícias e expectativas do Polymarket supera as regras técnicas de referência?
2. Fornecer ao JEV o histórico estruturado de erros e acertos melhora suas decisões?
3. A melhoria, se existir, compensa o **custo real** das chamadas ao OpenRouter?

**Importante:** o JEV **não é retreinado** pelo projeto. O aprendizado acontece em um componente Python próprio, que avalia decisões passadas, consolida padrões estatísticos e fornece esse contexto nas próximas chamadas ao modelo.

## Como o experimento funciona

Três estratégias independentes acompanham o mesmo mercado e começam, cada uma, com **100 USDT fictícios**:

| Carteira | Identificador | Estratégia | O que mede |
| --- | --- | --- | --- |
| **A** | `BASELINE_TECHNICAL` | Indicadores e regras fixas, sem IA | Referência quantitativa |
| **B** | `JEV_STATIC` | Indicadores, notícias por API, Polymarket e JEV, sem memória | Contribuição da estratégia enriquecida completa |
| **C** | `JEV_LEARNING` | Mesmo JEV + contexto do Learning Engine | Contribuição do aprendizado |

Cada carteira tem saldo, posições, ordens e resultados próprios. **Não** são 300 USDT em uma carteira única: são três cenários comparativos com 100 USDT cada.

Pelas [decisões D009/D010](docs/DECISIONS.md), escolher explicitamente o perfil antes de criar uma sessão, com banco e trio A/B/C próprios. Nova sessão inicia capital novo; restauração recupera configuração/perfil, carteiras, memória e histórico sem reset. O usuário pretende operar dois perfis após homologação: serão duas sessões e seis carteiras independentes, com orçamento de IA global coordenado. Catálogo inicial `trend_15m_v1`; outros estilos exigem contratos próprios; consultar [perfis e sessões](docs/PERFIS_E_SESSOES.md). HTTP/TUI integram a entrega após Marcos 1–5; HTML e outros estilos são evolução.

[D013](docs/DECISIONS.md) define pré-configuração por estratégia baseada nos documentos, com ajustes antes de criar a sessão e valores efetivos persistidos. Os perfis de uso serão escolhidos na partida entre os implementados/validados; restaurar conserva a configuração salva. Guardar esse requisito para a futura TUI, sem antecipar suas telas/fase.

### Ciclo operacional

```mermaid
flowchart TD
    M[Mercado público: candles e bid/ask] --> F[Indicadores e contexto de mercado]
    N[Notícias e Polymarket] --> X[Fatores e evidência curta reutilizáveis]
    X --> B
    X --> C
    F --> A[Carteira A: regras técnicas]
    F --> B[Carteira B: JEV sem memória]
    F --> L[Learning Engine: memória de resultados maduros]
    L --> C[Carteira C: JEV com memória]
    A --> R[Validação de risco e Paper Broker]
    B --> R
    C --> R
    R --> D[(SQLite: fonte de verdade)]
    D --> O[Outcome Evaluator]
    O --> L
    D --> E[JSONL + exportações JSON/CSV]
    E --> H[Futuro dashboard HTML]
```

A cada **candle fechado de 15 minutos**, o serviço atualiza os dados e avalia as estratégias. A tendência também considera candles de **1 hora**. Cotações públicas podem ser consultadas entre ciclos para monitorar stops e posições abertas.

Todas as simulações são **Spot, long-only**: `BUY` abre uma posição no ativo base configurado; `SELL` encerra a posição existente; `HOLD` não modifica a carteira. Não há short, futuros ou alavancagem.

## Aprendizado contínuo: o diferencial

O **Learning Engine** é independente do JEV. Ele registra o cenário de cada decisão e, quando há dados posteriores suficientes, avalia seu resultado.

- **Memória contextual:** combina regime de mercado, faixas de RSI, volume, volatilidade e situação da carteira.
- **Resultados amadurecidos:** avalia horizontes de **4 e 16 candles**; decisões recentes não entram prematuramente na memória.
- **Comparação contrafactual:** verifica oportunidades não executadas (`HOLD`) sem lançar negociações fictícias na carteira.
- **Estatísticas rastreáveis:** amostras, taxas de acerto, retorno líquido médio, incerteza e período observado.
- **Contexto compacto:** envia ao JEV da carteira C somente os padrões relevantes e suficientemente amostrados.

Pela [decisão D003](docs/DECISIONS.md), todos os grupos preservam execução/perfil, símbolo, posição, família do resultado e horizonte. O nível específico exige 30 resultados amadurecidos; o fallback por regime exige 50. Quando insuficientes, o contexto informa a ausência de amostras. A janela permanece de 60 dias e o limite é de três padrões. [D014](docs/DECISIONS.md) aprova labels contrafactuais amadurecidos de A/B/C como fontes da memória de C, contando avaliações equivalentes uma vez e preservando todas as origens. Dependência entre candles consecutivos permanece reservada em P008; exemplos únicos não comprovam independência.

A V1 usa **aprendizado estatístico e contextual**, não redes neurais nem ajuste automático dos pesos do JEV. Os parâmetros de risco e os limiares da estratégia permanecem fixos durante a comparação. Uma perda isolada não é automaticamente tratada como erro do modelo.

Pela [decisão D006](docs/DECISIONS.md), falta de bid válido nos 90s após o horizonte produz label `UNAVAILABLE`, excluído da memória, com motivo e cobertura reportados. Backfill de candles não substitui cotações ausentes; não há fonte histórica adicional na V1.

Pela [decisão D007](docs/DECISIONS.md), importar/exportar [dataset acumulativo de aprendizado](docs/DATASET_APRENDIZADO.md) permite iniciar C com amostras compatíveis de outras execuções, mediante vínculo explícito que preserva a origem. Cada nova revisão reúne histórico válido e novos resultados amadurecidos, sem duplicar amostras ou sobrescrever versões. O arquivo histórico pode superar 60 dias; memória ativa mantém janela, símbolo, mínimos e contexto compacto. B e saldos não recebem histórico importado. Import/export implementados; transferência estatística separada integra V1 em D052/10.10, e D030 permite outros ativos na V1 em sessões independentes. Aumentar o acervo não comprova maior precisão.

Pela [decisão D008](docs/DECISIONS.md), preservar memória específica por ativo. O pedido posterior D052 inclui transferência automática separada na V1, com normalização, origem, validação prospectiva e ativação/suspensão em [TRANSFERENCIA_APRENDIZADO.md](docs/TRANSFERENCIA_APRENDIZADO.md). Não somar amostras BTC aos mínimos locais de outra moeda; melhoria exige avaliação real.

Para evitar conclusões artificiais, somente informações efetivamente disponíveis **antes de cada decisão** poderão influenciá-la (*sem look-ahead*). A POC não pressupõe que as probabilidades do JEV sejam probabilidades calibradas de lucro.

## Configuração inicial da POC

| Parâmetro | Valor inicial |
| --- | --- |
| Mercado | Par Spot configurável com cotação USDT; um por sessão (BTC/USDT é exemplo). |
| Capital | `100 USDT` por carteira |
| Intervalo principal | `15m` |
| Confirmação de tendência | `1h` |
| Indicadores | RSI, MACD, EMA, ATR e volume relativo |
| Alocação máxima por compra | 20% do patrimônio, limitado ao caixa disponível; orçamento inclui a taxa de entrada |
| Stop-loss / take-profit | 1,5% / 3,0% (valores experimentais) |
| Trava de perda diária | 5% do patrimônio de referência do início do dia UTC, por carteira: encerra posição e bloqueia compras até o próximo dia |
| Taxa simulada | 0,10% por lado |
| Slippage simulado | 0,05% por lado |
| Modelo | `typesafe/jev-1.13` via OpenRouter |
| Tentativas JEV por pedido | Até duas totais: inicial e uma repetição por falha transitória, respeitando orçamento e prazo |
| Probabilidade mínima da ação | 0,65, com margem mínima de 0,10 sobre a segunda opção |
| Memória | Janela móvel de 60 dias; padrões com amostragem mínima |
| Persistência | SQLite + eventos JSONL + exportações JSON/CSV |

Esses valores são **hipóteses iniciais de pesquisa**, não parâmetros otimizados nem recomendações de investimento. A especificação técnica completa está disponível em [`docs/SPEC.md`](docs/SPEC.md).

Pela [decisão D004](docs/DECISIONS.md), a trava diária usa caixa mais o ativo base marcado ao bid e permanece após restart ou recuperação intradia. Encerramento exige cotação fresca; sem ela, a saída fica pendente. A reativação no novo dia UTC exige referência válida e demais condições de entrada; a virada não cancela proteção ainda pendente.

## Arquitetura Python

A [base hexagonal com Docker Compose](docs/ARQUITETURA.md) está aprovada em P016/D012: núcleo separado das integrações, um motor/container por sessão e armazenamento local persistente. Motor e Docker implementados, um banco por sessão e orçamento global compartilhado. D011 define `trend_15m_v1`; outro estilo exige contrato e implementação próprios.

O projeto é modular, com TUI como cliente REST/WS e motores independentes:

```text
ai-trade-memory/
├── AGENTS.md                 # Orientações para agentes de programação
├── README.md
├── pyproject.toml
├── Dockerfile                # Imagem comum
├── compose.yaml              # Um motor por sessão
├── .env.example
├── config/
│   └── default.yaml
├── docs/
│   └── SPEC.md               # Especificação técnica completa
├── src/
│   └── poc/
│       ├── domain/           # Regras, indicadores, finanças paper e estatísticas
│       ├── application/      # Casos de uso, portas e unidade de trabalho
│       ├── adapters/
│       │   ├── inbound/      # CLI e agendamento
│       │   └── outbound/     # Fontes públicas, JEV, SQLite, arquivos e orçamento
│       └── bootstrap.py      # Composição dos adaptadores/configuração
├── tests/
├── deploy/                   # Alternativa systemd (prevista)
└── data/                     # Gerado em execução; ignorado pelo Git
    ├── sessions/RUN_ID/
    │   ├── poc.sqlite3
    │   ├── logs/YYYY-MM-DD/events.jsonl
    │   └── exports/
    │       ├── dashboard-latest.json
    │       ├── decisions.csv
    │       ├── fills.csv
    │       └── ai_usage.csv
    └── datasets/              # Arquivos portáveis versionados
```

**Tecnologias previstas:** Python 3.11+, `asyncio`, `httpx`, Pydantic, SQLite, pandas/NumPy, biblioteca de indicadores técnicos, `pytest` e `ruff`.

O banco **SQLite é a fonte de verdade**. Os arquivos JSONL e JSON/CSV são derivados dos registros persistidos e podem ser reconstruídos. Isso prepara o projeto para um dashboard HTML simples, sem criar servidor web na V1.

## Integrações externas

| Serviço | Uso | Segurança |
| --- | --- | --- |
| **Binance Public Market Data** | Candles e preços públicos | Apenas leitura, sem credenciais de exchange |
| **API de notícias cripto** | Marketaux gratuito 30m + RSS complementar/alternativo 10m (D015/D016/D017); filtros/paginação/quota pendentes | Guardar publicação, primeira coleta, proveniência e limites/cobertura por fonte |
| **Polymarket** | Expectativas de eventos e métricas públicas | Apenas leitura; sem operações na plataforma |
| **OpenRouter / JEV** | Classificação de fatores externos e decisões probabilísticas | Chave em variável de ambiente, nunca nos logs |

A integração do JEV usa a **Decisions API**, e não o endpoint de chat:

```text
POST https://openrouter.ai/api/alpha/decisions
Model: typesafe/jev-1.13
Authorization: Bearer $OPENROUTER_API_KEY
```

O sistema registra `usage.cost`, tokens, latência, modelo e status de cada chamada quando disponibilizados. Custos **reais em USD** do OpenRouter ficam separados do saldo **virtual em USDT**. Chamadas compartilhadas entre B e C não devem ser cobradas duas vezes na contabilidade.

Pela [decisão D005](docs/DECISIONS.md), cada pedido JEV de classificação ou negociação permite uma chamada inicial e uma única repetição (`max_retries: 1`). As tentativas físicas são registradas separadamente, inclusive possível cobrança desconhecida após timeout. Prazo e orçamento podem impedir a repetição; restart preserva o contador. Falha final da decisão resulta em HOLD, com monitoramento de risco ativo.

O desenho aprovado usa **fatores externos com evidência curta**: cálculos do Polymarket são locais; classificações semânticas necessárias usam JEV e são reutilizadas entre decisões e B/C enquanto válidas. Todas as chamadas de classificação entram no mesmo orçamento global de IA. Esse processamento ainda depende de implementação e de critérios detalhados, conforme [D002](docs/DECISIONS.md) e [contexto de fontes](docs/FONTES_DE_CONTEXTO.md).

## Como executar (interface prevista)

> **Atenção:** os comandos abaixo fazem parte do contrato de implementação da POC. Eles estarão disponíveis **após o código Python ser implementado** conforme `docs/SPEC.md`; este README, sozinho, não disponibiliza um bot executável.

Preparação do ambiente:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

No arquivo `.env`, configurar localmente `OPENROUTER_API_KEY` para as consultas reais ao JEV. Nunca versionar credenciais.

Comandos previstos para execução e manutenção:

```bash
# Inicializar banco e validar componentes offline
python -m poc init-db --config config/default.yaml --run-id RUN_ID --profile trend_15m_v1
python -m poc smoke-offline --config config/default.yaml

# Testar UMA chamada ao OpenRouter (requer chave)
python -m poc smoke-openrouter --config config/default.yaml

# Coletar histórico de mercado sem criar trades retroativos
python -m poc backfill --config config/default.yaml --days 7

# Consultar perfis e iniciar uma nova sessão
python -m poc profiles --config config/default.yaml
python -m poc run --config config/default.yaml --new-session --profile trend_15m_v1

# Restaurar uma sessão existente, sem reinicializar capital
python -m poc run --config config/default.yaml --resume RUN_ID

# Consultar situação e gerar dados para análise
python -m poc status --config config/default.yaml --run-id RUN_ID
python -m poc report --config config/default.yaml --run-id RUN_ID --format json
python -m poc export --config config/default.yaml --run-id RUN_ID --format all
```

Em Linux, o caminho operacional aprovado é **Docker Compose**, com um motor por sessão, volumes locais persistentes e retomada a partir do SQLite. **Systemd** permanece alternativa nativa. Reiniciar o processo **não** reinicializa o capital nem permite duplicar operações. Se o serviço ficar offline, ele recompõe dados e avaliações pendentes, mas não executa ordens retroativas como se tivesse estado online. Os arquivos/comandos de deploy ainda precisam ser implementados e validados.

O banco e os artefatos pertencem à sessão escolhida. `trend_15m_v1` identifica o contrato técnico atual; implementação e homologação continuam pendentes. `--new-session` cria banco novo; `--resume RUN_ID` usa somente o existente, sem transformar erro de restauração em outra sessão. Comandos de dados identificam `--run-id RUN_ID`; o orçamento de IA não multiplica com a quantidade de sessões.

## Logs, métricas e futuro dashboard

O projeto será desenvolvido com observabilidade desde o início:

- **Decisões:** features, notícias disponíveis, contexto da memória, probabilidades, ação proposta, ação validada, motivos de rejeição.
- **Negociações virtuais:** ordens, preço de preenchimento, taxas, slippage, quantidade e PnL realizado.
- **Carteiras:** USDT disponível, ativo base em posição, patrimônio, retorno, exposição e drawdown.
- **Aprendizado:** resultados amadurecidos, padrões, tamanho da amostra e versões da memória.
- **Uso da IA:** chamadas, latência, tokens, falhas, custo efetivo em USD e custo desconhecido quando não houver informação de cobrança.
- **Operação:** heartbeat, falhas de mercado, atrasos de candles, reinicializações e recuperação.

A comparação principal é **C − B**, para avaliar o valor adicionado pelo Learning Engine, destacando o período em que a memória estiver disponível. **B − A** é complementar e avalia o pacote completo com JEV, notícias e Polymarket; não isola exclusivamente a contribuição do modelo. O relatório também avaliará resultado líquido simulado, risco e custo das chamadas da IA. O desenho mantém três carteiras por sessão/perfil; dois perfis após homologação terão trios independentes, conforme D009/D010. Contratos das novas fontes e implementação ainda estão pendentes.

Uma POC que termina com mais de 100 USDT **não comprova, por si só, vantagem estatística nem rentabilidade futura**. O objetivo é coletar evidências reproduzíveis, inclusive quando o desempenho for negativo.

O futuro frontend HTML poderá consumir `data/sessions/RUN_ID/exports/dashboard-latest.json` e os CSV. **A V1 inclui TUI terminal conectada aos motores após o núcleo; HTML permanece futuro.** Fase/fluxo remotos definidos em SPEC 15.4/D051.

## Garantias e limitações

- **Nenhuma ordem real:** sem depósitos, saques, credenciais de corretora ou rotas privadas para enviar ordens.
- **Falha segura:** sem preços válidos ou resposta confiável do JEV, não abrir posições por inferência.
- **Risco acima da IA:** saldo, stop-loss, take-profit, limites e estado da posição prevalecem sobre qualquer sugestão do modelo.
- **Auditoria:** configurações, decisões, resultados e custos devem ser reproduzíveis e rastreáveis.
- **Pesquisa, não aconselhamento:** o projeto é experimental e não representa promessa de ganhos financeiros.

## Roadmap da V1

- [ ] Estrutura Python, configuração, banco, broker virtual e testes offline.
- [ ] Coleta pública de mercado, indicadores e execução contínua sem duplicações.
- [ ] Integração OpenRouter/JEV, carteiras A/B/C e apuração de custos reais da IA.
- [ ] Outcome Evaluator, rótulos amadurecidos e Learning Engine contextual.
- [ ] Transferência automática entre moedas com catálogo/normalização/validação/gates.
- [ ] Core REST/WSS/token/2FA/lifecycle server-side e TUI V1 local/remota.
- [ ] Notícias e Polymarket, fatores com evidência curta e reutilização, relatórios, JSONL/CSV/JSON, operação com Docker Compose, alternativa systemd e testes de aceite.

**Documentação de implementação:** [`docs/SPEC.md`](docs/SPEC.md) define as regras e invariantes obrigatórias; [`AGENTS.md`](AGENTS.md) orienta os agentes de programação. Em caso de divergência, a especificação técnica é a referência para implementação.

**Contextos de desenvolvimento e operação:** [`docs/README.md`](docs/README.md) organiza a pesquisa de estilos de trade, as instruções para desenvolvimento e execução, o uso da TUI e os registros de decisões. Outros perfis dependem de contratos próprios; a TUI V1 está implementada e testada localmente.

## Referências

- [TypeSafe AI — JEV](https://docs.typesafe.ai/introduction)
- [OpenRouter — JEV 1.13](https://openrouter.ai/typesafe/jev-1.13)
- [OpenRouter — Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)
- [Binance — dados públicos de mercado](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)

---

*ai-trade-memory — decisões probabilísticas, memória própria e evidência mensurável.*

## Motor contínuo e diagnóstico JEV

```bash
uv run python -m poc run --new-session --profile trend_15m_v1 --symbol ETHUSDT --run-id eth-01
uv run python -m poc run --resume eth-01 --serve
uv run python -m poc backfill --run-id eth-01 --days 7
uv run python -m poc smoke-openrouter
docker compose up -d engine_btc
docker compose stop engine_btc
```

Compose restaura sessões previamente preparadas (`session-btc` e, no perfil `parallel`, `session-eth`), cada uma com seu SQLite/volume. Sem portas públicas; API interna usa 8081. Prepare os bancos pelo CLI antes do Compose. Alternativa systemd em deploy/jev-paper-trading@.service; ajuste usuário/caminhos locais e use apenas um supervisor por sessão. SIGTERM encerra tarefas e projeta eventos; fechar consultas não encerra o engine.

Configure OPENROUTER_API_KEY localmente. Smoke faz no máximo uma tentativa física, registra a cobrança observada e nunca chama o broker. HTTP 401/402/403 abre circuito persistido vinculado à credencial; corrigir a chave libera uma identidade de credencial nova. Não usar Binance keys. O orçamento global em data/operational/ai-budget.sqlite3 limita todas as sessões a 240 tentativas e US$ 0,05 observado/dia UTC. Custos ausentes ficam unknown; não há garantia de teto absoluto de fatura com cobrança desconhecida. Logs/exports incluem decisões, ai_calls e custos sem credenciais.

## Memória e datasets

```bash
uv run python -m poc import-learning --run-id eth-01 --input data/datasets/r001.jsonl
uv run python -m poc export-learning --run-id eth-01 --output data/datasets/r002.jsonl
uv run python -m poc evaluate-outcomes --run-id eth-01
```

Importe antes da primeira decisão ou selecione learning.initial_dataset_path no YAML antes de preparar. Sem arquivo, a sessão começa sem memória; restauração usa os dados aceitos no SQLite e não relê o arquivo. Export não sobrescreve versões existentes. Finanças nunca são importadas. Labels usam bid registrado nos 90s após maturação; candle histórico não fabrica uma cotação faltante. Sem amostras locais suficientes, C continua sem feedback útil. Origem estrangeira permanece arquivada; transferência automática usa uma camada separada com gates prospectivos. A camada estatística local declara dependência entre candles/horizontes.

## Contexto externo e relatórios

Coleta de RSS/Marketaux roda separada do risco. Marketaux usa somente a conta gratuita (100 requisições/dia compartilhadas e até três itens na primeira página), com truncamento explícito; token pode ser preenchido depois. Conteúdo novo/alterado é classificado pela Decisions API dentro do orçamento global e reutilizado. As decisões recebem fatores e evidência curta; artigos integrais e dados futuros não entram no prompt. B/C usam o mesmo snapshot externo. Sem fatores por falha/pendência, compras B/C ficam bloqueadas; saídas de risco continuam.

Polymarket usa apenas Gamma /markets, CLOB /book e Data /v2/trades públicos por GET. Proxy opcional fica em POLYMARKET_PROXY_URL no .env local; nunca em código ou export. Unidade Gamma ainda não suficientemente documentada nas referências verificadas: métricas bare permanecem UNVERIFIED, excluindo o sinal quantitativo até comprovação de unidade/semântica. Isso não impede fatores válidos de notícias.

Janela de notícias ajustada antes da sessão é respeitada na consulta/filtro/validade.
ID de evento Polymarket é referência inicial: associação literal requer pergunta e
regras completas iguais; grupos ambíguos ficam pendentes. Filtros precedem vagas e
seleção tem auditoria persistida. Deltas 5/60m usam livros realmente observados;
referência faltante aparece como indisponível. Datas de ocorrência exigem evidência
explícita; publicação/resolução não dão horário de acontecimento automaticamente.

Dashboard/CSV incluem decisões propostas/aprovadas/executadas, memória/outcomes, custo físico USD separado de patrimônio virtual USDT, comparação C−B/B−A e cobertura. Essas diferenças observadas não demonstram causalidade ou rentabilidade. Dados de fonte e classificação ficam auditáveis; falhas isoladas não apagam fatores elegíveis de outras fontes.

## Lifecycle e backups

```bash
uv run python -m poc start-engine --run-id minha-sessao
uv run python -m poc engine-status --run-id minha-sessao
uv run python -m poc stop-engine --run-id minha-sessao
uv run python -m poc backup --run-id minha-sessao --output data/backups/minha-sessao-r001
POC_DATA_DIR=/tmp/restore-isolado uv run python -m poc restore-backup --run-id minha-sessao --input data/backups/minha-sessao-r001
```

Runtime requer Docker no servidor e imagem local previamente construída; não baixa imagem automaticamente. Container usa UID/GID do operador, bind mount próprio e API em porta loopback alocada. Compose fornece alternativa de serviços explícitos para session-btc/session-eth; evite supervisores concorrentes. Credenciais são passadas somente por nomes de variáveis permitidos, sem valor em argumentos/comandos persistidos.

Alterar segredos no .env exige reiniciar o controle/processo nativo e recriar
containers dos motores preservando bancos/volumes: o ambiente é lido na partida,
e docker restart sozinho mantém o ambiente antigo do container. Chave JEV nova
usa outra identidade no circuito persistido, sem apagar orçamento/auditoria.

Backups incluem SQLite canônico e bases operacionais existentes, cada arquivo com seu próprio corte consistente; não há transação conjunta entre bancos. Arquivos/projeções não substituem o ledger. Restore preserva identidade e capital e rejeita destino existente/corrompido. Se precisar reconstruir orçamento/quota, bloqueia novas chamadas IA/Marketaux até o próximo dia UTC para não gastar capacidade incerta; RSS e risco/paper continuam. Não sobrescreve orçamento atual com backup antigo. Faça recuperação em diretório isolado, confira validate-data e só então planeje substituição do serviço parado.

## Transferência automática entre moedas

O engine publica exemplos maduros válidos em data/learning/catalog.sqlite3 por outbox; importação inicial continua fixa, sem reimportação por candle. Transferência é uma camada separada, ativada no template, ajustável antes da sessão. Fonte estrangeira nunca entra nos mínimos locais. Sem fontes, C segue sem complemento.

Padrões estrangeiros exigem 50 exemplos não neutros compatíveis. C salva previsões sombra sem IA/trade adicional; só usa o padrão após 30 avaliações futuras não sobrepostas e Brier estritamente melhor que o baseline salvo. Igualdade/piora/falta de cobertura suspendem o uso; locals têm prioridade e o contexto tem até três padrões totais. Não transfere carteira, pesos JEV ou aprovação ACTIVE para nova sessão. Diagnóstico: uv run python -m poc transfer-status --run-id minha-sessao. CSV de transfer_shadows/transfer_states inclui proveniência e métricas; catálogo/estados entram no backup.

## Controle e TUI V1

Proprietário de produção é configurado por você localmente; nenhum usuário/senha
padrão é criado pela aplicação. Configure o autenticador com a seed/URI exibida
pelo bootstrap, sem copiar esse segredo para logs/documentação:

```bash
uv run python -m poc bootstrap-owner --username meu-usuario
uv run python -m poc control-api --port 8080
# Em outro terminal; a TUI não precisa das chaves OpenRouter/Marketaux:
uv run python -m poc tui --server http://127.0.0.1:8080
```

`serve-control` é alias de `control-api`. Se a porta estiver ocupada, escolha outra
em ambos os comandos. Login usa senha e TOTP. Tokens ficam na memória da TUI;
refresh é rotativo. Recuperação do autenticador, exclusivamente no servidor:
`uv run python -m poc reset-owner-2fa --username meu-usuario`. A troca revoga tokens
anteriores. Banco de auth em data/control, separado dos motores; protege seed
TOTP e hashes com permissões locais restritas.

Na TUI: selecione sessão para visualizar; N cria com perfil/par/defaults e ajustes
JSON antes da partida, dataset opcional e transferência configurável. S inicia
ou retoma a sessão selecionada preservando banco/dinheiro/configuração. D abre
import/export; import inicial é bloqueado após a primeira decisão, export não
sobrescreve arquivo local. R atualiza; Tab navega; abas mostram decisões, memória,
eventos com filtro e configuração readonly; ? ajuda; O faz logout; Q sai.
Fechar a TUI ou o gateway não para motor. Parada explícita:
`uv run python -m poc stop-engine --run-id MINHA_SESSAO` no servidor, ou REST stop.

REST cuida dos comandos/snapshots/datasets; WS traz replay por cursor e dados
observáveis. Mercado/ledger são lidos do backend; nenhum saldo da imagem é usado.
Sem cotação/heartbeat atual, interface mantém diagnóstico de falta de atualização.
Contratos, limites e endpoints em [API_CONTROLE_V1.md](docs/API_CONTROLE_V1.md).
[Captura real](docs/relatorios/tui-v1-dashboard.svg) e
[terminal menor](docs/relatorios/tui-v1-terminal-pequeno.svg), ensaio E10.

### Controle em Docker e hospedagem posterior

Em Linux, a imagem do controle inclui apenas o CLI Docker além da base comum:

```bash
docker build -t ai-trade-memory:0.1.0 .
docker compose --profile control build control_api
export POC_UID="$(id -u)" POC_GID="$(id -g)"
export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
export POC_HOST_DATA_DIR="$PWD/data"
# Mesmo diretório no host e no mount /data do controle; usa 8080 por padrão.
export POC_CONTROL_PORT=8080
docker compose --profile control up -d control_api
```

O controle acessa o socket para lifecycle somente no servidor; a TUI usa a API.
Bind do controle mapeia POC_HOST_DATA_DIR para /data e o runtime utiliza o caminho
real do host nos mounts dos motores. Os motores montam somente sua sessão,
operational e learning, sem pasta control/auth; porta da API do motor em loopback.
Não rode outro supervisor para o mesmo run_id.

Para acesso remoto, configure DNS seu e proxy TLS (sem expor motores):

```bash
export POC_PUBLIC_HOST=seu-dominio.example
docker compose --profile control --profile remote up -d control_api tls_proxy
uv run python -m poc tui --server https://seu-dominio.example
```

Caddyfile validado localmente; domínio/certificado público e estabilidade externa
não foram testados. HTTP remoto é recusado. A aplicação não instala firewall ou
publica domínio por conta própria. Segredos seguem .env/ambiente privados.

## Validação atual e limites

191 testes conjuntos passaram após integrar REST/WS/TUI e revisar contexto/E11; casos sintéticos
ficam exclusivamente em fixtures/temporários e não entram no catálogo operacional.
Binance REST/WS e Docker/lifecycle/backup/restore têm ensaios reais locais. Gateway
nativo e em Docker preservaram motores no logout/SIGTERM; cliente TUI exibiu sessão
real. [Status/evidências](docs/STATUS_DESENVOLVIMENTO.md) detalham cada etapa.

OpenRouter autenticado respondeu 401 no ensaio: integração com resposta válida
continua pendente e a chave rejeitada não é reenviada indefinidamente. Token
Marketaux fica para preenchimento posterior pelo usuário; RSS tem cobertura
parcial explícita. Gamma/CLOB/Data Polymarket acessíveis pelo proxy local, mas
campos Gamma com unidade USD não suficientemente documentada permanecem excluídos
dos sinais quantitativos. Não há prova de ACTIVE transferido/rentabilidade real.
O ensaio obrigatório de 24 horas ainda não foi concluído; não declarar aceite
operacional desassistido antes dessa evidência.

### Atualização de imagens e observação prolongada

Depois de atualizar código/schema, reconstrua a imagem e recrie containers
parados preservando os mesmos volumes. O runtime rejeita início de container
parado com imagem diferente da tag atual; não migra banco para código antigo.
Em Compose: `docker compose up -d --force-recreate engine_btc` (idem engine_eth).
Para runtime dinâmico, pare explicitamente e remova somente o container
identificado por engine-status, sem remover volumes/diretório; start-engine
recria usando o banco aceito. Backup/restore permanece disponível.

Ensaio E11 iniciado com sessões próprias acceptance-v1-btc e acceptance-v1-eth.
São novos trios de paper, com configurações/identidades isoladas. Consultar:

```bash
uv run python -m poc engine-status --run-id acceptance-v1-btc
uv run python -m poc status --run-id acceptance-v1-btc
uv run python -m poc validate-data --run-id acceptance-v1-btc
uv run python -m poc validate-data --run-id acceptance-v1-eth
```

Início não equivale a conclusão de 24h. JEV rejeitado/Marketaux ausente e métricas
Gamma não verificadas continuam registrados; decisões técnicas e proteção
funcionam com fontes públicas disponíveis. Nenhuma rentabilidade ou homologação
é presumida.

Observador readonly, sem lifecycle ou novas inferências, grava amostras periódicas
de saúde, auditoria/capital, duplicidade, cutoff da memória/fills, custos/fontes e
imagem. Use uma pasta nova para cada ensaio:

```bash
uv run python -m poc observe --run-id acceptance-v1-btc --run-id acceptance-v1-eth \
  --output data/acceptance/MEU_ENSAIO --duration-hours 24 --poll-seconds 60
```

Observação final corrente em `data/acceptance/v1-20261012-final/observation.json`,
iniciada 12/10/2026 21:57 UTC; mínimo previsto 13/10 21:57 UTC (18:57 Brasília).
`COMPLETED` significa tempo de relógio decorrido; revise amostras de degradação e
limitações das fontes antes do aceite. Parar o observador não para motores.
[Relatório E05/E11](docs/relatorios/VALIDACAO_E05_E11.md) registra a prévia, retomadas,
backup/restore e dataset real BTC→ETH, sem afirmar transferência ACTIVE ou lucro.
