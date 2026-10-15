# Moedas para os perfis scalping, day trade e swing

**Pesquisa em 14/10/2026.** Corte comum dos candles: **17:58 UTC / 14:58 de
Brasília**. Seleção para experimentar a POC em paper, sem executar sessões ou
validar rentabilidade. Não altera perfis, serviços, carteiras ou dataset real.

## Proposta para discussão

| Perfil | Primeiro candidato | Alternativas | Motivo e limitação |
| --- | --- | --- | --- |
| Scalping 1m/5m | **ZECUSDT** | SUIUSDT; SOLUSDT para referência menos volátil | Maior oscilação que SOL, volume elevado e spread muito estreito na amostra. Stop atual equivale a cerca de 1,9 ATR de 1m no corte; isso não é calibração nem probabilidade de sucesso. Descoberta específica de Zcash precisa de atenção. |
| Day trade 15m/1h | **SUIUSDT** | NEARUSDT para maior intensidade; UNIUSDT | Volatilidade superior a SOL/XRP, liquidez suficiente para os pequenos tamanhos da POC e stop de 1% menos apertado em relação ao ATR que em NEAR. Cobertura direta Polymarket não comprovada. |
| Swing 4h/1d | **UNIUSDT** | AVAXUSDT; NEARUSDT após revisar risco | Histórico suficiente, volatilidade intermediária/alta e mais candidatos técnicos históricos do template que SUI/SOL. Não implica mais trades lucrativos; pode passar períodos sem entrada. |

NEAR é a alternativa mais forte para intensificar o movimento com volume
relevante. Sua amplitude também torna os stops fixos atuais relativamente
estreitos; não escolhi automaticamente a moeda mais volátil para cada perfil.
As escolhas acima são inferências desta triagem, não resultados de desempenho.

SOL permanece útil como referência para o conjunto JEV/fontes: há mapeamento
específico de ativo já implementado e maior oferta de metadados Polymarket que
nos candidatos principais. Não há garantia de fatores elegíveis em todo ciclo.

## Comparação dos candidatos

Volatilidade abaixo é o desvio padrão dos retornos percentuais simples de 15m,
escalado por `sqrt(96)` para uma unidade equivalente diária, nas janelas de sete
e trinta dias. **Não é retorno, lucro médio, amplitude diária nem previsão.**
Spread é a mediana de 12 leituras públicas, entre 18:01:40 e 18:02:51 UTC;
volume é a janela móvel de 24h da Binance consultada aproximadamente às 17:57 UTC.

| Par | Vol. 7d | Vol. 30d | Volume 24h, milhões USDT | Spread mediano, % | Papel sugerido |
| --- | ---: | ---: | ---: | ---: | --- |
| ZECUSDT | 4,99% | 5,74% | 230,38 | 0,00086% | Prioridade scalping |
| SUIUSDT | 4,35% | 5,53% | 50,85 | 0,00976% | Prioridade day trade |
| UNIUSDT | 4,62% | 6,11% | 47,05 | 0,01403% | Prioridade swing |
| NEARUSDT | 7,41% | 8,26% | 155,71 | 0,02073% | Alternativa mais agressiva |
| AVAXUSDT | 4,04% | 5,04% | 26,83 | 0,01013% | Alternativa swing |
| SOLUSDT | 2,86% | 2,91% | 230,59 | 0,00960% | Referência de execução/contexto |
| XRPUSDT | 2,67% | 3,53% | 164,95 | 0,00753% | Alternativa líquida, menos volátil neste recorte |
| ETHUSDT | 2,12% | 2,27% | 629,12 | 0,00041% | Referência do ensaio anterior |
| QNTUSDT | 6,21% | 13,00% | 24,80 | 0,00489% | Reservar para estresse/outliers |
| STRKUSDT | 15,69% | 10,61% | 23,09 | 0,01991% | Reservar para estresse/microestrutura |

As leituras são de Spot USDT da Binance, não volume global. Uma amostra de cerca
de um minuto não comprova spread/profundidade sustentáveis por um mês.

## Compatibilidade com os parâmetros atuais

ATR é amplitude verdadeira média, não direção ou chance de acerto. Referência
conceitual: [Fidelity — ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr).
Os números seguintes usam o `FeatureEngine` de produção com os parâmetros e
600 candles de cada intervalo do template, no corte comum da pesquisa.

