# Dataset de aprendizado para novas execuções

**Escopo vigente D051/D052/SPEC 1.50:** [plano ordenado](PLANO_DESENVOLVIMENTO_V1.md) e [status](STATUS_DESENVOLVIMENTO.md). Catálogo inicial trend_15m_v1, TUI remota REST/WSS com token/2FA e transferência automática separada na V1; outros estilos são evolução. Notas antigas de pendências são históricas. Implementação/validação pendentes.

**D030 — suporte a outros ativos na V1:** um par Spot configurável com cotação USDT por sessão, selecionado antes de iniciar; BTC é exemplo/default. Banco, trio A/B/C e memória por símbolo permanecem separados. Quantidades, metadados, feeds, prompts e contexto usam o ativo destino. Retomada mantém o par salvo; transferência estatística separada integra a V1 conforme D052/SPEC 10.10. [Contrato vigente, seção 4.3](SPEC.md). Implementação pendente.

**Estado em 11/10/2026:** importação/exportação e evolução acumulativa aprovadas em P013/[D007](DECISIONS.md), implementação pendente. D007 permite associação explícita de amostras compatíveis a novas execuções, preservando a origem. P014/[D008](DECISIONS.md) aprova memória específica por ativo e avaliação separada de padrões compartilháveis; o pedido posterior D052 inclui a implementação na V1, com método/gates em [TRANSFERENCIA_APRENDIZADO.md](TRANSFERENCIA_APRENDIZADO.md). Validação real permanece pendente.

## Finalidade

Guardar observações históricas auditáveis para o Learning Engine local de C iniciar uma nova execução com amostras elegíveis. O arquivo funciona como uma base inicial de memória estatística; os pesos do JEV permanecem iguais. Reiniciar o processo na mesma execução já deve conservar memória, carteiras e histórico no SQLite, sem depender deste arquivo.

Uma nova execução mantém três carteiras independentes de 100 USDT e não importa saldos, posições, fills ou travas anteriores. Importar memória pode antecipar sua disponibilidade quando houver amostras compatíveis suficientes para o contexto atual; não garante cobertura dos regimes nem melhor desempenho.

## Modos de início confirmados pelo usuário

**Aprovação explícita em 11/10/2026, reafirmando D007/P013:**

- **Sessão nova com dataset:** selecionar/validar a base antes da primeira decisão e persistir a importação. C utiliza somente amostras elegíveis, com origem, cutoff e mínimos preservados.
- **Sessão nova sem dataset:** manter `learning.initial_dataset_path: null`, sem histórico inicial. C acumula observações locais e usa memória quando houver evidência suficiente; B/C compartilham inferência somente nas condições da SPEC.
- **Restauração da sessão existente:** recuperar memória e demais estados do SQLite, sem exigir dataset externo nem reler um arquivo alterado.

Importação inicial é opcional; B permanece sem memória e A/B/C iniciam com 100 USDT virtuais em uma sessão nova. Origem/deduplicação entre carteiras foi aprovada posteriormente em P008/D014, conforme a seção abaixo. O requisito será refletido na configuração antes da partida; telas e controles TUI continuam para P007.

## Arquivo versionado

Usar arquivos UTF-8 JSONL, por exemplo `learning-dataset-r001.jsonl` e `learning-dataset-r002.jsonl`: primeira linha com metadados, demais linhas com observações amadurecidas. Revisão do acervo e versão do schema são campos distintos. Exportar do SQLite com leitura consistente e publicação por arquivo temporário seguido de rename, sem sobrescrever a versão anterior. Não há observações reais neste repositório para gerá-los agora.

