# Análise das decisões HOLD — ETHUSDT, 14/10/2026

**Sessão:** `eth-01`, perfil `trend_15m_v1`.  
**Corte dos dados:** 14/10/2026, 13:06:41 de Brasília / 16:06:41 UTC.  
**Fonte:** SQLite canônico, aberto em `mode=ro`, com uma única transação de
leitura. Não foram feitas chamadas às APIs, alterações de configuração ou
reinicializações do motor.

## Resultado inicial

Aguardar foi mais favorável que comprar na maioria dos pontos observados,
considerando a venda hipotética em um prazo fixo e os custos da simulação.
Houve recuperações lucrativas de curto prazo que o bot deixou passar. Isso
sustenta a prudência do HOLD nessa amostra, sem demonstrar vantagem do JEV
sobre a estratégia técnica ou comprovar que os critérios são os melhores.

Considerando **apenas ciclos em que o JEV efetivamente escolheu HOLD**:

| Horizonte após a decisão | Ciclos com resultado válido | Compra hipotética negativa / HOLD favorecido | Compra hipotética positiva | Retorno líquido médio da compra hipotética |
|---|---:|---:|---:|---:|
| 1h — 4 candles | 24 | 19 (79,2%) | 5 | −0,7864% |
| 4h — 16 candles | 7 | 7 (100%) | 0 | −3,1042% |

Os percentuais de retorno incidem sobre o valor hipoteticamente aplicado,
não sobre os 100 USDT de cada carteira. As duas linhas possuem conjuntos de
decisões diferentes; os resultados de 4h disponíveis são todos do dia 14.
São frequências descritivas do histórico, não taxas de acerto validadas.

## O que foi contado

O histórico contém 55 ciclos concluídos e 165 decisões, todas HOLD, de
13/10 às 12:30 até 14/10 às 13:00, em horário de Brasília. Não houve fills.
A/B/C permanecem sem resultado de negociação realizado; os retornos deste
relatório são contrafactuais, não lucro ou prejuízo efetivo das carteiras.

Em B e C, por carteira, existem:

- 32 decisões com motivo `JEV_CHOICE`;
- 20 decisões `AI_CIRCUIT_OPEN`;
- 3 decisões `AI_CONTEXT_TOO_LARGE`.

As últimas duas categorias são bloqueios históricos de integração, não
escolhas de mercado do JEV. Foram excluídas da avaliação principal acima.
Suas ocorrências históricas não indicam, por si, falhas ainda ativas.

Os resultados de A/B/C coincidem para cada ciclo/horizonte observado. Foram
contados uma vez, verificando a igualdade dos retornos e dos `sample_id`.
As 204 linhas amadurecidas por carteira correspondem a **68 combinações
únicas de ciclo/horizonte**, e não a 204 observações independentes.

Na visão completa do histórico, incluindo bloqueios técnicos:

| Horizonte | Resultado amadurecido | Indisponível por ausência de cotação válida | Ainda pendente |
|---|---:|---:|---:|
| 1h | 45 ciclos | 6 ciclos | 4 ciclos |
| 4h | 23 ciclos | 16 ciclos | 16 ciclos |

Entre os 45 resultados de 1h, 38 compras hipotéticas seriam negativas;
entre os 23 resultados de 4h, 22 seriam negativas. Esses números não devem
ser apresentados como desempenho de decisões do JEV, porque misturam
escolhas com bloqueios de integração.

## Mesmas decisões nos dois horizontes

Para comparar os horizontes sem mudar o conjunto, existem sete ciclos de
HOLD escolhido pelo JEV com ambos os resultados válidos:

| Horizonte | HOLD favorecido | Compra hipotética positiva | Retorno líquido médio da compra hipotética |
|---|---:|---:|---:|
| 1h | 4 de 7 | 3 de 7 | −0,3577% |
| 4h | 7 de 7 | 0 de 7 | −3,1042% |

Nesses sete casos, algumas recuperações em 1h não persistiram até 4h.
A diferença entre os horizontes mostra por que o resultado precisa ser
avaliado conforme o prazo definido, sem escolher retrospectivamente o melhor.

## Recuperações de curto prazo não capturadas

Cinco decisões de HOLD escolhido pelo JEV tiveram compra hipotética positiva
ao completar 1h. Todos os horários abaixo são de **14/10, em Brasília**:

