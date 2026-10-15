# Candidato para nova sessão de paper trading — 14/10/2026

**Corte Binance:** 14/10/2026, 13:27:02 de Brasília / 16:27:02 UTC.
Leituras públicas, sem credenciais Binance, inferência JEV ou alteração da sessão ETH.

## Candidato recomendado

**SOLUSDT** como próxima sessão de teste: combina volatilidade superior à do
ETH no recorte observado, maior volume que várias alternativas mais voláteis
e candidatos de contexto no Polymarket. É uma escolha para experimentar o
bot em paper trading, não uma recomendação de compra imediata ou garantia de
mais operações lucrativas.

**SUIUSDT** foi o destaque em volatilidade entre os dez pares pesquisados.
Pode servir a um ensaio posterior de oscilações maiores, mas teve menor
volume negociado e nenhum candidato passou os pisos básicos de metadados
no recorte consultado de sua tag Polymarket. Isso enfraquece a escolha para
o teste atual de enriquecimento JEV, sem provar ausência global de contexto.

## Comparação

| Par | Volatilidade equivalente diária, últimos 7 dias | Volume Spot Binance em 24h, milhões de USDT | Spread observado, % |
|---|---:|---:|---:|
| SUIUSDT | 4,34% | 48,56 | 0,00984% |
| AVAXUSDT | 4,05% | 26,72 | 0,01014% |
| ADAUSDT | 4,01% | 21,44 | 0,04383% |
| LINKUSDT | 3,31% | 22,24 | 0,00802% |
| SOLUSDT | 2,85% | 228,24 | 0,00961% |
| DOGEUSDT | 2,80% | 46,64 | 0,01215% |
| XRPUSDT | 2,68% | 165,82 | 0,00752% |
| ETHUSDT | 2,13% | 615,75 | 0,00041% |
| BNBUSDT | 1,76% | 54,37 | 0,00137% |
| BTCUSDT | 1,56% | 1.398,44 | 0,00001% |

SOL teve aproximadamente **34% mais volatilidade que ETH**; XRP, **25% a
mais**; SUI, **103% a mais**. São relações medidas nessa janela, não uma
propriedade permanente das moedas nem estimativas de lucro diário.

Todos os pares estavam `TRADING` e permitiam Spot. O spread corresponde a
uma única observação do melhor bid/ask, não a uma média histórica nem a uma
garantia de profundidade. Volume é do par Binance, não do mercado global.

## Método

- Mesma janela nos dez pares: 671 candles fechados de 15m, aberturas desde
  07/10 às 16:30 UTC e último fechamento em 14/10 às 16:15 UTC.
- Retornos simples de fechamento a fechamento, em percentual. Volatilidade:
  desvio padrão amostral desses retornos multiplicado por `sqrt(96)`,
  equivalente diário descritivo, sem anualização. O candle em formação foi
  excluído. Os últimos sete dias contêm 671 candles completos elegíveis
  porque o corte aconteceu entre fechamentos.
- Preços, volumes, retornos e spread calculados com `Decimal`. Indicadores
  técnicos calculados pelo `FeatureEngine` existente, sem alterar seu código,
  usando histórico de até 1.000 candles de 15m e 240 de 1h. Esse aquecimento
  de pesquisa não reconstrói o estado histórico exato da sessão ETH.
- Snapshot de 24h é a janela móvel informada pelo provedor no momento da
  consulta, distinta da janela de sete dias usada para volatilidade.

## Polymarket e notícias

Leitura Gamma pública via proxy configurado, sem chamadas ao JEV. Uma página
de até 100 mercados por tag específica, com ordenação por volume 24h:

| Ativo | Mercados recebidos na página | Ativos, com livro habilitado, liquidez reportada ≥ US$ 10 mil e volume 24h ≥ US$ 1 mil |
|---|---:|---:|
| SOL | 100 | 10 |
| XRP | 100 | 8 |
| SUI | 9 | 0 |

Esses são **candidatos de metadados**, não fatores já elegíveis para o bot.
Não foram validados nesta pesquisa profundidade, spread do livro Polymarket,
recência do negócio, associação ao acontecimento, relevância ou prazo.
A classificação e todos os filtros continuam obrigatórios numa nova sessão.
A página de 100 registros não comprova cobertura completa de SOL/XRP.

Notícias Marketaux/RSS por nova moeda não foram classificadas nem tiveram
cobertura quantitativa validada nesta pesquisa. Não há promessa de que a
coleta produzirá fatores utilizáveis em todos os ciclos.

## Efeito sobre o perfil atual

No corte, os dez pares tinham tendência de 1h `bearish` e nenhum cumpria
todos os critérios de entrada da carteira A do `trend_15m_v1`. SOL tinha RSI
aproximadamente 38,3; XRP, 33,1; SUI, 39,4, todos abaixo do mínimo 45 da A.
Volatilidade maior também pode significar queda maior; não autoriza relaxar
os filtros para fabricar compras ou concluir que o JEV decidirá comprar.

Se SOL for escolhida, criar sessão separada e preservar a ETH. Não foi criada
ou iniciada nova sessão nesta pesquisa. Compartilhamento do orçamento global
de IA precisa ser considerado na comparação simultânea.

## Fontes e evidências

- [Documentação oficial Binance: dados públicos sem chave](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md).
- [Documentação Spot REST](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md): `/api/v3/time`, `/ticker/24hr`, `/ticker/bookTicker`, `/exchangeInfo` e `/klines`, consultados em `https://data-api.binance.vision`.
- [Página oficial de mercados Solana](https://polymarket.com/crypto/solana).
- [Mercados XRP em outubro](https://polymarket.com/event/what-price-will-xrp-hit-in-october-2026).
- Gamma: `https://gamma-api.polymarket.com/tags/slug/{slug}` e `/markets`; tags `solana`, `xrp`, `sui`. Não foram armazenadas credenciais nas evidências.

Artefatos públicos locais em `data/research/coin-candidates-20261014T162707Z/`:

- [Resumo e indicadores](../../data/research/coin-candidates-20261014T162707Z/summary.json).
- [Comparação CSV](../../data/research/coin-candidates-20261014T162707Z/comparison.csv).
- [Respostas públicas Binance](../../data/research/coin-candidates-20261014T162707Z/public_responses.json).
- [Triagem pública Polymarket](../../data/research/coin-candidates-20261014T162707Z/polymarket_metadata.json).
- [Hashes SHA-256](../../data/research/coin-candidates-20261014T162707Z/sha256.json).

Dados locais são ignorados pelo Git. Nenhum parâmetro, carteira ou serviço
operacional foi alterado; não houve compra real ou simulada nesta pesquisa.