| Registro | Conteúdo proposto |
| --- | --- |
| Metadados | `dataset_id`, revisão, versão de schema, datasets predecessores e hashes, criação/cutoff de exportação, origem, quantidade de amostras, composição por ativo/regime/período e hash SHA-256 dos registros de amostras em sua representação exportada. |
| Proveniência | ID estável da observação, execução/carteira/decisão de origem, versões de código, template da estratégia, alterações/configuração efetiva e hash (D013), features, labels e política de amostragem. Preservar a origem também ao reexportar dados importados. |
| Contexto original | Símbolo, perfil/intervalo, estado da posição, família do label, horizonte e features/buckets disponíveis naquele momento. |
| Tempo | `decision_at`, `as_of`, disponibilidade original dos dados, maturação prevista, observação/disponibilidade do bid de saída e `matured_at` efetivo. |
| Resultado | Retorno líquido, preços de referência e saída com fonte/horários, comissões, slippage e status avaliado. Valores financeiros em strings decimais. |

Exportar resultados válidos positivos, negativos e neutros de A/B/C, incluindo estados elegíveis com HOLD conforme D014. Não selecionar apenas trades vencedores ou executados. `UNAVAILABLE`, pendentes, dados inválidos e fixtures ficam fora das amostras reais reutilizáveis; contagens e motivos de exclusão acompanham a auditoria. Não incluir segredos ou artigos integrais; notícias/Polymarket não são dimensões da memória V1.

## Origem e equivalência aprovadas (P008/D014)

C usa labels contrafactuais válidos e amadurecidos de A/B/C, contando avaliações equivalentes uma vez. Preservar contexto/features, instante/candle, símbolo/perfil/protocolo, posição, família/horizonte, cotações/horários, custos e versões; incluir quantidade/orçamento se afetarem o cálculo. Mesmo candle ou retorno isolado não bastam para unir exemplos. Não selecionar representante pelo melhor resultado.

Cada exemplo único conserva identidade estável e todos os vínculos originais de execução/carteira/decisão, com maturação/disponibilidade por origem. Exportar/importar esses vínculos, inclusive quando outra origem equivalente aparecer numa revisão posterior, sem apagar as anteriores ou multiplicar a contagem. Filtrar elegibilidade temporal de cada origem antes de deduplicar para a consulta. Decisões e avaliações individuais permanecem na auditoria; saldos, fills e ledger não são fundidos.

Mínimos 30/50 e estatísticas usam exemplos únicos elegíveis. Avaliações distintas de candles consecutivos ainda podem compartilhar parte do mesmo horizonte futuro. O usuário pediu guardar essa dependência em P008 para discussão posterior; deduplicação não comprova independência. Preservar tempos/origens e distinguir contagens de avaliações de origem das de exemplos únicos. Tratamento de amostragem e incerteza continua pendente, sem escolher espaçamento, pesos ou novos mínimos.

## Acervo histórico e memória ativa

O acervo guarda a união deduplicada dos dados importados válidos e dos novos resultados locais amadurecidos. Conservar identidade e origem original ao reexportar; um exemplo reimportado ou presente em dois arquivos não vira dois exemplos. Cada nova versão registra seus predecessores para rastrear a evolução.

Guardar amostras antigas válidas no acervo, mesmo depois de saírem da janela operacional. A memória ativa de C usa somente o subconjunto compatível com a execução, símbolo e contexto, dentro dos 60 dias contratados e com maturação/disponibilidade anteriores à decisão. Arquivo crescer por vários meses não aumenta implicitamente essa janela. Informar separadamente amostras arquivadas, elegíveis, inativas por idade/ativo/protocolo e rejeitadas por invalidade.

D030 permite este fluxo com outra moeda em uma nova sessão na V1, mantendo memória específica por símbolo:

| Etapa | Acervo exportado | Uso operacional |
| --- | --- | --- |
| Mês 1, BTC | Revisão 1 com observações BTC amadurecidas. | C acumula memória BTC quando os mínimos permitirem. |
| Mês 2, outra moeda em nova sessão | Revisão 2 preserva BTC e acrescenta resultados do novo ativo. | Observações BTC ficam arquivadas/inativas na memória do novo ativo; resultados locais alimentam sua memória específica. Camada estrangeira separada pode ser validada/ativada conforme D052; não entra nas contagens locais. |
| Sessões posteriores | Novas revisões acrescentam observações sem duplicar antecessores. | Consultar memória elegível por ativo/contexto; avaliar qualidade em dados posteriores. |

