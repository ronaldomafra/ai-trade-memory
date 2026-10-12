# Transferência automática de aprendizado entre moedas — V1

**D052 · SPEC 1.50/10.9–10.10 · 12/10/2026.**
Incluída por solicitação do usuário; implementação/validação pendentes.
Defaults abaixo são escolhas técnicas iniciais do agente, não calibração empírica ou garantia de benefício.
[Plano E07](PLANO_DESENVOLVIMENTO_V1.md) · [Dataset](DATASET_APRENDIZADO.md).

## Separação e fluxo

BTC permanece BTC. Importar BTC para ETH não produz exemplos ETH nem altera mínimos locais 30/50. A/B e carteiras não recebem estado transferido; JEV não altera pesos.

Catálogo/transferência são distintos da importação inicial imutável. Configuração congela habilitação/política na criação; publicação contínua de dados maduros é parte do tratamento experimental transferido.

1. OutcomeEvaluator confirma label válido maduro no SQLite de origem.
2. Outbox/publicador escreve catálogo idempotente com identidade/origens equivalentes e disponibilidade real.
3. Dataset validado pode abastecer catálogo; importação atual não vira disponibilidade histórica.
4. Consulta destino seleciona fontes estrangeiras compatíveis, janela/cutoff e candidatos.
5. Antes do outcome destino, salva previsão sombra/baseline/hash/proveniência.
6. Após maturação, avalia previsão salva; habilita/suspende pelo gate.
7. C recebe complemento validado dentro do limite; locais permanecem separados.

Sem dataset e sem fonte compatível, operar normalmente sem transferência. Não pedir importação a cada novo resultado.

## Compatibilidade e normalização

Chave inclui perfil/algoritmo/configuração semântica/versões de indicadores/features/buckets/label, intervalo, regime, posição, família, horizonte/duração, fees/slippage e política de referência/cotações. Identidade/símbolo/diretório podem diferir; diferenças materiais não são ignoradas. Validar filtros/arredondamento que afetem o label.

Features comparáveis: RSI, razões preço/EMA, ATR%, volume relativo e retorno líquido percentual; calculadas só com dados disponíveis na origem. Preço/quantidade/volume monetário absolutos não são comparáveis por troca de ticker. Mesmos buckets versionados, sem normalização ajustada com futuro.

Conservar origem/símbolo, tempos, protocolo, normalizer_version, policy_version, hash e cutoff. Futuro, pendente, UNAVAILABLE, fixture ou dado não verificável/incompatível não é candidato.

## Defaults técnicos

| Regra | V1 |
| --- | --- |
| Habilitação | `learning.transfer.enabled: true` no template; ajustável só antes da partida. |
| Janela | 60d, revalidada por consulta. |
| Fonte | Outros símbolos do catálogo autorizado do proprietário. |
| Padrão | Grupo exato regime/RSI/volume/volatilidade/posição/família/horizonte; sem agregado estrangeiro global. |
| Fonte mínima | >=50 exemplos únicos não neutros/grupo; ganhos/perdas preservados, neutros reportados à parte. |
| Limite | Até 200/grupo, rodadas determinísticas entre símbolos; mais recentes primeiro por fonte, desempate ID. |
| Validação | >=30 labels destino não neutros com previsões sombra e intervalos decisão→maturação não sobrepostos. |
| Grupo de validação | Política/protocolo/destino/posição/família/horizonte/regime; reúne buckets elegíveis desse regime. |
| Contexto | Três padrões totais; locais primeiro, depois transferidos nas vagas, sem chave local repetida. |
| Inferência | Nenhum JEV por publicação/normalização/score; só decisão C já prevista, no orçamento global. |

Uma fonte BTC é suficiente para pesquisar; não exigir duas moedas. Rodadas reduzem dominância sem selecionar vencedores ou forçar proporção ganhos/perdas. Mínimos/espaçamento novos só para transferência, sem alterar aprendizado local.

## Validação prospectiva

Uma sombra por ciclo/contexto de C/família/horizonte com ID idempotente; não multiplicar pela origem A/B/C. Salvar p=(wins+1)/(wins+losses+2) antes do outcome destino, com composição/hash/cutoff e baseline: taxa local suavizada elegível do contexto/família/horizonte pela hierarquia da SPEC 10.3 naquele instante ou 0,5 quando ausente. É frequência de retorno positivo da família na fonte, não chance de lucro de uma ordem JEV.

Positivo y=1, negativo y=0; neutros auditados fora do score. Brier = média de (p−y)²; comparar ao baseline nos mesmos últimos 30 casos elegíveis, dentro de 60d. ACTIVE só com Brier estritamente menor. Igual/pior suspende, insuficiência aguarda dados. Não é teste de significância ou prova de lucro.

Construir série não sobreposta cronologicamente; próximo intervalo começa após término do anterior. Não selecionar por acerto. Guardar IDs; exemplos não são independência comprovada.

Validação por regime pode reunir buckets; só grupos fonte suficientes são utilizáveis. Mostrar escopo agregado de validação, sem alegar teste individual suficiente do bucket. Locais têm prioridade.

Mudança de política/normalizador/protocolo requer nova fase/run_id e série correspondente. Crescimento normal da fonte sob política fixa é permitido; cada previsão salva permanece congelada com seu hash. Nunca recalcular previsão após saber resultado ou escolher thresholds nos dados usados para declarar sucesso.

## Estados e recuperação

| Estado por destino/grupo | Significado |
| --- | --- |
| DISABLED | Configuração desabilitada. |
| NO_SOURCES | Sem fonte estrangeira compatível. |
| INSUFFICIENT_SOURCE | Grupo fonte não passa mínimo/qualidade/janela. |
| VALIDATING | Candidato com evidência destino insuficiente. |
| ACTIVE | Todos os gates atuais passam. |
| SUSPENDED | Piora/igualdade ou perda de elegibilidade; motivo persistido. |
| UNAVAILABLE | Consulta/catálogo indisponível; não renovar snapshot vencido. |

Reavaliar em cada consulta e após maturação; falha/frescor suspende apenas complemento afetado. Persistir transições/score/versão/cobertura. Restore revalida no cutoff atual sem resetar histórico.

## Contexto e dataset

Schema de memória versionado identifica source_scope LOCAL/TRANSFERRED, destino/fontes, contagens/janela/métricas/validação. No contexto, resumir fontes a até três símbolos e contagem/hash do conjunto completo; proveniência completa fica no SQLite/relatório. Não enviar acervo ou série sombra brutos. Valores financeiros em strings Decimal.

Dataset conserva observações originais/provenientes, nunca source_symbol reescrito como destino. Séries sombra/gates são estado de sessão no backup/relatório; dataset não transporta aprovação ACTIVE a nova sessão.

C−B mede memória presente, local e/ou transferida. Reportar origem/períodos/cobertura e suspensões; não atribuir efeito exclusivamente ao aprendizado local. Sombra não cria quarta carteira ou JEV extra.

Moeda nova pode começar VALIDATING. Software completo inclui gates testados, sem obrigar ativação real prematura; fixtures demonstram funcionamento, não vantagem econômica.