| Par | ATR 1m | ATR 15m | ATR 4h | Interpretação descritiva |
| --- | ---: | ---: | ---: | --- |
| ZEC | 0,185% | 1,178% | 4,117% | Stop scalp 0,35% ≈ 1,9 ATR; stops day/swing abaixo de um ATR dos respectivos candles neste corte. |
| SUI | 0,171% | 0,911% | 3,119% | Stop day 1% ≈ 1,1 ATR; menos extremo que NEAR, ainda precisa de observação. |
| UNI | 0,184% | 0,926% | 3,298% | Stop swing 4% ≈ 1,2 ATR de 4h. |
| NEAR | 0,273% | 1,425% | 4,822% | Stop day 1% ≈ 0,7 ATR e swing 4% ≈ 0,83 ATR: oscilação normal pode cruzá-los. |
| AVAX | 0,112% | 0,712% | 2,765% | Alternativa swing menos intensa que UNI/NEAR. |
| SOL | 0,108% | 0,634% | 2,126% | Menor movimento; parâmetros têm outra escala em ATR. |
| STRK | 0,321% | 1,837% | 10,494% | Extremo para stops fixos atuais; movimento não equivale a oportunidade executável. |

Não existe um múltiplo de ATR universalmente correto. A comparação identifica
incompatibilidades possíveis; não justifica trocar stops automaticamente ou
implementar stop ATR. Qualquer ajuste deve ser revisado e fixado no perfil antes
da sessão destinada ao teste extenso.

No livro observado, o menor lado dentro de ±0,1% do midpoint tinha pelo menos
US$ 199,8 mil em ZEC, 93,8 mil em SUI, 34,4 mil em UNI, 55,7 mil em NEAR e
279,3 mil em SOL. São somas dos primeiros 100 níveis; quando o recorte não atinge
a borda da faixa, representam limite inferior do livro visível, não profundidade
total garantida. São muito superiores ao tamanho inicial de aproximadamente
20 USDT por entrada da POC, mas não garantem preço durante inferência.

Taxas e slippage **configurados na simulação**, mais o spread amostrado, exigem
movimento aproximado de 0,30–0,32% apenas para equilíbrio de uma ida e volta nos
candidatos principais. Não são taxas reais verificadas da conta Binance. O
alvo scalp de 1,20% continua sendo alvo bruto do perfil, não lucro por operação.

## Os templates encontrariam sinais?

Triagem histórica **aproximada**, sem executar o bot/JEV ou simular fills:

| Par | Scalping: cruzamentos / candidatos A, 7d | Day trade: rompimentos / candidatos A, 30d | Swing: rompimentos / candidatos A, 90d |
| --- | ---: | ---: | ---: |
| ZEC | 227 / 8 | 199 / 18 | 31 / 5 |
| SUI | 233 / 11 | 238 / 35 | 27 / 1 |
| UNI | 246 / 11 | 205 / 33 | 35 / 8 |
| NEAR | 234 / 11 | 230 / 34 | 34 / 10 |
| AVAX | 205 / 7 | 248 / 27 | 34 / 6 |
| SOL | 215 / 12 | 177 / 23 | 23 / 2 |
| XRP | 234 / 12 | 189 / 23 | 21 / 1 |

Primeiro número: somente setup estrutural. Segundo: setup com RSI, volume,
alinhamento EMA, MACD, tendência mais lenta e agenda da A. B/C têm suas próprias
avaliações e não exigem todas as confirmações adicionais da A.

Os números **não são operações, taxa de acerto ou chamadas previstas**: ignoram
posição, cooldown, espaçamento, tetos, orçamento, contexto, inferência e custos.
Indicadores históricos usam a série coletada, não replay exato de janelas móveis
de 600/restarts; cada instante usa somente candles que já haviam fechado, mas
não reconstrói a disponibilidade/latência histórica. Somente o snapshot técnico
atual foi calculado pelo builder de produção com sua janela de 600.

Em swing, oito candidatos A em 90 dias para UNI não sustentam promessa de muitas
operações em um mês. SUI teve apenas um, motivo para não priorizá-la em swing
usando este template. Mais volatilidade não garante mais sinais válidos.

**No corte, nenhum dos candidatos principais tinha compra técnica válida.**
Em ZEC/SUI/UNI/NEAR, a tendência de 1h era de baixa; a diária era de alta,
mas sem rompimento válido de swing. Selecionar uma moeda para testar não é
recomendar abrir posição imediatamente nem forçar compras para obter amostras.

## Por que não começar pelos extremos?