## Importação aprovada

1. Selecionar explicitamente o dataset antes da primeira decisão da nova execução. Sem seleção, manter a inicialização sem memória anterior. Não adicionar importações durante o período de avaliação nem alterar silenciosamente o arquivo já selecionado.
2. Validar schema, integridade e proveniência. Para uso na memória ativa, validar compatibilidade de símbolo, perfil/intervalo, famílias, horizontes, features/buckets, custos e política de cotações/amostragem. Guardar hashes originais, mas comparar componentes relevantes: `run_id` diferente não deve sozinho rejeitar a importação. Registros válidos de outro ativo ou protocolo permanecem arquivados/inativos, sem entrar nas estatísticas da execução; transferi-los exige a política de P014.
3. Fixar a base inicial com resultados conhecidos antes do começo da execução. Na consulta, aplicar janela móvel de 60 dias e `matured_at < learning_cutoff_at`, além da disponibilidade no destino antes da decisão. Registrar horário da importação; nunca usá-la para alterar decisões anteriores. Dados antigos válidos permanecem no acervo, sem completar os mínimos da memória ativa.
4. Preservar `origin_run_id`, identidade original e todos os vínculos de proveniência. Associar as amostras aceitas à execução destino por vínculo de importação, sem reescrever sua origem. Deduplicar importações repetidas, datasets sobrepostos e reexportações conforme D014, conservando origens equivalentes sem multiplicar exemplos. Quantidade de exemplos únicos não comprova independência estatística; a dependência entre candles consecutivos continua em P008.
5. Recalcular as estatísticas no Learning Engine. Preservar mínimos 30/50, famílias/horizontes separados e máximo de três padrões no contexto. Amostras importadas expiram com a janela; a memória continua incorporando resultados locais amadurecidos pela política fixa da execução.
6. Persistir importação, hash, versões, contagens aceitas/elegíveis/inativas/rejeitadas e razões no SQLite, com ativação transacional e retomada idempotente. Não expor importação parcial, carregar o arquivo inteiro em cada inferência ou depender dele depois de importado para reconstruir o estado aceito.

## Desenho aprovado de transferência e detalhes pendentes (P014/D008)

O usuário aprovou preservar memória específica por ativo e avaliar separadamente uma camada de padrões compartilháveis, mantendo origem identificada. Guardar moedas no mesmo arquivo com partições por símbolo não prova validade de seus padrões no ativo destino. Prioridade/peso, normalização, mínimos e critérios de ativação da camada compartilhada ainda precisam de contrato e avaliação; não transformá-la em fallback operacional da hierarquia atual antes disso.

Retornos percentuais, RSI, ATR percentual e volume relativo são candidatos a representação comparável; não importar valores absolutos de preço ou volume como se fossem equivalentes. Normalizar não prova que a relação com o resultado se mantém. Buckets de volatilidade relativos ao histórico de cada moeda também precisam de interpretação compatível. Até concluir os critérios técnicos/ativação de transferência de P014, preservar símbolo nos grupos e manter dados de outro ativo fora da memória operacional. D008 não altera a janela de 60 dias, mínimos 30/50, máximo de três padrões; D030 amplia ativos executáveis sem autorizar mistura de estatísticas.

