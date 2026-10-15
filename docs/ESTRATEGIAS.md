# Estilos e estratégias para a execução da POC

**Atualização D056/SPEC 1.54 — 14/10/2026:** pesquisa aprofundada e plano de cadastro/templates de swing, scalping e day trade em [PESQUISA_PERFIS_ESTRATEGIA.md](PESQUISA_PERFIS_ESTRATEGIA.md) e [PLANO_PERFIS_ESTRATEGIA.md](PLANO_PERFIS_ESTRATEGIA.md). Hold fica para depois. O código atual executa somente trend_15m_v1; os novos presets são propostas ainda não implementadas. O texto abaixo conserva a pesquisa inicial de 11/10; transferência já integra V1 por D052 e não está mais excluída.

**D030 — suporte a outros ativos na V1:** um par Spot configurável com cotação USDT por sessão, selecionado antes de iniciar; BTC é exemplo/default. Banco, trio A/B/C e memória por símbolo permanecem separados. Quantidades, metadados, feeds, prompts e contexto usam o ativo destino. Retomada mantém o par salvo; transferência estatística entre moedas continua em P014. [Contrato vigente, seção 4.3](SPEC.md). Implementação pendente.

Pesquisa consultada em **11/10/2026** para definir o comportamento do serviço de paper trading. Os estilos abaixo são referências para discussão. Somente as regras já descritas na [SPEC](SPEC.md) constituem o contrato vigente.

[D009/D010](DECISIONS.md) exigem escolher o perfil antes de criar sessão e preparar dois perfis após homologação do usuário, cada sessão com banco e trio A/B/C próprios. O contrato de seleção está em [PERFIS_E_SESSOES.md](PERFIS_E_SESSOES.md); quais estilos/regras serão habilitados continua em P006. A pesquisa não escolhe os dois perfis nem aprova novos thresholds.

## Três dimensões da estratégia

| Dimensão | O que define | Exemplos |
| --- | --- | --- |
| Estilo de operação | Duração pretendida e frequência de atuação | Scalping, day trade, swing, position, buy and hold. |
| Família de sinais | Hipótese que orienta entradas e saídas | Tendência, momentum, rompimento, reversão à média. |
| Variante experimental | Método de decisão comparado | A técnica, B JEV sem memória, C JEV com memória. |