- **QNT:** volatilidade 30d de 13%, mas 7d de 6,21%. Um retorno de fechamento
  de 15m de +31,68% em 27/09 às 22:45 UTC influencia a janela; o 1% de maiores
  retornos ao quadrado responde por 52% da soma de quadrados dos retornos.
  Semelhança com um pico não demonstra movimento recorrente negociável.
- **STRK:** volatilidade 7d de 15,69%; spread excedeu o teto scalp de 0,05%
  em uma das 12 leituras, chegando a 0,05307%. ATR 1m de 0,321% está próximo do
  stop 0,35%. Bom candidato posterior a estresse, não minha primeira opção.
- **WAL:** variação 24h de +62,55% no ticker, spread mediano de 0,05686% nas
  seis leituras iniciais e somente 369 candles diários disponíveis. O preset
  swing exige 600; não inicia com esses defaults.
- **PEPE:** spread mediano observado de 0,24480% na triagem inicial, acima dos
  tetos atuais de scalping, day trade e swing. Preço unitário baixo não implica
  baixo custo proporcional.
- **HYPE:** apenas 20 candles diários; janela 30d/90d incompleta e sem warmup
  swing suficiente. Não comparar suas métricas parciais como janelas completas.
- **PUMP, ONDO e MUBARAK:** 398, 551 e 566 candles diários respectivamente;
  não atendem ao warmup diário de 600 do preset swing sem outra configuração
  aprovada. Não fabricar histórico para completar o template.

## Notícias e Polymarket

Consultas públicas pelo proxy já configurado funcionaram. A pesquisa usou
cache SQLite próprio em `data/research/`, sem renovar cache operacional,
classificar com JEV ou consumir a cota Marketaux.

Pela descoberta real do motor, com seus tetos e filtros:

| Ativo | Mercados diretos acima dos pisos de liquidez/volume | Após associação/metadados válidos | Livros/negócios aprovados na amostra |
| --- | ---: | ---: | --- |
| SOL | 11 | 2 | 0 de 2 avaliados |
| XRP | 7 | 2 | 0 de 2 avaliados |
| SUI | 0 | 0 | Nenhum candidato direto nesse recorte |
| ZEC | 0 | 0 | Busca do motor caiu na tag genérica crypto |
| NEAR | 0 | 0 | Busca do motor caiu na tag genérica crypto |
| UNI | 0 | 0 | Busca do motor caiu na tag genérica crypto |

SOL/XRP falharam por spread, profundidade e negócio recente no snapshot.
BTC teve um aprovado entre três verificados, mostrando que os filtros foram
efetivamente aplicados. Isso não prova ausência de cobertura global ou futura;
apenas uma página/snapshot e até três livros por ativo foram inspecionados.
Mercados macro não estão contados como cobertura direta da moeda.

Consulta adicional por nomes canônicos encontrou a tag `zcash` com 100 mercados
recebidos, `uniswap` com sete e `starknet` vazia, todos sem candidatos aprovados
nos metadados/associação desse recorte. O motor atualmente tenta `zec`/`uni`
e usa fallback crypto; o catálogo de aliases possui nomes completos somente
para BTC, ETH, SOL, BNB e XRP. **Mapeamento de nomes para os novos ativos é
um ponto concreto a revisar se quisermos avaliar seu enriquecimento específico.**
Não foi alterado nesta pesquisa. Consultas `near-protocol`, `quant` e `injective`
retornaram 404; isso não demonstra inexistência de outros slugs/mercados.

RSS configurado: Cointelegraph retornou 30 itens; CoinDesk respondeu 308 e não
foi alterado. No título/resumo publicado nas últimas 24h havia cinco menções a
BTC, uma a ETH e uma a SOL; zero para ZEC/SUI/UNI/NEAR nesse pequeno recorte.
Starknet apareceu por nome completo, mas não pelo ticker STRK, reforçando o
limite do mapa atual. **Marketaux por candidato ainda não foi validado**; zero
menções no RSS não equivale a ausência de notícias ou impacto neutro.

Não confundir teste de funcionamento com teste do enriquecimento: sem fatores
adequados, poderemos avaliar execução/risco e as decisões possíveis sob cobertura
limitada, mas não demonstrar contribuição do Polymarket naquela amostra. Não
reduzir seus filtros ou inventar relação macro para produzir fatores.

## Planejamento do teste extenso

O trio proposto é **ZEC/scalping, SUI/day trade e UNI/swing**. Se a prioridade
for isolar o efeito do perfil, escolher a mesma moeda para os três reduz o
confundimento entre ativo e estilo; moedas diferentes servem a ensaios distintos,
sem comparação direta de rentabilidade entre perfis. Dentro de cada sessão,
A/B/C continuam comparáveis sob o mesmo ativo/perfil/configuração.