| Decisão | Venda de referência após 1h | Retorno líquido hipotético | Resultado hipotético com a quantidade permitida pela alocação de até 20 USDT |
|---|---|---:|---:|
| 07:15 | 08:15 | +0,0267% | +0,0053 USDT |
| 08:15 | 09:15 | +0,2291% | +0,0454 USDT |
| 08:30 | 09:30 | +0,4362% | +0,0863 USDT |
| 11:30 | 12:30 | +0,0251% | +0,0050 USDT |
| 11:45 | 12:45 | +0,3002% | +0,0597 USDT |

São pontos de avaliação positivos após custos, não operações reconstruídas
ou entradas comprovadamente aprováveis por todos os filtros do bot. Não
somar esses resultados: as posições hipotéticas se sobrepõem e o perfil
permite apenas uma posição por carteira.

## A decisão específica que motivou a análise

O ciclo das **13:00 de Brasília / 16:00 UTC**, citado na conversa, ainda não
tem resultado amadurecido no corte deste relatório:

- resultado de 1h previsto para 14:00 de Brasília / 17:00 UTC;
- resultado de 4h previsto para 17:00 de Brasília / 20:00 UTC.

Os dois registros estão `PENDING`. O motor já registra e amadurece esses
resultados automaticamente. A análise não antecipa o resultado nem promete
uma atualização automática deste documento.

## Método e verificações

Foi usado o contrato atual do Learning Engine, `ENTRY_LONG_NET_RETURN`:

```text
retorno líquido (%) = 100 × [
  bid_do_horizonte × (1 − slippage) × (1 − taxa)
  / (ask_de_entrada × (1 + slippage) × (1 + taxa)) − 1
]
```

Taxa: **0,10% por lado**. Slippage: **0,05% por lado**. O spread é incorporado
pelos preços ask de entrada e bid de saída, sem adicioná-lo novamente.
O cálculo monetário usa a quantidade arredondada registrada na referência
de cada observação; o restante da alocação não é tratado como aplicado.
Custos de inferência JEV não entram nesse retorno de negociação.

Os 204 retornos persistidos foram recalculados com `Decimal` e conferidos
com tolerância absoluta inferior a `1e-20` ponto percentual. Também foram
verificados: referência de entrada observada depois da decisão, maturação
anterior ao corte, cotação de saída observada nos 90s após o horizonte e
recebida até a avaliação, ausência de fixtures e deduplicação A/B/C.

## Limitações e interpretação

- O cálculo vende no horizonte fixo; não simula a trajetória com stop de
  1,5%, take profit de 3%, saídas intermediárias ou reentrada. Uma perda
  hipotética de 3,10% ao final de 4h não é uma perda que o bot necessariamente
  teria sofrido operando com seu stop. Não há garantia de execução no stop.
- Janelas consecutivas se sobrepõem e vários casos pertencem ao mesmo
  movimento de mercado. Não se assume independência nem significância.
- Há lacunas e mudanças de integração no histórico. Entre 13/10 às 20:45 e
  14/10 às 07:15 de Brasília há aproximadamente 10h30 entre ciclos. Ausência
  de cotação no prazo permanece indisponível; não houve preenchimento por
  candles históricos ou preços posteriores.
- A também aguardou nos 55 ciclos. Portanto, a amostra ainda não distingue
  vantagem do JEV sobre A. Nos 32 ciclos de escolha JEV, a memória de C
  estava `insufficient_samples`, impedindo avaliar vantagem de C sobre B.
- Os 32 ciclos com escolha JEV têm 22 estados `bearish` e 10 `range`, sem
  estados `bullish`. Uma amostra de HOLD em mercado desfavorável não basta para
  avaliar a capacidade de entrar e sair durante oportunidades de alta.

Manter os critérios durante a observação evita ajustá-los apenas aos
resultados já conhecidos. A próxima comparação deve incluir os resultados
pendentes, novas condições de mercado e entradas efetivas, quando ocorrerem.

## Artefatos

Diretório congelado desta análise:
`data/analysis/eth-hold-20261014T160641Z/`.

- [Resumo estruturado e validações](../../data/analysis/eth-hold-20261014T160641Z/summary.json).
- [CSV deduplicado por ciclo/horizonte](../../data/analysis/eth-hold-20261014T160641Z/matured_unique_cycle_horizons.csv).
- [CSV com todas as origens A/B/C](../../data/analysis/eth-hold-20261014T160641Z/matured_by_wallet.csv).
- [Hashes SHA-256 dos artefatos](../../data/analysis/eth-hold-20261014T160641Z/sha256.json).

Os CSVs incluem horários UTC e de Brasília, IDs de origem, cotações, retorno
líquido e resultado monetário hipotético. Os dados locais são ignorados pelo
Git; o documento contém os números e as limitações do corte.