Transferência de dados pouco relacionados pode piorar o resultado em uma tarefa destino, fenômeno estudado como transferência negativa. A referência geral não demonstra que isso ocorrerá neste bot nem valida um método entre criptoativos. [Wang et al., Characterizing and Avoiding Negative Transfer](https://arxiv.org/abs/1811.09751).

## Equilíbrio e avaliação

Avaliar cobertura por ativo, regime, período, família/horizonte e qualidade, sem definir equilíbrio como metade ganhos/metade perdas. Não duplicar exemplos raros nem apagar negativos para melhorar métricas; políticas de seleção/peso futuras precisam de versão, decisão própria e validação fora do período usado para escolhê-las. Preservar também dados fora da seleção em seu acervo auditável.

Uma revisão maior pode aumentar cobertura, mas não é automaticamente mais precisa. Testar versões congeladas em períodos posteriores, com critérios de comparação fixados antes da avaliação. Separar diferenças entre mês/regime e moeda: observar BTC num mês e outro ativo no seguinte não isola o efeito de trocar moeda. Se no futuro houver teste retrospectivo, ele deverá reproduzir disponibilidade temporal, maturação e estado de memória; importar hoje um arquivo antigo não autoriza backtest ou trades retroativos pela CLI ao vivo.

A avaliação temporal deve usar passado para construir a memória e dados posteriores para avaliá-la, evitando a mistura de futuro e passado explicada na [documentação de TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). A referência orienta o desenho; não acrescenta scikit-learn ou outro modelo à V1. Validar também os horizontes sobrepostos conforme P008.

## Efeito na comparação e na operação

B continua sem feedback histórico. Em execuções com dataset, C−B mede a contribuição da memória inicial mais a memória acumulada durante a execução. Identificar esse tratamento no relatório, dataset de origem, amostras iniciais e data de ativação. Não apresentar esse resultado como prova exclusiva de aprendizado produzido naquela sessão. Separar avaliações que iniciam sem memória das que iniciam com memória importada.

Exportação, validação e estatísticas são processamento local; não exigem novas inferências para cada amostra. O contexto enviado ao JEV permanece limitado aos padrões relevantes. C pode passar a exigir chamada própria desde o início se a memória já estiver disponível; nesse caso há menos compartilhamento B/C e o consumo físico pode aumentar. Os limites globais de chamadas/custo permanecem.

A capacidade acrescenta desenvolvimento de schema versionado, compatibilidade, importação, deduplicação, migração e auditoria; não exige um modelo adicional, banco vetorial ou treinamento do JEV. D007 integra a capacidade ao Marco 4, respeitando a ordem da SPEC. Validar duplicidade, arquivos incompatíveis/corrompidos, dados futuros/vencidos, restart da importação, conservação do acervo e isolamento de B e dos saldos.

Na futura TUI, indicar memória inicial, dataset/revisão/hash, origem/período e amostras arquivadas/elegíveis/inativas/rejeitadas, distinguindo importadas de locais e os ativos. A fase da TUI continua em P007. Importação/exportação estão aprovadas em D007; D008 aprova o desenho de memória específica e avaliação de padrões compartilháveis. Transferência automática integra a entrega V1 conforme D052/10.10 e [contrato](TRANSFERENCIA_APRENDIZADO.md). Implementação/validação pendentes; não mostrar recurso como operacional antes de implementado.

## Comandos contratados, ainda não implementados

```bash
python -m poc import-learning --config config/default.yaml --run-id RUN_ID --input data/datasets/learning-dataset-r001.jsonl
python -m poc export-learning --config config/default.yaml --run-id RUN_ID --output data/datasets/learning-dataset-r002.jsonl
```

`learning.initial_dataset_path` também pode selecionar a base inicial no YAML, com default `null`; fixar identidade/hash na execução e reconhecer importação prévia sem duplicá-la. Importar após a primeira decisão é rejeitado. Exportar nunca sobrescreve uma versão anterior. Os comandos não consultam JEV, alteram carteira ou executam trades.

## Catálogo automático separado da importação inicial

A base local selecionada continua fixa na sessão. Dados amadurecidos publicados por outras sessões no catálogo alimentam somente a camada transferida, com disponibilidade real, protocolo/origem e validação no destino. Esse fluxo não reimporta arquivos na base local nem altera capital. Exportar conserva origem e observações; não transportar aprovação ACTIVE para outra moeda/sessão. Ver D052 e SPEC 10.10.
