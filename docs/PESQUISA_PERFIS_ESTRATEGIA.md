# Pesquisa para os perfis swing, scalping e day trade

**Consulta: 14/10/2026.** Pesquisa para orientar implementação paper-only; não é
validação de rentabilidade. O [plano](PLANO_PERFIS_ESTRATEGIA.md) separa requisitos
do usuário, mecanismos implementáveis e defaults experimentais propostos.

## 1. Fontes e limites da pesquisa

Usadas fontes dos próprios provedores de mercado, instituições e autores, com
referências técnicas oficiais para o transporte. Os materiais educacionais
descrevem métodos; não demonstram que nossos valores de EMA/RSI/stop funcionam em
ETH ou outra moeda. Exemplos com derivativos não autorizam derivativos nesta POC.

| ID | Fonte primária | Contribuição utilizada |
| --- | --- | --- |
| R1 | [Binance Academy — swing](https://www.binance.com/en/academy/articles/a-beginners-guide-to-swing-trading-cryptocurrency) | Horizonte de dias/semanas; referências de 4h/diário e famílias de tendência/rompimento. |
| R2 | [Fidelity — swing trading](https://www.fidelity.com/learning-center/trading-investing/trading/swing-trading) | Entrada por confirmação de direção ou recuperação; regras de saída e risco. |
| R3 | [Binance Academy — scalping](https://www.binance.com/en/academy/articles/what-is-scalping-trading-in-cryptocurrency) | Movimentos curtos, velocidade, custos/liquidez e métodos de momentum/range. |
| R4 | [IG — custos do scalping](https://bts.ig.com/en/trading-opportunities/beginners-guide-to-scalping-41249-171220) | Repetição de custos e relação entre ganhos pequenos, perdas e taxa de acerto. |
| R5 | [Binance Academy — day trade](https://www.binance.com/en/academy/articles/a-beginners-guide-to-day-trading-cryptocurrency) | Entrada/saída intradiária e distinção entre mercado tradicional e cripto contínuo. |
| R6 | [Fidelity — RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI) | Momentum e limites da interpretação de sobrecompra/sobrevenda. |
| R7 | [Fidelity — ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr) | Medida de volatilidade e diferença entre stop fixo e adaptado à volatilidade. |
| R8 | [Fidelity — Bollinger Bands](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands) | Bandas relativas à volatilidade; hipótese distinta de reversão/range. |
| R9 | [Binance.US — suporte/resistência](https://support.binance.us/en/articles/9843935-the-basics-of-support-and-resistance-explained) | Níveis/zones, rompimentos e falsas confirmações. |
| R10 | [Binance — streams públicos](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md) | Intervalos, candle fechado, ritmo do stream e bookTicker. |
| R11 | [Binance — REST público](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md) | Klines UTC, limite/paginação e reconstrução de dados. |
| R12 | [Bailey et al. — The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) | Selecionar configurações pelo mesmo histórico pode produzir falsa vantagem. |

Não houve coleta autenticada, backtest novo, chamada JEV ou teste de execução dos
presets para realizar esta pesquisa. Não foi necessário acessar Polymarket:
seus contratos existentes são reaproveitados, com horizonte/contexto por perfil.

## 2. Estilo não determina sozinho a estratégia

Swing, day trade e scalping descrevem principalmente horizonte e frequência.
Uma implementação precisa escolher família, disparo, invalidação, tamanho,
agenda e custos. Scalping também é uma forma de operação intradiária; os nomes
se sobrepõem. No catálogo, terão IDs distintos para evitar comportamento ambíguo.

| Família pesquisada | Como se pretende obter entrada | Falha típica | Destinação nesta entrega |
| --- | --- | --- | --- |
| Tendência/momentum | Alinhamento direcional e confirmação de força | Mercado lateral e reversão brusca | Reutilizar EMAs/MACD/RSI existentes. |
| Rompimento | Fechamento supera máxima anterior com confirmação | Falso rompimento, chase e retorno ao range | Família escolhida para os presets day trade/swing. |
| Pullback em tendência | Recuperação após recuo numa tendência válida | Comprar uma reversão real como se fosse recuo | Pesquisada; não acrescentar outra máquina de estados agora. |
| Cruzamento de médias | Média curta cruza acima da média de referência | Atraso e sucessivos cruzamentos no range | Família escolhida para scalping de minutos. |
| Reversão à média/range | Retorno após afastamento de uma referência | Tendência persiste e o desvio aumenta | Pesquisada; adiar, sem atribuir reversão a um RSI isolado. |
| Spread/market making/HFT | Microestrutura e execução de ordens passivas | Fila, adverse selection, velocidade e inventário | Fora: bookTicker + taker paper não simula fila nem confirma fill passivo. |

A escolha de duas famílias simples para três estilos é uma **decisão de desenho
proposta para a POC**, não conclusão empírica sobre qual estratégia vence.

## 3. Swing

As referências descrevem posições por dias ou semanas, utilizando estrutura em
gráficos mais lentos. Isso pede tempo em posição e avaliação de aprendizado mais
longos que o legado de quatro horas. A combinação 4h/1d é coerente com essa
descrição, mas os intervalos exatos continuam escolhas experimentais. [R1](https://www.binance.com/en/academy/articles/a-beginners-guide-to-swing-trading-cryptocurrency)

Entrada após confirmação e compra de um recuo são hipóteses diferentes. Escolhemos
inicialmente rompimento confirmado de máxima anterior, para tornar o nível e a
invalidação reproduzíveis sem interpretação visual de padrões. O fechamento do
próprio candle não pode participar da máxima que pretende romper. [R2](https://www.fidelity.com/learning-center/trading-investing/trading/swing-trading)

Proposta: EMA20/50/200, RSI e volume, candle 4h/tendência 1d, duração máxima de
14 dias e labels de 1/7 dias. Stop 4% e take 8% são defaults de teste próprios;
volatilidade pode torná-los inadequados. ATR já disponível ajuda a diagnosticar
essa inadequação; stop ATR e trailing ficam para nova família/versão, evitando
mudar a regra no meio da amostragem. [R7](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr)

Implicação: um mês pode ter poucas operações e memória insuficiente por regime.
Não baixar mínimos nem importar scalping como swing para obter C ativa.

## 4. Day trade

O traço definidor é entrar e sair dentro do período diário escolhido. Como cripto
não tem fechamento diário de bolsa, precisamos fixar uma fronteira operacional.
A agenda UTC proposta é nossa convenção, não obrigação da exchange. [R5](https://www.binance.com/en/academy/articles/a-beginners-guide-to-day-trading-cryptocurrency)

Proposta: 15m/1h, rompimento das oito máximas anteriores com confirmação, posição
máxima de oito horas, cutoff de entrada 23:30 UTC e saída programada 23:55 UTC.
Isso o diferencia do legado, que pode atravessar a virada UTC. O encerramento
vem do relógio/risco e não exige esperar o próximo candle ou pedir autorização ao
JEV. Sem cotação válida fica pendente, sem preço de fechamento inventado.

Não escolhidos agora: reversão em range e VWAP intradiária. Acrescentariam hipóteses
e indicadores/âncoras que não são necessários para validar o primeiro catálogo.
Não confundir o VWAP de um sinal com supor preenchimento real ao preço médio.

## 5. Scalping

As referências associam scalping a movimentos pequenos e repetidos, com execução
rápida e dados atuais. Há métodos de momentum, range e exploração de spread;
eles exigem simulações diferentes. Escolhemos cruzamento/momentum em candles
de 1m com contexto de 5m, sem pretender competir em HFT. [R3](https://www.binance.com/en/academy/articles/what-is-scalping-trading-in-cryptocurrency)

Ganhos pequenos ficam especialmente sensíveis a custos e a uma perda maior.
Taxa de acerto isolada não determina resultado líquido. Não existe evidência
obtida nesta pesquisa para chamar 0,8–1,5% de média pessimista garantida. O take
de 1,20% proposto é cenário-alvo, não média prevista. [R4](https://bts.ig.com/en/trading-opportunities/beginners-guide-to-scalping-41249-171220)

Proposta: EMA9/21/50, RSI/volume, stop 0,35%, duração máxima 15min, quote <=2s e
prazo ponta a ponta <=8s. São hipóteses que podem reprovar por custo ou latência.
Uma consulta IA por candle de 1m seria incompatível com 240 chamadas/dia: usar
admissão local, checkpoints e teto persistido de ciclos, reportando oportunidades
descartadas. Não afirmar que o protocolo representa todos os scalps do mercado.

O cálculo aproximado de taxa+slippage atual é 0,30% por ida e volta, antes do
spread/quantização. Sobre um alvo bruto de 0,8%, isso deixaria cerca de 0,5% antes
dos demais efeitos, **somente no cenário vencedor**. A validação de perfil deve
usar a prévia exata do broker e também perdas, não essa subtração aproximada.

## 6. Indicadores, dados e validade

RSI mede momentum; extremos não determinam automaticamente reversão, pois podem
persistir numa tendência. Usar o indicador com contexto e thresholds versionados,
sem tratá-lo como probabilidade de alta. [R6](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI)

Bandas relativas à média/volatilidade oferecem outra família, não um substituto
automático para a regra de tendência. Sua inclusão não é necessária ao primeiro
catálogo; permanece referência para perfis posteriores. [R8](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands)

A API pública suporta os intervalos propostos. Usar candles UTC fechados; o
stream pode publicar atualizações periódicas e não equivale a uma decisão de
milissegundos. Melhor bid/ask é outra fonte de evento; não inferir liquidez em
profundidade ou ordem executada só pelo ticker. [R10](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md)

Warmup precisa cobrir o maior indicador em **cada** intervalo. Para 600 candles
diários são necessários aproximadamente 600 dias do ativo; se faltarem, não
inventar histórico nem iniciar com EMA200 inválida. REST permite paginação
limitada e verificação de sequência; não usar candles abertos no aquecimento.
Novos tokens podem ser inelegíveis para um preset sem ajustar o template antes
de outra sessão. [R11](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md)

## 7. Como avaliar sem fabricar vantagem

Testes unitários/replays identificados comprovam fórmulas, transições e falha
segura. Quando só houver OHLC histórico, qualquer fill sintético deve ser
declarado; não reconstruir bids que não observamos nem inserir essas amostras no
catálogo real. A prova operacional vem de paper com cotações públicas observadas.

Escolher o melhor preset depois de testar muitas combinações no mesmo intervalo
pode selecionar ruído. Registrar tentativas e separar ajustes do período futuro
de avaliação. A POC não precisa implementar o método estatístico completo dos
autores para adotar essa disciplina. [R12](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)

Classificar notícias ajuda o contexto, mas não elimina custo, latência ou risco de
execução. B−A avalia o pacote enriquecido; C−B avalia memória quando utilizável.
Comparar estilos distintos não isola efeito do JEV. Novas moedas permanecem
sujeitas a metadados públicos, tamanho mínimo, qualidade e origem do aprendizado.