Três ativos com Marketaux a cada 30 minutos demandariam nominalmente 144
consultas/dia, acima das 100 do plano gratuito. A [página oficial de preços](https://www.marketaux.com/pricing)
confirma 100 requisições/dia e três artigos por consulta. Uma opção a revisar
antes da partida é 60 minutos por ativo, nominalmente 72/dia antes de falhas;
não alterada aqui. Perfis sobre o mesmo ativo podem reutilizar coletas por ativo.

O teto global atual de 240 chamadas JEV continua compartilhado. Nos tetos de
ciclos dos três templates (80 + 96 + 6), duas inferências B/C distintas por ciclo
exigiriam até 364 chamadas, antes de classificação/retry; compartilhamento B/C e
filtros podem reduzir a demanda, sem garantir cobertura de todos os ciclos.
Registrar descartes/quota na análise para não atribuir HOLD por limite ao modelo.

Para o mês, fixar moeda, revisão e parâmetros escolhidos e acompanhar também
fills, motivos de bloqueio, custos líquidos, drawdown, latência e cobertura.
Memória só é utilizável após mínimos e maturação; swing pode continuar sem
amostras suficientes, mesmo após um mês. O usuário decide a duração, sem gate
obrigatório de 24h. Nenhuma sessão foi criada, publicada ou iniciada aqui.

## Método, fontes e artefatos

- Universo: 32 pares nativos Spot USDT ativos, selecionados pelo maior volume
  24h entre os com ao menos 10 milhões USDT. Excluídos stablecoins, fiat, ouro e
  ações tokenizadas explicitamente enumerados no arquivo do universo. É uma
  amostra dos líquidos atuais, sujeita a viés de seleção, não todo o mercado.
- Histórico: 15m para 7/30 dias, 4h para 90 dias; série adicional para warmup.
  Nos 12 finalistas, 1m/5m para sete dias e warmup. Diário de até 720 registros
  requisitados para verificar a disponibilidade de 600 candles fechados.
- Validados **120 arquivos, 329.212 candles fechados**, sem gaps, duplicatas,
  OHLCV inválido ou fechamento futuro. HYPE tem cobertura histórica parcial
  identificada, não preenchida. A disponibilidade histórica de quotes não é
  reconstruída pelos candles.
- Preços/volumes/spreads/cenários em `Decimal`; indicadores técnicos usam floats
  conforme o domínio existente. Retornos/ATR não foram inseridos em bancos de
  sessão, labels ou catálogo de aprendizado.
- [Binance — dados públicos](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)
  e [Spot REST](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md):
  `/api/v3/time`, `/exchangeInfo`, `/ticker/24hr`, `/ticker/bookTicker`,
  `/klines` e `/depth` em `https://data-api.binance.vision`.
- [Binance Academy — scalping](https://www.binance.com/en/academy/articles/what-is-scalping-trading-in-cryptocurrency),
  [day trade](https://www.binance.com/en/academy/articles/a-beginners-guide-to-day-trading-cryptocurrency)
  e [swing](https://www.binance.com/en/academy/articles/a-beginners-guide-to-swing-trading-cryptocurrency)
  fundamentam distinções de horizonte/custos; não indicam nossos thresholds.
- [Polymarket — dados](https://docs.polymarket.com/market-data/overview) e
  [detalhes de mercado](https://docs.polymarket.com/market-data/market-details).
  APIs Gamma/CLOB/Data somente leitura, limites atuais do projeto preservados.

Evidências em `data/research/profile-coins-20261014/`, ignoradas pelo Git:

- [Comparação dos 32 pares CSV](../../data/research/profile-coins-20261014/market_comparison.csv).
- [Métricas e janelas JSON](../../data/research/profile-coins-20261014/market_screen.json).
- [Compatibilidade com perfis](../../data/research/profile-coins-20261014/profile_fit.json).
- [Polymarket e RSS](../../data/research/profile-coins-20261014/context_coverage.json).
- [Triagem de notícias por nomes/tickers](../../data/research/profile-coins-20261014/news_screen.json).
- [Verificação de dados e concentração](../../data/research/profile-coins-20261014/data_quality.json).
- [Hashes](../../data/research/profile-coins-20261014/sha256.json).

Scripts e respostas públicas completos ficam na mesma pasta. Não foram salvos
proxy, senhas ou chaves nos artefatos. Nenhuma alteração do core/TUI ou reinício
de serviço foi necessário para esta pesquisa.