Uma estratégia operacional também precisa definir entradas, saídas, tamanho da posição e gestão de risco. O nome do estilo sozinho não determina essas regras. [Binance Academy — estratégias de criptomoedas](https://www.binance.com/en/academy/articles/a-beginners-guide-to-cryptocurrency-trading-strategies).

Para a POC, comparar A/B/C dentro do mesmo perfil mantém a duração, os custos e as oportunidades de execução comparáveis. Dar scalping a A, swing a B e buy and hold a C misturaria o efeito do estilo com o efeito da memória. Essa é uma implicação do desenho experimental do projeto.

## Estilos pesquisados

| Estilo | Característica temporal | Consequência para o bot proposta nesta pesquisa |
| --- | --- | --- |
| Scalping | Operações muito curtas, buscando movimentos pequenos e frequentes. | Exige avaliar latência, resolução das cotações e custos antes de definir um perfil. |
| Day trade | Entrada e saída dentro de um dia ou sessão. | Precisa definir o significado de sessão em mercado cripto e a política de encerramento. |
| Swing trading | Posições por dias a semanas. | Requer maior tempo de posição, outros horizontes de labels e aquecimento coerente. |
| Position trading | Posições por semanas ou meses, seguindo movimentos mais longos. | Exige observação longa e contexto de mercado compatível. |
| Buy and hold | Compra e manutenção por um horizonte longo. | Requer regras próprias de entrada e encerramento; pode ser estudado como referência adicional. |

As definições de scalping e day trade estão nos guias de [scalping](https://www.binance.com/en/academy/articles/what-is-scalping-trading-in-cryptocurrency) e [day trading](https://www.binance.com/en/academy/articles/a-beginners-guide-to-day-trading-cryptocurrency). Os horizontes de swing estão no guia de [swing trading](https://www.binance.com/en/academy/articles/a-beginners-guide-to-swing-trading-cryptocurrency); position e buy and hold estão no [panorama de estratégias](https://www.binance.com/en/academy/articles/a-beginners-guide-to-cryptocurrency-trading-strategies).

As faixas temporais são descrições gerais. Intervalo de candle e tempo em posição são grandezas distintas: olhar um gráfico de 15m não define, por si só, a duração de um trade.

### Scalping

As margens pequenas tornam execução e taxas especialmente relevantes. A fonte destaca decisões rápidas, dados em tempo real e o impacto de comissões quando há muitas operações. [Binance Academy — scalping](https://www.binance.com/en/academy/articles/what-is-scalping-trading-in-cryptocurrency).

**Implicação para a POC:** polling de 10s, decisão em candle de 15m, timeout de IA de 20s e tolerância de atraso de 90s não demonstram capacidade de capturar oportunidades de segundos. Um perfil de scalping dependeria de outro contrato temporal e de evidências de latência. Diminuir o candle no YAML não basta.

### Day trade

Em cripto, a negociação contínua exige explicitar o que conta como dia operacional. [Binance Academy — day trading](https://www.binance.com/en/academy/articles/a-beginners-guide-to-day-trading-cryptocurrency).

**Implicação para a POC:** escolher entre uma sessão com horário de encerramento e uma duração máxima contada da entrada. A SPEC usa UTC para limites diários, mas não determina uma liquidação obrigatória à meia-noite. Essa questão permanece aberta.

### Swing e position

Swing trabalha com movimentos de vários dias e costuma consultar gráficos de 4h e diários. [Binance Academy — swing trading](https://www.binance.com/en/academy/articles/a-beginners-guide-to-swing-trading-cryptocurrency).

**Implicação para a POC:** reduzir a frequência de inferência não elimina o monitoramento de risco. Horizonte de memória, limite de posição, janela de notícias e período de observação devem acompanhar o perfil. O limite vigente de 16 candles de 15m corresponde nominalmente a 4h, portanto não expressa uma política de posição por vários dias.

### Buy and hold e a ação HOLD

Buy and hold mantém o ativo por um horizonte longo. DCA, outro conceito, distribui compras em intervalos regulares. [Binance Academy — estratégias de criptomoedas](https://www.binance.com/en/academy/articles/a-beginners-guide-to-cryptocurrency-trading-strategies).

Na POC, `HOLD` significa apenas **não alterar a carteira naquele ciclo**: pode ocorrer sem posição ou com posição no ativo base. Não equivale a buy and hold. DCA exigiria compras adicionais, incompatíveis com a regra vigente de rejeitar `BUY` quando já existe posição. Nenhum desses perfis está habilitado pela pesquisa.

## Famílias de sinais

| Família | Hipótese de operação | Relação com a V1 |
| --- | --- | --- |
| Tendência | Buscar continuidade de um movimento direcional. | A já exige alinhamento de EMAs e tendência de 1h; manter as condições exatas da SPEC. |
| Momentum | Usar direção e força recente da variação de preço. | MACD e RSI já fazem parte do contexto; uma política nova exigiria regras versionadas. |
| Rompimento | Buscar continuação depois que o preço supera uma zona relevante. | Candidata; ainda faltam definição objetiva da zona, confirmação e invalidação. |
| Reversão à média ou range | Buscar retorno de um desvio a uma referência ou oscilação dentro de uma faixa. | Candidata; exige definir referência, regime, confirmação e saída. |

Momentum descreve a velocidade da variação de preços e pode ser usado com outros indicadores. [Fidelity — Momentum](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/momentum).

Suportes e resistências são zonas que podem produzir reação ou rompimento; falsos rompimentos continuam possíveis. [Binance Academy — suporte e resistência](https://www.binance.com/en/academy/articles/the-basics-of-support-and-resistance-explained).

Bandas de Bollinger descrevem níveis relativos à média e à volatilidade; o preço pode permanecer próximo ou além de uma banda em tendências fortes. Tocar uma banda não basta para afirmar reversão. [Fidelity — Bollinger Bands](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands).

As famílias são referências conceituais, sem promessa de desempenho nos ativos configurados. Thresholds, indicadores adicionais e algoritmos candidatos não passam a integrar a V1 por constarem nesta pesquisa.

## Enquadramento do perfil vigente

**Interpretação técnica:** o contrato atual se aproxima de operação de curto prazo orientada a tendência, com cadência de 15m. Ainda falta definir se receberá formalmente o nome day trade e se terá encerramento por sessão.

| Parâmetro vigente | Valor |
| --- | --- |
| Mercado e capital | Um par Spot USDT configurável por sessão, long-only; 100 USDT por carteira. |
| Decisão e tendência | Candles fechados de 15m e 1h. |
| Monitoramento de cotação | Polling nominal de 10s; quote com idade máxima de 30s. |
| Duração máxima | 16 candles, nominalmente 4h no intervalo atual. |
| Risco | Uma posição; alocação máxima de 20% do patrimônio, limitada ao caixa. |
| Proteções | Stop de 1,5%, take de 3%, trava diária de 5%. |
| Custos simulados | Taxa de 0,10% e slippage de 0,05%, por lado. |
| Aprendizado | Labels de 4 e 16 candles; janela de até 60 dias. |

Fonte dos valores: [SPEC, seções 4, 7, 9 e 10](SPEC.md). São hipóteses do experimento.

**Cálculos derivados da configuração:** taxas e slippage somam aproximadamente 0,30% em uma compra seguida de venda, antes do spread e da quantização. Isso representa cerca de 0,06 USDT sobre 20 USDT de exposição. A contabilidade efetiva deve seguir as fórmulas do broker, sem substituir os cálculos exatos por essa aproximação.

Um dia completo contém 96 intervalos de 15m. B/C usariam nominalmente 96 chamadas físicas compartilhadas ou 192 separadas, antes de retries e chamadas de diagnóstico. Em 1m seriam 1.440 ou 2.880, acima do limite vigente de 240 chamadas/dia. Frequência de sinal e orçamento de IA precisam ser definidos conjuntamente.

## Critérios para definir outro perfil

Antes de habilitar um perfil, definir sua hipótese, família de sinais, dados exigidos, cadência de decisão, duração máxima, sessão, orçamento de IA, custos, proteções e horizontes de aprendizado. Comparar a latência observada com a validade temporal do sinal e reservar chamadas para falhas transitórias.

Cada perfil deve produzir evidências próprias de integridade, amostragem e desempenho. Horizontes de 4/16 candles não devem ser herdados automaticamente: 4 candles de 1m e 4 candles de 4h avaliam eventos diferentes.

As decisões de escopo estão guardadas em [PONTOS_A_ESCLARECER.md](PONTOS_A_ESCLARECER.md). Esta pesquisa inicial não habilita estilos; D056 posteriormente selecionou swing/scalping/day trade para o plano de implementação, com contratos propostos e hold adiado.
