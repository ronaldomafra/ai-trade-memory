# Polymarket na sessão ETH — 13/10/2026

**Atualização 14/10:** a integração descrita abaixo é evidência histórica; o
ensaio de 24h iniciado em 13/10 sofreu suspensão do host e foi interrompido.
Novo ensaio iniciado em 14/10 às 08:28:50 de Brasília, com bloqueio temporário
de suspensão e observador corrigido; consultar o [status](../STATUS_DESENVOLVIMENTO.md).

## Problema e correção

A API estava acessível, mas a descoberta geral por mercados mais novos não
garantia candidatos úteis para a moeda da sessão. As métricas CLOB não tinham
contrato monetário verificado e a associação exigia títulos literalmente iguais,
excluindo também mercados de faixas com regras e período iguais.

A descoberta agora resolve a tag pública da moeda e de juros e consulta páginas
planas de mercados ativos, ordenadas por volume de 24h. As consultas de tags
entram no teto de cinco requisições por revisão; o cache preserva a data original
da coleta. Moeda sem tag específica usa o tema crypto com limitação explícita.
O escopo é registrado: não cobre todos os temas macroeconômicos nem comprova
ausência de mercados fora das páginas consultadas.

O contrato `GAMMA_NUM_DOLLAR_FIELDS_V1` usa `liquidityNum` e `volume24hr`.
A [referência oficial de mercados](https://docs.polymarket.com/market-data/market-details)
descreve as métricas; o [CLI oficial](https://github.com/Polymarket/polymarket-cli/blob/main/src/output/markets.rs)
mostra esses campos com formatação monetária e teste de escala. Trata-se de
totais reportados em USD nominal, separados da profundidade observada no livro.
Não se infere escala a partir de nomes de campos CLOB nem se presume cotação
cambial de stablecoin. Campos ausentes ou versão incompatível seguem UNVERIFIED.

Mercados acima/abaixo de faixas só compartilham ocorrência quando as regras
completas, ativo explícito, objeto/período do título e prazo de resolução
correspondem. Apenas o preço da faixa é normalizado; datas, anos e horários
continuam na comparação. ID do evento sozinho não verifica associação.
Grupos ambíguos continuam pendentes; agrupamento não demonstra independência.

Foi corrigido também o cutoff da seleção: a disponibilidade é avaliada depois
da resposta da descoberta, preservando `observed_at` de cada registro. O horário
anterior à requisição descartava os registros recém-recebidos. O teste confirma
que esses dados continuam ausentes de snapshots anteriores à disponibilidade.

A validade do fator respeita também o horário original do livro e a expiração
do último negócio. Livro fresco não estende a recência de um negócio antigo;
o teste verifica a retirada do fator assim que esse prazo termina.

Nenhum piso de liquidez, volume, spread, profundidade ou recência foi reduzido.
Configuração da sessão, capital, histórico e orçamento JEV permanecem preservados.
Não há whitelist fixa de mercado ou token; seleção e classificação são reais.

## Evidência antes da implantação

Ensaio isolado com API real e proxy local: cinco requisições, 227 mercados,
29 candidatos aprovados nos filtros de metadados. Na amostra de livros/negócios,
o mercado 5407319, Ethereum acima de US$ 2.400 em 14/10, passou também pelos
filtros quantitativos: spread de 1 pp, profundidade por lado acima de US$ 1.000
e negócio recente. Esse ensaio não renovou datas nem transplantou cache para
a sessão. Elegibilidade é dinâmica e precisa ser confirmada em execução.

## Testes e atualização

230 testes passaram em 28,58s; Ruff e formatação limpos. Cobrem paginação,
contagem física incluindo tags, cache/restart, outras moedas, metadados/unidades,
associação com datas/horários divergentes, latência da descoberta e cutoff.
Um aviso de depreciação é da integração Starlette/httpx dos testes.

Backup online antes da atualização:
`data/backups/eth-01-before-poly-20261013-2222`, auditoria OK. Os bancos do backup
são individualmente consistentes; não se presume atomicidade entre bancos.

Imagem final do motor: `66138fae36c8`; controle: `720e65543765`.
Motor ETH recriado às 22:28 UTC, com o banco original; controle na porta 18080.
Antes da troca: 26 ciclos/78 decisões, três lançamentos iniciais no ledger e
zero fills. Comparação de hashes da retomada e evidência operacional são
registradas no status; novas decisões posteriores não são retroativas.

## Observação de 24 horas

Na primeira verificação, quatro classificações Polymarket responderam HTTP 200 e
três fatores foram selecionados: mercados 5407319, 5407322 e 5432687. Na revisão
final, quatro fatores: 5407308/5407319 e 5432687/5432689, até dois por ocorrência.
Uma classificação nova reutilizou o mesmo orçamento, sem aumentar seus tetos. Notícias
mantiveram quatro fatores. Livros passaram pelos pisos originais; confiança e
impacto indeterminados continuam explícitos. RUNNING, WS conectado, clock
VERIFIED, cotação fresca, auditoria/invariantes OK e zero reinícios automáticos.
Hashes de ledger/fills/decisões/ciclos e configuração preservados na retomada.

Observação iniciada em **13/10/2026 às 22:29:07 UTC**, até **14/10 às 22:29:07 UTC**
(19:29:07 de Brasília), a cada 60s. Processo independente PID 3976866; artefatos
em `data/acceptance/eth-poly-20261013T222907Z`: `observation.json`, `samples.jsonl`,
`validation-at-start.json`, `observer.pid` e `observer.log`. Primeira amostra
sem violações ou degradações. O teste está em andamento, não concluído.
A coleta preparatória em `eth-poly-20261013T222513Z` foi interrompida para a
atualização final e preservada; suas três amostras não constituem aceite de 24h.

Fechamento de 22:30 UTC confirmado: o pedido Decisions incluiu quatro notícias
e quatro fatores Polymarket. Resposta HTTP 200, modelo
`typesafe/jev-1.13-20260917`, custo observado de US$ 0.000417228, compartilhada
por B/C. Ambos retornaram HOLD/JEV_CHOICE, sem negócios simulados nesse ciclo;
A também HOLD. `first-candle.json` guarda IDs, contagens, custo e auditoria.
Payload de 20.589 bytes, dentro do teto. Essa evidência comprova o uso do
contexto na inferência, sem alegar que ele melhora a decisão ou rentabilidade.

O observador lê banco e estado Docker, sem controlar o bot ou fazer inferências.
Além de saúde, auditoria, custos e invariantes, registra cobertura, quantidade
e IDs de fatores externos utilizáveis. Tempo decorrido sozinho não conclui
aceite: amostras degradadas, custos, fontes e invariantes precisam ser revisados.
Transferência ACTIVE e rentabilidade exigem dados futuros; este teste não
comprova vantagem preditiva ou rentabilidade.
