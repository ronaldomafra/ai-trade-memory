# Evidências E00/E01 — 12/10/2026

Implementação inicial da SPEC 1.50, mantendo o objetivo da V1 completa em andamento. E02–E11 ainda pendentes/em desenvolvimento.

## Verificações executadas

- uv sync: dependências resolvidas/travadas em uv.lock, ambiente Python 3.11.15.
- uv run pytest -q: 55 testes passaram.
- uv run ruff check e ruff format: verificados sobre código e testes novos.
- uv build: distribuição Python gerada; migration SQL incluída no wheel.
- CLI config-check/help/smoke-offline/status/validate-data e reconstrução JSONL exercitados.
- GET público exchangeInfo BTCUSDT: consulta real via adaptador, base BTC, cotação USDT e incremento 0.00001; sessão verification-market-btc criada com 100 USDT por carteira e nenhum fill.

Os testes cobrem configuração/limites, Decimal, taxas dentro de orçamento, increments BTC/ETH, risco/UTC/precedência/latch, recuperação de proteção pendente, atomicidade com crash injetado no ledger, concorrência de duas conexões e idempotência pós-retomada. Também validam isolamento/restore/locks, controles GET-only, fronteiras hexagonais e projeções/rebuild após append incompleto.

## Artefatos locais

Smoke de referência: data/sessions/smoke-e9e2473f30654cf9/poc.sqlite3, logs e exports. Audit retornou ok, seis fills e três trades fechados, todos sintéticos. Não são evidências de rentabilidade ou chamadas JEV. Dados runtime ficam no gitignore.

## Limitações e próxima etapa

Não foram testados OpenRouter/Marketaux/Polymarket, feeds contínuos, Docker ou TUI. Não houve ordens reais nem carregamento de credencial de exchange. Dataset não é ativado sem importer validado E04. Próxima entrega E02: indicadores/mercado/ciclos/A/continuidade.

Semântica dos filtros consultada na [documentação oficial Binance](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md). Os limites públicos de quantidade/notional são aplicados ao fill simulado; o motor não reproduz o matching/valor médio de execução de uma ordem real.
