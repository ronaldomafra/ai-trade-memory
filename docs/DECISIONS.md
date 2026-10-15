# Decisões do projeto

Registrar decisões aprovadas e sua relação com o contrato da POC. Aprovação de desenho e implementação são estados distintos. Questões abertas ficam em [PONTOS_A_ESCLARECER.md](PONTOS_A_ESCLARECER.md).

## D001 Comparações entre as carteiras enriquecidas

**Aprovada pelo usuário em 11/10/2026. Origem: P001. Implementação: pendente.**

Manter três carteiras independentes na V1, dentro do mesmo perfil operacional:

| Carteira | Dados de contexto | Decisão |
| --- | --- | --- |
| A | Indicadores técnicos | Regras determinísticas. |
| B | Indicadores, notícias por API e expectativas do Polymarket | JEV sem memória. |
| C | Mesmo contexto externo de B, acrescido de memória estatística | JEV com memória. |

**Confirmação explícita do usuário em 11/10/2026:** após avaliar se Polymarket poderia substituir notícias, manter as duas famílias de informação no contexto externo de B/C: notícias (Marketaux com RSS complementar/alternativo, D015–D017) e expectativas negociadas do Polymarket. Notícias são complemento; o ganho de qualidade ainda precisa de avaliação. Esta confirmação reafirma D001, sem nova variante de carteira ou alteração das cadências aprovadas.

Uma notícia e um mercado Polymarket podem refletir o mesmo acontecimento; presença em duas fontes não comprova evidências independentes nem autoriza somar confiança automaticamente. Preservar origem e relação com o evento; critérios de agrupamento/qualidade continuam em P012. A confirmação não aprova as categorias propostas em P011 nem define frequência ou mínimos de qualidade do Polymarket.

**Comparação principal C−B:** avaliar a contribuição incremental da memória. Manter iguais o snapshot externo, modelo, perguntas, custos simulados e regras de risco de B/C. Destacar o período posterior à disponibilidade da memória, número de amostras e quantidade de decisões influenciadas. Antes disso, compartilhar chamadas quando os estados forem equivalentes, conforme a SPEC.

**Comparação complementar B−A:** avaliar o pacote completo de JEV com notícias e Polymarket frente às regras técnicas. O resultado não isola exclusivamente a contribuição do modelo ou de uma fonte de contexto.

Avaliar retorno, drawdown, resultado líquido dos trades e custos reais de IA. Preservar a distinção entre USDT virtual e USD real e contabilizar cada chamada física uma vez. Nenhuma das comparações comprova desempenho persistente por um resultado isolado.

Não acrescentar uma quarta carteira na V1 para isolar o Polymarket. Um estudo específico com e sem essa fonte será um experimento separado, com as demais condições comparáveis.

**Justificativa:** preservar a pergunta central sobre aprendizado, mantendo um controle técnico e evitando ampliar o desenho inicial com vários tratamentos simultâneos.

**Impactos:** atualizar a composição de B/C e a interpretação das métricas nas seções 0, 7.3 e 14 da SPEC; refletir essa composição no README, nos contextos de desenvolvimento, fontes e TUI. Provedor da API de notícias, relação com RSS, filtros e qualidade do Polymarket continuam em P010/P011. P002 foi resolvido posteriormente em D003; os demais pontos seguem o registro de pendências.

## D002 Fatores de contexto com evidência curta

**Aprovada pelo usuário em 11/10/2026. Origem: discussão sobre processamento de notícias e Polymarket, registrada em P012. Implementação: pendente.**

Processar notícias e expectativas de eventos antes das decisões de negociação. Enviar fatores separados acompanhados de evidência curta, fonte, identificadores e horários. Preservar o significado do acontecimento; não reduzir todo o contexto externo a um único índice de confiança.

| Fonte | Processamento determinístico local | Classificação pelo JEV |
| --- | --- | --- |
| Notícias | Sanitização, deduplicação, agrupamento de cobertura, datas e filtros auditáveis. | Relevância para BTC, tipo de evento, impacto potencial e horizonte, com critérios versionados. |
| Polymarket | Probabilidade implícita com origem do preço, variação, spread, liquidez e idade do snapshot. | Relação semântica do evento com BTC quando necessária; não pedir cálculos já disponíveis por código. |

Separar relevância, impacto potencial, qualidade dos dados e confiança da classificação. Incluir estados indeterminado/indisponível; ausência de informação não representa neutralidade. Confiança do JEV não comprova veracidade da notícia, qualidade da fonte nem probabilidade de lucro. A probabilidade de um evento do Polymarket mantém seu significado original.

Classificar itens novos ou alterados na chegada e reutilizar resultados persistidos enquanto conteúdo, versão e validade permitirem. Atualizar métricas numéricas do Polymarket localmente. Não concentrar o processamento em uma única atualização diária. Usar título e resumo curto da fonte como evidência; não acrescentar um modelo gerador de resumos à V1.

B/C recebem o mesmo snapshot de fatores externos. O cache de classificação é processamento compartilhado das fontes, sem resultados históricos das carteiras, e não constitui a memória estatística exclusiva de C.

Toda classificação pelo JEV usa a Decisions API contratada e conta como chamada física nos limites globais já existentes: 240 chamadas/dia e US$ 0,05 de custo observado/dia. Persistir propósito da chamada, tokens, custo efetivo, modelo, versão dos critérios e vínculos aos itens processados. Não aumentar os limites implicitamente nem duplicar custo ao reutilizar os fatores em B/C.

Somente classificações concluídas e disponíveis antes do início da decisão podem integrar seu snapshot. Manter evidência, derivação e versões em SQLite para auditoria; uma revisão futura não altera decisões passadas. Validar classificação em exemplos com avaliações de referência e medir custo total, reutilização e qualidade antes do uso operacional. A redução de tokens e a melhoria de decisões são hipóteses a medir.

**Justificativa:** reduzir o reenvio de texto repetido, compartilhar processamento entre B/C e preservar evidência suficiente para interpretar os fatores.

**Impactos:** SPEC 1.2, coleta/contexto, custos, persistência, validação, Marco 5 e documentação de desenvolvimento, execução e TUI. Provedor/fallback permanecem em P010; seleção e qualidade do Polymarket em P011; critérios, limites de validade e política detalhada de classificação/falhas em P012. P002 sobre as chaves da memória foi resolvido posteriormente em D003.

## D003 Separação e hierarquia da memória

**Aprovada pelo usuário em 11/10/2026. Origem: P002. Implementação: pendente.**

Separar obrigatoriamente execução/perfil, símbolo, estado da posição, família do resultado e horizonte de avaliação em todos os agrupamentos da memória. Na V1, `run_id` delimita a execução e sua configuração/perfil imutável; não misturar execuções ou estilos diferentes.

**Revisão posterior:** D007 permite amostras de outras execuções por importação explícita validada e vínculo à execução destino, preservando origem e compatibilidade. As separações por símbolo, posição, família e horizonte e os mínimos continuam; não há transferência automática entre moedas.

Definir a chave obrigatória como `(run_id, symbol, position_context, label_kind, horizon_bars)`. O nível específico acrescenta `(market_regime, rsi_bucket, volume_bucket, volatility_bucket)` e exige pelo menos 30 resultados amadurecidos. Quando insuficiente, consultar o nível por regime: chave obrigatória mais `market_regime`, exigindo pelo menos 50 resultados amadurecidos. Se ambos forem insuficientes, retornar `historical_feedback.status=insufficient_samples`.

Usar `ENTRY_LONG_NET_RETURN` para carteira sem posição e `HOLD_VS_SELL_RETURN` para carteira com posição; preservar o significado de cada família e separar os horizontes 4/16. O fallback pode ampliar RSI, volume e volatilidade, mas mantém todas as separações obrigatórias e o regime. Não introduzir outro nível global na V1.

Preservar janela móvel de 60 dias, cutoff estrito de maturação e limite máximo de três padrões no contexto. Selecionar o nível elegível conforme a hierarquia, sem preencher o limite com padrões sem amostragem. Registrar chaves, nível, amostras, versões e vínculos à decisão. Notícias/Polymarket permanecem no contexto externo compartilhado de B/C e não acrescentam novas dimensões aos grupos de memória desta V1.

**Justificativa:** evitar mistura de retornos com interpretações distintas e manter uso possível da memória quando os grupos específicos ainda tiverem poucas observações.

**Impactos:** SPEC 1.3, seções 10.3–10.5, persistência e critérios de validação do Marco 4; documentação de desenvolvimento, execução, TUI e README. A origem dos resultados e sua deduplicação continuam em P008; a aprovação não define quais carteiras fornecem amostras nem transforma horizontes sobrepostos em observações independentes.

## D004 Trava diária com encerramento e bloqueio persistente

**Aprovada pelo usuário em 11/10/2026. Origem: P003. Implementação: pendente.**

Aplicar a mesma regra de risco independentemente a A/B/C: ao atingir ou ultrapassar 5% de perda sobre o patrimônio de referência do início do dia UTC, acionar `DAILY_RISK_GUARD`, encerrar toda a posição virtual existente com cotação fresca e bloquear novas compras até o próximo dia UTC. Não depender do JEV nem permitir que notícias/Polymarket desativem a proteção.

Usar patrimônio total: caixa mais BTC marcado ao bid público observado, conforme a seção 9.1 da SPEC. A referência é o início do dia, não o pico intradia. O percentual permanece configurável e fixo por execução; o default é 5%. Calcular com `Decimal`.

Persistir referência, dia UTC, cotação/horário de origem, acionamento, prazo de bloqueio e saída pendente por carteira no SQLite. Recuperação do patrimônio e restart no mesmo dia não removem a trava. Se faltar cotação fresca, manter bloqueio e encerramento pendente, sem inventar fill. Quando stop e trava coincidirem, preservar a prioridade de saída contratada e registrar também o acionamento da trava, sem duplicar venda.

No próximo dia, estabelecer uma nova referência válida e liberar entradas quando os dados e demais validações permitirem. Usar o primeiro estado observado válido do novo dia, preservando seu horário; não fabricar patrimônio à meia-noite quando o serviço estava sem dados ou desligado. Uma saída de proteção já pendente permanece até o fechamento com cotação válida; o rollover não a cancela. Encerramento por proteção continua impedindo reentrada no mesmo ciclo.

**Justificativa:** fazer da perda diária uma interrupção da exposição e das entradas daquela carteira, com regra determinística, auditável e resistente a reinícios.

**Impactos:** SPEC 1.4, cálculo/precedência de risco, retomada, persistência por dia/carteira, eventos e testes; contextos de desenvolvimento, execução e TUI e resumo de risco no README. P004 foi resolvido posteriormente em D005; os demais pontos seguem o registro de pendências.

## D005 Duas tentativas totais por requisição JEV

**Aprovada pelo usuário em 11/10/2026. Origem: P004. Implementação: pendente.**

Limitar cada requisição lógica ao JEV a duas tentativas totais: uma inicial e, quando necessário, uma única repetição. Definir `max_retries: 1`, onde retries contam repetições após a chamada inicial. A regra vale para classificação de contexto e decisão de negociação pela Decisions API; não define políticas dos provedores de notícias/Polymarket.

Repetir somente falhas transitórias, respeitando backoff/jitter, `Retry-After`, orçamento global e prazo útil. Para negociação, não iniciar repetição quando a espera e o timeout não couberem na janela restante do candle. Interromper chamadas diante de erro de credencial/crédito; resposta inválida segue falha segura, sem repetição automática para tentar obter outra decisão.

Persistir cada tentativa física separadamente, vinculada a um `logical_request_id` e `attempt_index` 1 ou 2. Registrar ID da resposta quando houver, propósito, horários, tokens e `usage.cost` observado. Timeout após envio pode ter cobrança desconhecida: registrar `unknown_billing_possible`, sem custo oficial igual a zero. As tentativas entram nos limites globais existentes; reutilização B/C não duplica cobrança.

Preservar o número de tentativas após restart e impedir uma terceira por reinício ou retries adicionais na camada HTTP/SDK. Uma resposta tardia não gera outra decisão ou fill. Se a decisão de negociação terminar sem resposta válida ou sem prazo/orçamento, aplicar HOLD seguro; monitoramento e saídas de risco continuam. Classificação sem resultado válido preserva indisponibilidade, sem inventar fatores; a política detalhada do contexto externo permanece em P012.

**Justificativa:** permitir uma recuperação de falha transitória com consumo e espera limitados, mantendo rastreabilidade de cobranças indeterminadas.

**Impactos:** SPEC 1.5, configuração de IA, contrato de falhas/custos, persistência de tentativas e testes do Marco 3; contextos de desenvolvimento, execução e TUI e README. Timeout de 20s, janela de 90s e orçamento global permanecem. P005 foi resolvido posteriormente em D006.

## D006 Labels indisponíveis sem cotação no horizonte

**Aprovada pelo usuário em 11/10/2026. Origem: P005. Implementação: pendente.**

Usar o primeiro bid público válido observado na janela inclusiva de 90s após cada horizonte de 4/16 candles, nas duas famílias de labels. Até a janela encerrar, a avaliação pode permanecer pendente. Sem bid elegível, manter `UNAVAILABLE`, motivo e horários para diagnóstico; retorno e indicador de sucesso permanecem nulos. Excluir esses registros das amostras e estatísticas da memória, sem tratá-los como neutros ou perdas.

Persistir continuamente as cotações observadas no SQLite. Na retomada, aproveitar cotações elegíveis já salvas, sem fabricar preço durante a interrupção. Backfill de candles não recompõe bid/ask ausentes; uma cotação dez minutos depois não representa o mesmo horizonte. Não adicionar fonte histórica de cotações na V1; avaliar uma extensão separadamente se a cobertura justificar.

Reportar labels esperados, pendentes, avaliados e indisponíveis por carteira, família e horizonte, além dos motivos. Medir cobertura entre janelas encerradas, sem esconder dados ausentes. Essa falta pode atrasar a memória, mas não modifica fills, ledger ou PnL realizado.

**Justificativa:** manter resultados auditáveis e evitar aprendizado sobre preços que o serviço não observou no horizonte contratado.

**Impactos:** SPEC 1.6, avaliador de resultados, persistência de cotações/outcomes, backfill, relatórios e testes do Marco 4; contextos de desenvolvimento, execução e TUI. Nessa revisão, a política de dataset entre execuções estava pendente em P013; importação/exportação foram aprovadas posteriormente em D007.

## D007 Importação e exportação de dataset acumulativo

**Aprovada pelo usuário em 11/10/2026. Origem: P013. Implementação: pendente.**

Permitir exportar observações amadurecidas e importar explicitamente uma base inicial para C em novas execuções compatíveis. O usuário aprovou importação e exportação e descreveu evolução mensal, incluindo intenção de acumular experiências de moedas diferentes. Preservar versões: cada nova exportação reúne amostras anteriores válidas e novas amostras locais amadurecidas, deduplicadas, com identidade original, proveniência, schema, predecessores e hashes.

Dataset é acervo histórico; memória ativa continua filtrada por protocolo compatível, símbolo, janela de 60 dias e cutoff temporal. Guardar resultados positivos, negativos e neutros; ausência de cotação não vira exemplo de treinamento. Recalcular estatísticas, respeitando mínimos 30/50 e máximo de três padrões. Não retreinar pesos do JEV nem enviar o arquivo bruto a cada decisão.

Esta decisão revisa o isolamento absoluto entre execuções de D003: amostras externas só participam por vínculo explícito validado à execução destino, mantendo `origin_run_id`. Sem importação, continua o aprendizado local isolado. B permanece sem memória. Não importar saldo/posições nem alterar parâmetros durante a avaliação; novas carteiras continuam com 100 USDT. Importação é fixada antes da primeira decisão; retomada usa SQLite, não uma releitura de arquivo modificado.

**Confirmação explícita do usuário em 11/10/2026:** permitir iniciar sessão nova com dataset selecionado/validado ou sem dataset. No primeiro caso, somente C recebe amostras elegíveis como memória inicial; no segundo, C acumula aprendizado local e aguarda os mínimos contratados. Retomar uma sessão existente recupera a memória do SQLite, sem exigir outra importação. Esta confirmação reforça D007; não resolve a proposta de carteiras fornecedoras/equivalências de P008.

O dataset pode preservar partições de diferentes ativos na evolução solicitada, sem juntar suas taxas de acerto. Usar BTC como memória estatística para outro ativo exige contrato de transferência/normalização e validação temporal: esse método e a fase de operação com outra moeda ficam em P014. Aprovação de importação/exportação não remove a separação por símbolo nem habilita múltiplos pares na V1.

Mais dados podem ampliar cobertura; uma nova versão não é automaticamente mais precisa ou equilibrada. Reportar composição por ativo/regime/período, origem e qualidade, preservando perdas. Avaliar melhoria em dados posteriores; não selecionar ou reponderar exemplos para melhorar resultados do mesmo período usado como evidência.

**Justificativa:** reutilizar o aprendizado local, acumular observações auditáveis e permitir evolução mensurável do acervo entre sessões.

**Impactos:** SPEC 1.7, configuração de base inicial, seção 10.8, CLI e persistência de importação/exportação, relatórios e testes do Marco 4; contextos de desenvolvimento, execução e TUI. P008 continua definindo carteiras fornecedoras/equivalências e independência; P014 reserva transferência entre ativos e critérios de equilíbrio. Não há dados reais de aprendizado ou código de importador/exportador ainda.

## D008 Memória específica por ativo e avaliação de padrões compartilháveis

**Desenho aprovado pelo usuário em 11/10/2026. Origem: P014. Implementação e validação: pendentes.**

Preservar memória específica por moeda e avaliar separadamente padrões compartilháveis entre ativos. Acumular observações em datasets versionados conforme D007, com origem e deduplicação, sem tratar estatísticas da primeira moeda como resultados observados na segunda. A camada compartilhada é uma direção aprovada de avaliação; ainda não há pesos, normalização, prioridade, mínimos ou critérios de ativação definidos.

Construir um acervo com ganhos, perdas, neutros e diferentes condições de mercado, incluindo oportunidades avaliadas após HOLD segundo P008. Avaliar equilíbrio por cobertura de ativo/regime/período e qualidade; não forçar metade ganhos/metade perdas. Preservar histórico e medir melhoria em períodos posteriores, com versões e critérios fixados antes da avaliação. Crescimento do arquivo não comprova maior precisão.

**Justificativa:** permitir reaproveitamento investigável entre moedas, mantendo evidência específica e avaliação auditável do benefício da transferência.

**Impactos:** SPEC 1.8, seção 10.9 e documentação do dataset, desenvolvimento, execução e TUI. P014 passa a desenho aprovado com detalhes técnicos/fase pendentes; não reabrir importação/exportação já aprovadas. V1 continua BTC/USDT com agrupamentos por símbolo; janela, mínimos, limite de contexto e orçamento permanecem. A aprovação não afirma que transferência foi implementada ou validada. Retomar a sequência de discussão em P006, que permanece aberto.

## D009 Perfis escolhidos antes da partida e dois perfis após homologação

**Requisito aprovado pelo usuário em 11/10/2026. Origem: P006. Implementação: pendente.**

Preparar perfis desde a primeira versão e exigir seleção explícita antes de iniciar uma sessão nova. Perfil é o contrato de estilo/regras; A/B/C são variantes de decisão dentro dele. Guardar ID/versão e configuração efetiva imutável; não habilitar candidato sem algoritmo, parâmetros completos e testes. O contrato técnico atual recebe identidade `trend_15m_v1`, sem chamar isso de perfil já implementado ou definir horário de encerramento por seu nome.

O usuário pretende rodar dois perfis após sua homologação, com mais evidências para avaliar ajustes. Cada um deve preservar seu próprio experimento A/B/C; dois perfis correspondem a seis carteiras virtuais independentes de 100 USDT. Não trocar perfil/parametrização dentro da sessão para melhorar retrospectivamente seus resultados. Dados de aprendizado preservam compatibilidade de perfil, inclusive na importação.

**Justificativa:** permitir escolher o comportamento operacional na partida e comparar estratégias identificáveis sem misturar o efeito do estilo com o da memória.

**Impactos:** SPEC 1.9, registro/validação de perfis nos Marcos 1–2, CLI, persistência/relatórios e contextos. P006 continua definindo quais perfis e suas políticas; operação conjunta/orçamento fica em P015. Homologação é o termo do usuário para sua validação; não implica certificação externa nem aprovação de dois perfis ainda não escolhidos.

## D010 Banco independente por sessão e restauração explícita

**Requisito aprovado pelo usuário em 11/10/2026. Origem: esclarecimento sobre sessões durante P006. Implementação: pendente.**

Cada sessão possui SQLite e artefatos próprios. Identificar sessão pelo `run_id`, com perfil/configuração e trio A/B/C persistidos. Nova sessão recebe identidade/banco novos e 100 USDT por carteira; restauração abre somente o banco escolhido e recupera saldos, posições, risco, ciclos, tentativas, memória e histórico sem reset, duplicação ou trades retroativos. Banco ausente/inválido não vira sessão nova automaticamente.

Guardar logs/exports em `data/sessions/RUN_ID/`, com caminhos resolvidos e lock por sessão. Sessões diferentes podem operar separadamente; uma mesma sessão não admite dois motores. Memória pode ser importada/exportada conforme D007 sem compartilhar estado financeiro. O orçamento de IA permanece global e precisa de coordenação entre motores antes da operação conjunta de D009; não multiplicar limites por banco.

O usuário deseja iniciar ou restaurar sessões pela futura TUI e determinou discutir essa interface por último. Guardar esse fluxo em P007, mantendo criação/restauração como contrato do serviço/CLI. Fase e controles da TUI ainda não foram definidos; esta decisão não inicia sua implementação.

**Justificativa:** conservar experimentos independentes, permitir retomada exata e distinguir nova sessão de recuperação de estado existente.

**Impactos:** SPEC 1.9, paths, banco por sessão, CLI e recuperação nos Marcos 1–2; relatórios, datasets e contextos. P015 reserva operação conjunta, orçamento e critérios de homologação; P007 será o último ponto discutido. Sessão persistida não equivale a dia UTC ou horário de day trade.

## D011 Primeiro perfil de curto prazo contínuo

**Aprovado pelo usuário em 11/10/2026. Origem: aprovação da proposta inicial de P006 antes da discussão de arquitetura. Implementação e homologação: pendentes.**

Adotar `trend_15m_v1` como primeiro perfil: operação contínua 24/7, decisões em candles fechados de 15m, confirmação em 1h e duração máxima nominal de 16 candles (~4h). Preservar regras técnicas, risco, custos e aprendizado da SPEC. Não acrescentar encerramento compulsório na virada UTC; essa referência continua controlando a trava diária de D004. Um processo disponível continuamente não mantém necessariamente uma posição aberta.

O segundo perfil ainda precisa ser escolhido e especificado. Esta aprovação não define scalping, swing ou hold, nem habilita execução sem testes. O usuário solicitou discutir arquitetura hexagonal/Docker antes de prosseguir; a avaliação fica em P016, com TUI por último em P007.

**Justificativa:** começar com o contrato técnico existente e uma política temporal explícita, preservando comparabilidade e sessões persistidas.

**Impactos:** SPEC 1.10, seção 4.1; perfis, execução e desenvolvimento. P006 passa a ter primeiro perfil aprovado e segundo pendente. A proposta de arquitetura ainda não é uma decisão aprovada de infraestrutura.

## D012 Arquitetura hexagonal e Docker Compose por sessão

**Base aprovada pelo usuário em 11/10/2026 ao solicitar seguir após a apresentação de P016. Implementação: pendente.**

Organizar um único projeto Python modular com domínio, aplicação, portas e adaptadores. Manter regras de paper trading, risco e estatísticas independentes das tecnologias externas. CLI/agendamento e futura TUI acionam casos de uso; integrações públicas, JEV e persistência implementam portas. SQLite continua realizando fill, ledger, saldo e eventos em uma única transação.

Adotar imagem Docker versionada comum e Docker Compose no mesmo servidor, com um motor/container por sessão e armazenamento local persistente próprio. Cada sessão conserva perfil, SQLite, logs, exportações e trio A/B/C. Criar sessão é explícito; o processo permanente restaura o mesmo `run_id`, inclusive após recriação do container. Preservar lock por sessão, sinais de parada, saúde e recuperação, sem reset de capital ou trades retroativos. A CLI nativa permanece disponível e systemd é alternativa de execução.

O orçamento de IA continua global. A necessidade de coordenação está aprovada; mecanismo específico, reservas, distribuição/prioridades e capacidade permanecem em P015. Não considerar aprovados o SQLite adicional de orçamento ou suas cotas apenas por esta decisão. Segundo perfil permanece em P006; contrato da TUI será discutido por último em P007.

**Justificativa:** separar responsabilidades e permitir testes isolados, execução independente e retomada persistida de múltiplas sessões.

**Impactos:** SPEC 1.11, seções 2–3, 15–19; organização hexagonal no Marco 1, imagem/Compose e retomada no Marco 2, validação operacional no Marco 5. Atualizar contextos e layout planejado. A aprovação do desenho não comprova deploy ou operação 24/7, nem muda limites de chamadas/custo ou contratos financeiros.

## D013 Pré-configuração por estratégia e ajustes antes da sessão

**Requisito definido pelo usuário em 11/10/2026. Origem: esclarecimento de P006. Implementação: pendente.**

Cada estratégia suportada terá uma pré-configuração baseada nos seus documentos. Na futura TUI, antes de iniciar a sessão, selecionar a estratégia, carregar essa base e permitir alterações nos seus parâmetros. Escolha dos perfis de uso ocorre na partida, sem exigir fixar agora o segundo estilo. O catálogo operacional continua limitado a perfis com contrato, implementação e validação próprios; pesquisa não equivale a capacidade executável.

Manter template estruturado/versionado com referência documental, unidades, campos editáveis e regras de validação. A aplicação resolve defaults mais ajustes explícitos e valida a configuração antes de criar carteiras/chamar IA. Persistir template, alterações, configuração efetiva e hash; aplicar a mesma parametrização ao trio A/B/C. Não alterar template canônico por editar uma sessão nem ampliar implicitamente o orçamento global.

Durante a sessão, conservar parâmetros; restauração recupera os valores efetivos salvos, sem aplicar defaults atualizados. Ajustes para outro experimento exigem sessão nova. Revalidar compatibilidade de importação de memória segundo protocolo/configuração efetivos. As restrições de paper trading e demais limites absolutos continuam vigentes.

Guardar o requisito de configuração antes da partida na referência TUI, sem antecipar telas, fase ou controles operacionais de P007. P006 passa a ter desenho de seleção/configuração resolvido, com catálogo, contratos dos estilos e campos editáveis ainda a especificar; continuar a pauta em P008.

**Justificativa:** facilitar início com parâmetros documentados e permitir experimentos configuráveis e reproduzíveis por sessão.

**Impactos:** SPEC 1.12, seções 4, 16, 17 e 19; templates/validação no Marco 1 e persistência/retomada, relatórios, datasets e contextos. Não autoriza negociação real, ajuste intrassessão ou operação de perfil ainda incompleto.

## D014 Origem A/B/C e deduplicação dos exemplos de memória

**Aprovado pelo usuário em 11/10/2026. Origem: P008. Implementação: pendente. Dependência entre candles consecutivos: reservada para discussão posterior por pedido explícito do usuário.**

A memória de C considera labels contrafactuais válidos e amadurecidos das decisões de A, B e C, incluindo estados elegíveis com HOLD. Preservar separação por símbolo, perfil/protocolo compatível, estado da posição, família e horizonte. PnL realizado das carteiras permanece uma medida financeira distinta desses labels; B continua sem histórico no contexto JEV.

Quando os dados de avaliação forem equivalentes, contar um único exemplo estatístico, com vínculos a todas as decisões de origem. Comparar contexto/features originais, instante/candle, cotações e horários, família/horizonte, custos e versões do protocolo; preservar quantidade/orçamento e outros dados quando afetarem o cálculo. Mesmo candle ou mesmo retorno, isoladamente, não bastam. Não escolher a origem pelo melhor resultado nem fundir avaliações materialmente diferentes.

Deduplicar apenas a camada estatística e o dataset: decisões, avaliações individuais, fills, ledger e saldos continuam preservados por carteira. Manter identidade estável do exemplo e identidades originais de seus vínculos, inclusive em importações, arquivos sobrepostos e reexportações. Filtrar maturação e disponibilidade de cada origem antes de contar o exemplo no cutoff da decisão; um vínculo posterior não ganha elegibilidade retroativa pelo grupo.

Os mínimos de 30/50 e as estatísticas usam exemplos únicos elegíveis, sem triplicar contagens por carteira. Continuam a janela de 60 dias, máximo de três padrões e demais regras de D003/D007. Versionar a política para tornar o conjunto usado reconstruível.

**Pendência guardada em P008:** avaliações de candles consecutivos podem compartilhar o mesmo trecho futuro nos horizontes 4/16. Exemplos únicos não são automaticamente independentes. Reservar medição de sobreposição/dependência e escolha do tratamento de amostragem e incerteza; esta aprovação não define espaçamento, pesos, tamanho amostral efetivo ou novos mínimos.

**Justificativa:** aproveitar avaliações observadas pelas três variantes sem inflar artificialmente a memória, mantendo proveniência e comparação B/C.

**Impactos:** SPEC 1.13, seções 10, 12, 16 e Marco 4; dataset, contextos e pauta. Origem/deduplicação de P008 aprovada; dependência temporal continua aberta. Nenhuma implementação ou validação estatística foi realizada nesta decisão.

## D015 API de notícias com plano gratuito

**Definido pelo usuário em 11/10/2026. Origem: P010, orçamento da fonte. Provedor, cadência e papel do RSS: pendentes. Implementação: pendente.**

Usar uma API de notícias com plano gratuito para a POC, sem assinatura adicional da fonte. Selecionar um plano que permita o uso contínuo pretendido; não considerar avaliação temporária garantia de gratuidade contínua nem ativar plano pago automaticamente. Gratuidade da fonte não altera o custo das chamadas JEV previstas em D002.

Escolher provedor considerando cobertura de BTC e contexto macro, frescor, limites de requisições/artigos e condições de armazenamento. Dimensionar coleta, paginação e repetição dentro da cota, incluindo sessões simultâneas; limite da conta não se multiplica por carteira ou banco. Limite atingido ou falha não significam ausência de notícias ou sentimento neutro.

Esta definição aprova a restrição de custo, sem escolher Marketaux ou outro fornecedor, frequência, complementação/fallback por RSS ou política de falha de B/C. Pesquisa e proposta concreta ficam em [FONTES_DE_CONTEXTO.md](FONTES_DE_CONTEXTO.md); concluir detalhes em P010 antes de implementar o adaptador.

**Justificativa:** manter enriquecimento por notícias sem acrescentar assinatura de dados à POC.

**Impactos:** SPEC 1.14, seção 5.4, fontes e contextos. Preservar orçamento JEV, contratos financeiros e Marcos 1–5. Nenhuma conta, credencial ou integração foi criada/validada por esta decisão.

## D016 Marketaux gratuito com RSS complementar

**Aprovado pelo usuário em 11/10/2026 ao solicitar seguir com o provedor proposto. Origem: P010, proposta Marketaux + RSS. Implementação e coleta autenticada: pendentes.**

Selecionar Marketaux no plano gratuito como API de notícias da POC, conforme D015. Manter RSS como complemento de cobertura/frescor e alternativa quando a API falhar ou atingir sua cota. O papel complementar permite coletar RSS também enquanto a API está disponível; não restringi-lo a falhas.

Normalizar API/RSS no mesmo contrato temporal, deduplicar notícias equivalentes preservando proveniência e usar o mesmo snapshot disponível em B/C. Persistir publicação, primeira coleta, origem e evidência curta; processar fatores conforme D002. Manter status de cada fonte separado da disponibilidade dos itens usados: falha de uma fonte não torna indisponíveis os dados válidos das demais nem equivale a notícia neutra. Cobertura parcial deve permanecer identificável.

Usar HTTP público de notícias somente leitura em `https://api.marketaux.com/v1/news/all`, com token da fonte em ambiente local, removido de URLs/logs/erros persistidos. Essa credencial não é uma credencial de exchange e não permite operações financeiras. Validar acesso, cobertura, quota efetiva e condições de retenção antes do uso operacional; escolha do provedor não comprova integração.

**Pendências de P010:** frequência da API, consultas/filtros, paginação, reserva de quota para repetições e coordenação da coleta entre sessões. RSS mantém o default vigente de 10m; não copiar essa frequência para a API. A proposta de API a cada 30m continua em discussão, sem aprovação implícita nesta escolha. Critérios detalhados de validade/falha dos fatores continuam em P012; orçamento JEV e finanças permanecem iguais.

**Justificativa:** combinar uma API gratuita de notícias com as fontes RSS já previstas, preservando cobertura e rastreabilidade diante de limites/falhas.

**Impactos:** SPEC 1.15, seções 0, 2, 4, 5, 16–19; fontes e contextos. Implementar API/RSS no Marco 5 após completar P010, com testes offline se não houver token. Não há conta, token ou adaptador criado por esta aprovação.

## D017 Cadência inicial de coleta de notícias

**Aprovado pelo usuário em 11/10/2026. Origem: P010, confirmação da proposta de frequência após D016. Implementação: pendente.**

Adotar Marketaux a cada 30 minutos e RSS a cada 10 minutos como pré-configuração inicial. Registrar separadamente `news.api_provider: marketaux`, `news.api_poll_minutes: 30` e `news.poll_minutes: 10` para RSS. Ajustes antes de uma nova sessão seguem D013, com validação de quota/compatibilidade; restauração recupera os valores persistidos.

A frequência é de coleta de notícias, distinta do candle de decisão de 15m e do monitoramento de risco. B/C continuam usando o mesmo snapshot externo disponível no início da decisão. Não consultar novamente por carteira nem reclassificar itens inalterados a cada candle; conservar reutilização e rastreabilidade de D002/D016.

Uma consulta periódica de API a cada 30m corresponde nominalmente a 48 requisições/dia, antes de paginação, buscas adicionais ou repetições. Isso não reserva automaticamente as demais chamadas nem garante cobertura completa. Cota pertence à conta do fornecedor; duas sessões isoladas somariam 96 chamadas periódicas, exigindo dimensionamento/coordenação antes de operar conjuntamente.

**Pendências reservadas em P010:** consultas/filtros, paginação, reserva de quota, coordenação de coleta/cache entre sessões e validação de cobertura/latência/retenção. Nenhum mecanismo compartilhado, quantidade de páginas ou nova cota foi aprovado nesta confirmação. Base de provedor/RSS/cadência definida; prosseguir a pauta em P011, preservando esses detalhes para fechamento técnico.

**Justificativa:** separar as cadências da API e do RSS e manter margem potencial para operações adicionais dentro do plano gratuito.

**Impactos:** SPEC 1.16, configuração e coleta no Marco 5, contextos e pauta. Testar agendas independentes e contagem física de chamadas conforme o contrato de quota a completar. Não altera orçamento JEV, finanças, critérios da memória ou fase da TUI; nenhuma coleta autenticada foi validada.

## D018 Seleção do contexto externo pela relevância para o ativo

**Aprovado pelo usuário em 11/10/2026, após esclarecer o comportamento para outra moeda sem influência de BTC. Origem: P011. Implementação: pendente.**

Selecionar notícias e mercados Polymarket pelo ativo da sessão. Na V1 BTC/USDT, priorizar BTC, juros/decisões do Fed e regulação cripto; geopolítica exige motivo concreto de relevância. Guardar motivo de inclusão/exclusão, sem escolher por popularidade ou por resultados observados posteriormente.

Na evolução para outra moeda, priorizar eventos/notícias da própria moeda, protocolo e ecossistema. Incluir fatores sobre BTC apenas quando houver relação justificada com o destino, sem presumir correlação permanente. Macro/regulação também precisam de relevância direta para o ativo, mesmo quando ele não acompanha BTC. Identificar o destino da classificação; não reaproveitar automaticamente fatores interpretados para BTC como se fossem classificados para outra moeda.

Sem mercado Polymarket relevante, registrar ausência de cobertura, sem transformar isso em cenário neutro, probabilidade de 50% ou confiança inventada. Não confundir coleta falha com resposta válida sem mercados relacionados. Quando B/C poderão abrir posições com cobertura parcial permanece em P012, sem política operacional nova nesta aprovação.

A memória de C continua separada por símbolo conforme D008. Dataset importado de BTC não ativa suas estatísticas para outro ativo; transferência de padrões permanece em P014. A V1 continua BTC/USDT: esta decisão orienta seleção de contexto e evolução, sem habilitar múltiplos pares.

**Pendências de P011:** compatibilidade dos horizontes, limites de frescor/spread/liquidez/profundidade, frequência de coleta e validação de acesso automático. Critérios semânticos, pesos, validade, falhas e orçamento continuam em P012/P015. Categorias aprovadas não comprovam cobertura ou vantagem preditiva.

**Justificativa:** adequar o contexto à moeda analisada, evitando carregar influência de BTC ou evidência sem relação demonstrada por simples padrão de configuração.

**Impactos:** SPEC 1.17, seções 0, 5.5–5.6 e 16; fontes, contextos e pauta. Implementação no Marco 5 após completar P011/P012. Configuração de fontes, orçamento JEV, memória, finanças e fase da TUI permanecem conforme decisões anteriores.

## D019 Prazos dos eventos em relação à janela da estratégia

**Aprovado pelo usuário em 11/10/2026. Origem: P011, proposta apresentada após D018. Implementação: pendente.**

Interpretar pergunta, regras e prazo/período do evento Polymarket em relação à janela do perfil. No primeiro perfil, decisões a cada 15m e posições por até 16 candles (~4h) são referências operacionais distintas da duração do evento.

Eventos distantes podem entrar como contexto relevante, sem interpretar sua probabilidade como previsão para o próximo candle. Identificar eventos previstos durante a janela da estratégia, sem aumentar automaticamente confiança ou chance de lucro. Prazo incerto permanece explícito; distinguir data/período do acontecimento e prazo de resolução do mercado, sem usar `endDate` como data presumida do acontecimento.

Preservar evidência, critérios/versões e disponibilidade temporal no snapshot externo comum B/C conforme D002. Novas informações não reescrevem contextos passados. A aprovação não muda os labels 4/16, o tempo máximo em posição ou regras de risco.

**Pendências:** qualidade/frescor, spread/liquidez/profundidade, frequência de coleta e acesso automático continuam em P011. Critérios detalhados, pesos, validade, falhas/cobertura parcial e orçamento seguem P012/P015. Não foram escolhidos pesos, limites numéricos de proximidade ou nova cadência.

**Justificativa:** permitir contexto de diferentes durações sem confundir expectativa de um evento com previsão de preço no horizonte da operação.

**Impactos:** SPEC 1.18, seções 5.6–5.7 e 16; fontes, contextos e pauta. Implementar no Marco 5 após completar os contratos de P011/P012. Nenhum adaptador ou classificação real foi validado por esta decisão; a TUI segue para discussão final.

## D020 Filtro de qualidade dos dados Polymarket

**Aprovado pelo usuário em 11/10/2026. Origem: P011, proposta apresentada após D019. Implementação: pendente.**

Antes de usar preços e variações do Polymarket no contexto quantitativo JEV, verificar por código: validade do mercado/resultado/preço; frescor das cotações e atividade recente; spread entre melhor bid/ask; liquidez e quantidade disponível perto do preço no livro. Identificar janelas de volume/atividade e distinguir métricas por mercado/resultado de totais agregados. Popularidade e volume acumulado não substituem o filtro.

Uma consulta recente não comprova negociação recente; `updatedAt` de metadados não comprova cotação atual. Profundidade requer dados do livro, sem inferi-la apenas pela liquidez agregada. Preservar origem do preço, horários e significado dos timestamps.

Dados inválidos/vencidos, qualidade insuficiente ou não verificável ficam fora dos sinais quantitativos utilizáveis enviados ao JEV, com status/motivo registrados para auditoria. Não converter rejeição em cenário neutro, 50% ou ausência presumida de acontecimentos. Aplicar o mesmo conjunto elegível em B/C, sem invalidar automaticamente notícias válidas de outra fonte.

**Pendências:** limites numéricos de frescor/spread/liquidez/profundidade/atividade, frequência de coleta e validação de acesso continuam em P011. Pontuação/pesos, validade das classificações e comportamento operacional de B/C com cobertura parcial seguem P012; esta decisão não bloqueia/libera entradas automaticamente.

**Justificativa:** evitar que indicadores numericamente precisos, mas sem qualidade observável suficiente, orientem a decisão como sinais utilizáveis.

**Impactos:** SPEC 1.19, seções 5.6 e 5.8 e 16; fontes, contextos e pauta. Implementação no Marco 5 após completar os contratos. Não altera orçamento JEV, finanças, memória ou fase da TUI; nenhuma coleta ou calibração operacional foi validada.

## D021 Binance pública com transporte híbrido WebSocket/REST

**Aprovado pelo usuário em 11/10/2026, após discutir WebSocket e esclarecer a ausência de vantagem documentada de estabilidade por chave de conta. Origem: P016, transporte de mercado. Implementação e conexão real: pendentes.**

Adotar na V1 WebSocket público somente de mercado da Binance para atualizações de bid/ask e candles, com REST público para aquecimento/histórico, recuperação de candles após interrupções e alternativa de cotações quando o stream falhar ou não fornecer dado fresco. Usar o domínio de mercado `data-stream.binance.vision`, canais `btcusdt@bookTicker`, `btcusdt@kline_15m` e `btcusdt@kline_1h`; REST mantém `data-api.binance.vision`. Não carregar chave/segredo de exchange nem cliente com suporte a negociação real.

A decisão do perfil inicial continua no fechamento de candle 15m, com tendência 1h fechada. Atualização de preço não dispara JEV; monitoramento de risco é independente e usa cotação validada. Preservar limite de frescor, saldo, regras paper, labels 4/16, maturação e orçamento de IA.

Implementar/testar ping/pong, renovação/reconexão, recuperação de assinaturas, gaps de candles, mensagens atrasadas/duplicadas e precedência/frescor dos dados entre transportes. Registrar IDs e timestamps disponíveis com seus significados, sem fabricar timestamp de evento ausente. REST de monitoramento conserva referência de aproximadamente 10s quando necessário como alternativa, sem repetir aquecimento completo a cada consulta.

Cotação fresca/persistida, cutoff, idempotência e transações financeiras permanecem obrigatórios. Recuperar candles não recupera bids históricos ausentes e não autoriza trades retroativos; D006 permanece. Conexão aberta ou ping recebido não comprova preço atual. Dados inválidos/ausentes por ambos os meios impedem novas posições e preservam saídas pendentes sem inventar preço.

**Justificativa:** receber atualizações de mercado durante a operação e preservar uma rota REST para inicialização e recuperação, sem depender de credenciais desnecessárias à POC.

**Impactos:** SPEC 1.20, seção 5.1, testes 16 e Marco 2; arquitetura, contextos e pauta. Revisar implementação de transporte/dimensionamento da persistência antes do aceite 24/7, com testes offline quando necessário. Não habilita operações reais, novo ativo ou alteração da cadência JEV. A proposta de coleta Polymarket 5m/60m/cache 10m continua pendente em P011, separadamente desta aprovação.

## D022 Cadência Polymarket e validade do snapshot em cache

**Aprovado pelo usuário em 11/10/2026, ao confirmar os intervalos propostos após D021. Origem: P011. Implementação/coleta real: pendentes.**

Para o perfil inicial `trend_15m_v1`, coletar preços/livros dos mercados selecionados a cada 5 minutos e revisar descoberta/metadados na inicialização e a cada 60 minutos. Aceitar snapshot em cache por até 10 minutos desde a última observação pública bem-sucedida e validada, sujeito ao filtro de qualidade D020 e à disponibilidade no início da decisão. Limite inclusivo: exatamente 10m permanece dentro do teto; acima dele, sinal quantitativo vencido.

Registrar pré-configuração separada `polymarket.prices_poll_minutes: 5`, `markets_poll_minutes: 60` e `snapshot_max_age_minutes: 10`. Ajustes antes de sessão seguem D013, com validação/persistência e restauração dos parâmetros efetivos. Esses valores são iniciais experimentais, sem calibração operacional comprovada ou aplicação universal a outros perfis.

Releitura do cache, falha de consulta e atualização apenas de metadados não renovam a idade do preço/livro. Cache recente não comprova negócio recente nem substitui validação do estado/tempo dos dados da fonte e de atividade. Preservar motivo de exclusão sem neutralidade ou probabilidade inventada.

A coleta atualiza números localmente e não exige uma chamada JEV por consulta; classificações necessárias de conteúdo novo/alterado seguem D002/P012 e orçamento global. B/C usam o mesmo snapshot externo disponível, sem consulta duplicada por carteira ou revisão retroativa. Não muda decisões por candle, monitoramento de risco Binance, transporte D021 ou cadências Marketaux/RSS.

**Pendências de P011:** limiares de spread/liquidez/profundidade/atividade, dimensionamento de mercados/paginação e validação da rota pública. Cobertura parcial, falhas, validade de classificação e critérios/pesos seguem P012; coordenação entre sessões P015. Não define liberação/bloqueio de entradas por fonte vencida.

**Justificativa:** atualizar expectativas entre decisões do perfil de 15m, com agendas separadas e validade explícita dos dados reutilizados.

**Impactos:** SPEC 1.21, seções 0, 4, 5.9, 16 e Marco 5; fontes, contextos e pauta. Testar cadência/cache com relógio controlado e preservar configuração da sessão. Nenhuma coleta Polymarket, integração ou vantagem preditiva foi validada por esta aprovação.

## D023 Spread máximo inicial Polymarket

**Aprovado pelo usuário em 11/10/2026. Origem: P011, limite de spread proposto após D022. Implementação/calibração: pendentes.**

Para `trend_15m_v1`, aceitar sinais quantitativos Polymarket com spread de até 2 pontos percentuais, inclusive. Calcular por código com `Decimal`: `spread_pp = 100 * (best_ask - best_bid)`, usando preços normalizados de 0 a 1 e melhor bid/ask válidos do mesmo resultado/livro observado. Não confundir pp com percentual relativo ao preço ou arredondar previamente para liberar valor acima do limite.

Registrar pré-configuração `polymarket.max_spread_pp: "2.0"`, ajustável antes de nova sessão conforme D013, validada e persistida/restaurada com os demais parâmetros. Exemplos hipotéticos: `0.49`/`0.51` tem 2 pp, dentro do teto; `0.48`/`0.52` tem 4 pp, fora dele. Dados ausentes/inconsistentes não viram zero e continuam sujeitos a D020/D022.

Acima do teto, excluir o sinal quantitativo do contexto utilizável JEV com motivo, valores e parâmetro efetivo registrados. B/C usam o mesmo conjunto elegível. Preservar notícias válidas de outras fontes; rejeição não significa cenário neutro ou ausência de acontecimentos.

**Pendências:** mínimo de liquidez, atividade recente/profundidade e validação do acesso continuam em P011; comportamento de entradas sem cobertura em P012. O teto é experimental, sem calibração real ou recomendação numérica atribuída à plataforma. Spread baixo sozinho não comprova qualidade, sobretudo perto de probabilidades extremas, nem define chance de lucro.

**Justificativa:** limitar a diferença entre as melhores ofertas antes de usar uma expectativa como sinal quantitativo, com cálculo local e filtro auditável.

**Impactos:** SPEC 1.22, configuração, seção 5.10 e testes 16; fontes, contextos e pauta. Implementar no Marco 5 após completar P011/P012. Não altera cadência, orçamento JEV, risco, memória, finanças ou fase da TUI; nenhuma operação Polymarket é autorizada.

## D024 Liquidez reportada mínima Polymarket

**Aprovado pelo usuário em 11/10/2026, ao confirmar o mínimo proposto após D023. Origem: P011. Implementação/calibração e validação de unidade/metodologia: pendentes.**

Para `trend_15m_v1`, adotar mínimo experimental equivalente a US$ 10.000 de liquidez reportada por mercado individual, inclusive. Pré-configuração `polymarket.min_liquidity_usd: "10000.00"`, ajustável antes de nova sessão conforme D013, validada e persistida/restaurada. Comparar com `Decimal` somente após validar campo, unidade monetária/escala e significado na versão da API, sem arredondar para liberar valor abaixo do piso.

Não presumir contratos, agregados de evento ou colateral desconhecido como USD/USDT; conversão, quando necessária, exige taxa/fonte/horário explícitos e disponíveis antes da decisão. Não somar mercados, fontes ou campos alternativos para alcançar o mínimo. Guardar valor original, unidade/escala, contrato/fonte/mercado, observação/disponibilidade, valor normalizado verificável, parâmetro efetivo e motivo de rejeição.

Abaixo do mínimo, ou sem qualidade verificável conforme D020, excluir o sinal quantitativo do contexto utilizável JEV. B/C usam o mesmo conjunto elegível; notícias válidas de outras fontes permanecem. Não fabricar neutralidade ou probabilidade; efeito sobre entradas com cobertura parcial continua em P012.

Liquidez reportada, volume negociado em 24h e profundidade do livro são critérios distintos. Passar nesse piso não substitui spread/frescor/atividade/profundidade, não comprova participantes independentes nem vantagem preditiva. O valor é hipótese experimental da POC, não limite oficial/recomendação atribuída ao Polymarket.

**Pendências:** atividade/profundidade, unidade/metodologia e frescor específico da liquidez, dimensionamento e acesso real seguem P011; cobertura parcial segue P012. Cadências D022 permanecem; uma coleta recente de livro não renova automaticamente o dado de liquidez. Esta aprovação não define novo TTL ou frequência.

**Justificativa:** acrescentar um piso auditável por mercado ao filtro local, preservando a distinção entre métricas e seus significados.

**Impactos:** SPEC 1.23, configuração, seção 5.11 e testes 16; fontes, contextos e pauta. Implementar no Marco 5 após completar P011/P012. Orçamento JEV, finanças paper, memória e fase da TUI continuam conforme decisões anteriores; nenhuma integração real foi validada.

## D025 Volume mínimo Polymarket nas últimas 24h

**Aprovado pelo usuário em 11/10/2026, ao confirmar o mínimo proposto após D024. Origem: P011. Implementação/calibração e validação de unidade/metodologia: pendentes.**

Para `trend_15m_v1`, adotar mínimo experimental equivalente a US$ 1.000 negociados nas últimas 24 horas por mercado individual, inclusive. Pré-configuração `polymarket.min_volume_24h_usd: "1000.00"`, ajustável antes de nova sessão conforme D013 e persistida/restaurada. Comparar com `Decimal` somente após validar campo, unidade monetária/escala, significado e janela na versão da API, sem arredondar para liberar valor abaixo do piso.

Não usar volume acumulado ou agregado de evento, presumir contratos/colateral como USD/USDT, somar métricas alternativas/mercados ou duplicar negócios para atingir o mínimo. Conversões exigem origem/taxa/horário explícitos conforme D024. Preservar valor original/normalizado verificável, mercado/fonte/versão, unidade/escala, janela/instante de referência disponível, observação/disponibilidade, parâmetro efetivo e motivo de rejeição.

Abaixo do piso, excluir o sinal quantitativo do contexto utilizável JEV. Dado ausente/inválido/vencido ou sem unidade/semântica/janela verificável segue D020, sem inventar neutralidade. B/C usam o mesmo conjunto elegível e notícias válidas de outras fontes permanecem; efeito sobre novas entradas com cobertura parcial continua em P012.

Volume diário não comprova negócio recente nos últimos minutos, participantes independentes, profundidade ou frescor do preço. É um piso experimental da POC, sem calibração empírica ou recomendação numérica atribuída à plataforma.

**Pendências:** recência dos negócios, profundidade, unidade/metodologia, frescor específico de liquidez/volume, dimensionamento e acesso real seguem P011. Coleta recente de preço/livro não renova automaticamente métricas antigas ou desloca sua janela. Nenhuma nova cadência/TTL foi aprovada; preservar D022 e disponibilidade temporal.

**Justificativa:** complementar o piso de liquidez com atividade observada numa janela identificada, sem confundir medidas de qualidade.

**Impactos:** SPEC 1.24, configuração, seção 5.12 e testes 16; fontes, contextos e pauta. Implementar no Marco 5 após completar P011/P012. Orçamento JEV, finanças paper, memória e fase da TUI permanecem; nenhuma coleta ou integração real foi validada.

## D026 Recência dos negócios Polymarket

**Aprovado pelo usuário em 11/10/2026, ao confirmar a janela de 60 minutos proposta após D025. Origem: P011. Implementação/calibração e coleta real: pendentes.**

Para `trend_15m_v1`, exigir evidência de pelo menos um negócio válido do resultado selecionado nos últimos 60m, inclusive: `decision_started_at - 60m <= trade_event_at <= decision_started_at`, observado/validado e disponível antes da decisão. Pré-configuração `polymarket.max_trade_age_minutes: 60`, ajustável antes de nova sessão conforme D013 e persistida/restaurada. Validar mercado/resultado, horário/unidade/significado do timestamp, proveniência e cobertura da consulta pública. Preço de último negócio sem horário, metadados/cache ou HTTP recente não comprovam recência. Sem evidência verificável, excluir sinal quantitativo com motivo e mesmo conjunto B/C, preservando notícias válidas; consulta incompleta/indisponível sem comprovação é qualidade não verificável, sem afirmar ausência de negócios. Guardar identidade do negócio, tempos original/normalizado e de observação/disponibilidade, idade, parâmetro e motivo; releitura/restart não rejuvenescem negócio e informação posterior não completa decisão passada. Rejeitar timestamp futuro/inconsistente e não presumir o primeiro registro como mais recente sem validar ordenação. Negócio 60m, cache 10m e volume 24h são critérios distintos; um negócio não comprova fluxo expressivo, pessoas independentes, profundidade ou vantagem preditiva. Limite experimental, sem calibração empírica/oficial; profundidade, frescor das métricas, contrato temporal, dimensionamento e acesso seguem P011, cobertura parcial P012. Coleta pública somente de leitura, sem JEV por negócio ou mudança de cadências; orçamento, risco e memória permanecem.

**Justificativa:** exigir evidência temporal de atividade além do volume diário, distinguindo negócio observado de atualização do cache.

**Impactos:** SPEC 1.25, configuração, seção 5.13 e testes 16; fontes, contextos e pauta. Implementar no Marco 5 após completar P011/P012. Nenhuma integração real foi validada; finanças paper e fase da TUI permanecem conforme contrato.

## D027 Profundidade perto do preço Polymarket

**Aprovado pelo usuário em 11/10/2026, ao confirmar os pisos por lado e a faixa em torno do midpoint propostos após D026. Origem: P011. Implementação/calibração e coleta real: pendentes.**

Para `trend_15m_v1`, exigir equivalente a pelo menos US$ 1.000 em ofertas de compra e US$ 1.000 em ofertas de venda, separadamente, no livro do mesmo resultado selecionado, dentro de 2 pontos percentuais do ponto médio entre melhor bid/ask.

Pré-configuração `polymarket.min_depth_per_side_usd: "1000.00"` e `polymarket.depth_band_pp: "2.0"`, ajustável antes de nova sessão e persistida/restaurada conforme D013.

Com preços de 0 a 1, `mid = (best_bid + best_ask) / 2`; incluir bids em `[max(0, mid - 0.02), mid]` e asks em `[mid, min(1, mid + 0.02)]`, limites e piso inclusivos. A banda total pode ter 4 pp e é distinta do spread máximo de 2 pp D023. Exemplo hipotético mid 0.50: compras entre 0.48 e 0.50 e vendas entre 0.50 e 0.52.

Derivar melhor bid/ask pelos preços válidos do livro, sem presumir posição nos arrays; validar consistência antes do midpoint. Somar por lado o valor monetário validado `price * size` dos níveis elegíveis com `Decimal`, após verificar unidade/escala/significado de preços, quantidades e colateral e qualquer conversão conforme D024. Não somar lados, resultados/mercados ou snapshots, nem duplicar níveis para atingir o piso.

Livro inválido/vencido, incompleto sem cobertura verificável da banda ou unidade não verificável segue D020; abaixo do piso em qualquer lado, excluir sinal quantitativo com motivo, mesmo conjunto B/C e notícias válidas, sem neutralidade inventada.

Preservar origem/horários/hash quando disponível, níveis, limites/valores calculados por lado e parâmetros efetivos disponíveis antes da decisão. Releitura/restart não rejuvenescem livro e coleta posterior não completa decisão passada. Frescor do livro segue D022.

Valores experimentais ajustáveis antes da sessão conforme D013, sem calibração empírica/oficial; ofertas podem mudar, sem comprovar negócio executado, pessoas independentes ou vantagem preditiva. Demais filtros D020/D022–D026 permanecem. Frescor específico de liquidez/volume, unidade/metodologia, dimensionamento e acesso seguem P011, cobertura parcial P012. Cálculo local e coleta pública somente de leitura, sem JEV por atualização nem mudança de cadências.

**Justificativa:** exigir ofertas próximas ao preço em ambos os lados, complementando liquidez reportada e atividade negociada com uma medida distinta e auditável.

**Impactos:** SPEC 1.26, configuração, seção 5.14 e testes 16; fontes, contextos e pauta. Implementar no Marco 5 após completar P011/P012. Orçamento JEV, finanças paper, memória e fase da TUI permanecem.

## D028 Frescor dos dados de liquidez e volume Polymarket

**Aprovado pelo usuário em 11/10/2026, ao confirmar validade de 75 minutos para liquidez e volume após D027. Origem: P011. Implementação/calibração e coleta real: pendentes.**

- Para `trend_15m_v1`, usar `polymarket.liquidity_max_age_minutes: 75` e `polymarket.volume_24h_max_age_minutes: 75`. Manter descoberta/metadados na inicialização e a cada 60m D022; os 15m adicionais são tolerância operacional experimental de um candle, sem calibração ou recomendação oficial.
- Calcular idade separadamente para cada métrica a partir da última observação pública bem-sucedida e validada: `0 <= decision_started_at - metric_observed_at <= limite efetivo`. Exatamente 75m satisfaz o critério inicial; acima dele não. Observação/validação e disponibilidade precisam preceder a decisão. Não completar snapshots passados com dados posteriores.
- Consulta falha, releitura/restart ou atualização apenas de preço/livro/outro campo não renovam a observação da métrica. Um livro elegível por D022 não torna liquidez/volume antigos elegíveis. Preços/livros permanecem com teto próprio de 10m.
- Preservar valor/unidade/mercado, origem/versão do contrato, instante/janela de referência da fonte quando disponível, observação/disponibilidade, idade calculada, limite efetivo, status e motivo. Não deslocar volume antigo para uma janela encerrada agora nem fabricar timestamp pelo `updatedAt` ou HTTP recente. Rejeitar horário de observação futuro/inconsistente. O TTL local não comprova sozinho atualização na origem; validar significado temporal e atualidade pelo contrato do provedor conforme D020. Timestamp da fonte ausente fica explícito e exige qualidade verificável.
- Acima do teto, dado inválido/vencido ou qualidade não verificável: excluir o sinal quantitativo com motivo, mesmo conjunto B/C e notícias válidas, sem neutralidade inventada. Esta decisão não define bloquear/liberar entradas com cobertura parcial; completar P012. Demais pisos/filtros D023–D027 permanecem.
- Parâmetros experimentais ajustáveis antes de nova sessão conforme D013, persistidos/restaurados sem aplicar defaults novos a sessões antigas. Cálculo local, sem inferência JEV por coleta, mudança de cadências ou orçamento. Implementar no Marco 5 após completar P011/P012; unidade/metodologia, contratos temporais reais, dimensionamento e acesso seguem P011. Nenhuma integração/calibração real é comprovada por esta aprovação.

**Justificativa:** alinhar validade local das métricas à coleta horária com tolerância de um candle, distinguindo sua idade da idade do preço/livro e do tempo de negócio.

**Impactos:** SPEC 1.27, configuração, seção 5.15 e verificações requeridas na seção 16; fontes, contextos e pauta. Finanças paper, memória, orçamento JEV e fase da TUI permanecem.

## D029 Quantidade de mercados Polymarket acompanhados

**Aprovado pelo usuário em 11/10/2026, ao confirmar até 10 mercados por sessão após D028. Origem: P011. Implementação/calibração e coleta real: pendentes.**

- Para `trend_15m_v1`, usar `polymarket.max_tracked_markets: 10`: inteiro positivo e teto total de mercados individuais acompanhados por sessão, compartilhados B/C. Contar IDs de mercados únicos; duplicatas não ocupam vagas e vários mercados de um mesmo evento contam separadamente. Preservar identificação dos resultados consultados; dois resultados do mesmo mercado não são mercados independentes adicionais.
- Selecionar pela relevância para BTC/USDT D018 e qualidade verificável D020/D023–D028. Popularidade/volume sozinhos não bastam. Acompanhar menos que o teto quando faltarem candidatos adequados, sem preencher vagas artificialmente nem fabricar neutralidade. O teto não comprova dez acontecimentos/evidências independentes; agrupamento, ordenação/desempates e critérios semânticos detalhados seguem P011/P012.
- Rever o conjunto na inicialização e a cada 60m conforme D022. Aplicar aos mercados acompanhados cadências/frescor e filtros já aprovados. Persistir composição, IDs de mercado/resultado, origem, motivos e horários de inclusão/exclusão/disponibilidade; B/C recebem o mesmo snapshot existente no início da decisão. Revisões posteriores não alteram decisões passadas.
- Coleta/cálculo local e fatores resumidos com evidência curta seguem D002; acompanhar dez mercados não exige dez chamadas JEV ou envio de respostas brutas. Classificação semântica necessária continua contabilizada no orçamento global; esta decisão não escolhe quantidade de fatores no prompt, pesos ou nova cota de IA.
- Teto inicial experimental ajustável antes de nova sessão conforme D013, com configuração efetiva persistida/restaurada. Não define páginas/limite da descoberta, frequência do feed de negócios ou mecanismo de coordenação entre sessões; completar P011/P012/P015. A coleta de candidatos para seleção é distinta do conjunto acompanhado, com limites próprios ainda a definir.
- Implementar no Marco 5 após completar contratos; unidade/metodologia, validação temporal e acesso reais permanecem pendentes em P011. Cobertura parcial não define nova regra de entrada B/C (P012); nenhuma negociação Polymarket ou integração/calibração real é autorizada/comprovada por esta aprovação.

**Justificativa:** limitar capacidade de acompanhamento da POC, preservando relevância, qualidade e contexto resumido compartilhado B/C, sem confundir quantidade com confiança ou independência.

**Impactos:** SPEC 1.28, configuração, seção 5.16 e critérios da seção 16; fontes, contextos e pauta. Finanças paper, memória, orçamento JEV e fase da TUI permanecem.

## D030 — Suporte a outros ativos na V1, um par por sessão

**Estado:** aprovado pelo usuário em 11/10/2026. **Contexto:** a restrição a BTC compromete o objetivo de avaliar moedas diferentes; o usuário exige suporte desde a primeira versão.

**Decisão:** um par Spot configurável com cotação USDT por sessão; BTCUSDT é exemplo/default. Selecionar par/perfil antes de iniciar, validar símbolo/ativo/cotação/estado e filtros nos metadados públicos de leitura. Quantidades, posições, contabilidade, prompts, feeds e relatórios usam o ativo base efetivo, sem campos BTC ou precisão universal. Resolver incremento/mínimos por par com Decimal. Cada sessão mantém SQLite, trio A/B/C de 100 USDT e memória específica por símbolo. Na retomada, não trocar par/configuração ou reinicializar capital.

Notícias e Polymarket priorizam moeda/ecossistema destino; BTC/macro requer relação justificada. Chaves de cache/classificação incluem identidade/contexto do destino. Dados BTC importados em ETH ficam arquivados/inativos; transferência estatística continua P014. Mais moedas não aprovam vários pares dentro de uma sessão, novos estilos automáticos ou aumento de orçamento; coordenação simultânea continua P015. Paper-only/Spot/long-only, sem operações reais ou API privada, permanecem.

**Impactos:** SPEC 1.29/4.3, contratos financeiros e de dados, AGENTS e documentação de desenvolvimento/execução/TUI/perfis/dataset/fontes. Substitui restrições anteriores a BTC em D007/D008/D018 e nas revisões históricas, que ficam preservadas como histórico. Exigir testes offline ao menos BTCUSDT/ETHUSDT e isolamento de memória/cache; integração e implementação pendentes.

## D031 — Paginação limitada da descoberta Polymarket

**Estado:** aprovado pelo usuário em 11/10/2026 após esclarecimento sobre descoberta e correção do escopo de moedas.

**D031 — paginação da descoberta aprovada:** `polymarket.discovery_page_size: 100` e `polymarket.discovery_max_requests_per_refresh: 5`, inteiros positivos e parâmetros experimentais ajustáveis antes da sessão conforme D013. Em cada revisão inicial/60m, o total de requisições físicas de páginas inclui retries e buscas por todos os temas da sessão, sem multiplicar por B/C. Até 500 registros antes de deduplicação somente com cinco páginas completas e bem-sucedidas; acompanhar no máximo 10 mercados D029. Validar rota/versão, tamanho retornado e cursor; interromper repetição sem progresso e paginação automática ilimitada. Registrar parâmetros, páginas, tentativas, IDs, horários, término e cobertura parcial quando houver limite com resultados restantes, erro ou cobertura incerta. Resposta vazia não renova dados antigos nem comprova ausência global de mercados relevantes. Coleta/filtro local não exige JEV por página; classificação segue D002/P012 e orçamento vigente. Ordenação/desempates, distribuição por tema, contratos/acesso, feed de negócios e regra de entrada com cobertura parcial permanecem pendentes. Ver SPEC 5.17; integração não validada.

**Impactos:** SPEC 1.30/5.17, configuração, testes exigidos do Marco 5, fontes e contextos. P011 prossegue para ordenação/priorização dos candidatos, contratos/unidades/acesso; P012 mantém agrupamento/fatores e entradas com cobertura parcial. A aprovação não comprova acesso automático nem eficácia/calibração dos limites.

## D032 — Prioridade dos candidatos Polymarket

**Estado:** aprovado pelo usuário em 11/10/2026, após a proposta de ordem geral de seleção em P011.

**Decisão:** aplicar filtros obrigatórios de qualidade antes de selecionar. Entre elegíveis, priorizar relação com a moeda/ecossistema, depois relação com a janela da estratégia e, entre relevâncias semelhantes, qualidade observável: dados mais recentes, spread menor e profundidade verificável. Eventos distantes podem fornecer contexto D019; popularidade não substitui relevância e proximidade não significa maior confiança ou lucro.

Identificar mercados sobre o mesmo acontecimento para evitar concentração e falsa independência, mantendo IDs/perguntas/resultados e contagem D029. Não somar probabilidades/confiança ou fundir preços por agrupamento. Classificação semântica reutiliza D002 e cache compatível; ordenação numérica é local, sem JEV obrigatório por revisão. Mesma seleção B/C e informações disponíveis antes do cutoff.

**Limites da aprovação:** critérios concretos de relevância/horizonte, pesos/desempates, método de agrupamento e distribuição das vagas serão detalhados em P011/P012. Não foi aprovada quantidade por acontecimento, categoria ou prompt, novo orçamento ou regra de entrada parcial. Memória estatística, risco, cadências, paginação D031 e máximo de dez mercados D029 permanecem.

**Impactos:** SPEC 1.31/5.18, testes exigidos do Marco 5, fontes, pauta e contextos de desenvolvimento/execução/TUI. P011 prossegue para distribuição das vagas entre acontecimentos. Implementação, integração e eficácia não validadas.

## D033 — Até dois mercados Polymarket por acontecimento

**Estado:** aprovado pelo usuário em 11/10/2026 após explicação com perguntas sobre uma atualização fictícia do Ethereum.

**Decisão:** para o perfil inicial, limitar a dois mercados individuais acompanhados sobre o mesmo acontecimento, dentro do teto total de dez por sessão, com mesma seleção B/C. Favorecer acontecimentos distintos relevantes à moeda/estratégia D032 e manter filtros de qualidade. Não fixar quotas obrigatórias por categoria ou completar vagas com candidatos inadequados; menos de dez é válido.

Pré-configuração `polymarket.max_markets_per_occurrence: 2`, inteiro positivo e valor experimental ajustável antes de nova sessão D013, persistido/restaurado com a configuração efetiva. Mercados contam individualmente D029; Sim/Não da mesma pergunta não são dois mercados adicionais. Manter IDs, evidências, agrupamento/versão e motivo de exclusão por teto. Duas perguntas sobre um acontecimento não confirmam informação independentemente; não somar probabilidades/confiança.

**Limites da aprovação:** método de agrupamento, identificação incerta e escolha exata dos representantes continuam em P011/P012. Não inventar grupos distintos nem supor independência para contornar o limite. A restrição se refere ao acompanhamento Polymarket; não limita moedas/perfis, amplia orçamento ou muda cadência, memória, risco ou política de entradas parciais.

**Impactos:** SPEC 1.32/5.19, configuração, testes exigidos do Marco 5, fontes/pauta e contextos de desenvolvimento/execução/TUI. P011 prossegue para identificar mercados sobre o mesmo acontecimento, depois critérios exatos de seleção/desempate, contratos e acesso. Implementação, integração e calibração pendentes.

## D034 — Identificação dos acontecimentos Polymarket

**Estado:** aprovado pelo usuário em 11/10/2026; proxy autorizado para consultar documentação quando necessário.

**Decisão:** usar grupos/identificadores de eventos do Polymarket como referência inicial e conferir pergunta/regras, objeto e período do acontecimento. Mesmo tema/moeda/tag não comprova identidade; IDs distintos não provam independência. Perguntas da mesma atualização Ethereum podem compartilhar acontecimento; atualizações distintas não são fundidas apenas por envolverem Ethereum. Data de resolução não substitui data do acontecimento D019.

Relação incerta fica explícita, sem grupo/independência inventados. A ação operacional para tais candidatos permanece em P011/P012. Guardar IDs, evidências, status, critérios/versões e disponibilidade, mesma associação B/C, sem reescrever seleções passadas. Reuso local/persistido e interpretação JEV necessária seguem D002 e orçamento vigente, sem inferência obrigatória a cada revisão. Teto D033 é aplicado ao agrupamento verificado; não muda memória, risco, cadência ou política de entradas parciais.

**Validação pontual de acesso:** documentação e uma consulta Gamma pública retornaram HTTP 200 via proxy; detalhes em FONTES_DE_CONTEXTO.md. Proxy fornecido pelo usuário foi usado somente em leitura, sem versionar endereço/autenticação ou inserir credenciais em resultados. Essa validação não inclui CLOB/livros, feed de negócios, estabilidade contínua ou integração do bot.

**Impactos:** SPEC 1.33/5.20, testes exigidos do Marco 5, fontes/pauta e contextos. Próximo ponto P011: tratamento operacional da identificação incerta; critérios exatos de seleção/desempate e contratos/acesso restantes continuam pendentes. Implementação e eficácia não validadas.

## D035 — Perguntas com acontecimento incerto ficam pendentes

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** guardar pergunta/dados/dúvida para auditoria, mas deixar candidato com associação não verificável fora dos mercados acompanhados e dos fatores Polymarket utilizáveis até confirmação. Pendente não ocupa vaga e não recebe grupo único fictício para contornar o teto D033. Quando a identificação estiver disponível, reconsiderar na revisão prevista D022, com relevância/filtros/frescor/tetos válidos, sem alterar decisões passadas.

B/C usam a mesma base e pendências/cobertura explícitas; outros mercados e notícias válidos permanecem disponíveis. Classificação/reuso seguem D002 e orçamento vigente, sem JEV obrigatório por candle/revisão. Falta de orçamento ou falha não autoriza fabricar associação. Persistir status, motivo, evidências, IDs e horários, com retomada sem promoção automática.

**Limites:** trata associação incerta ao acontecimento; prazo incerto isolado continua D019. Confirmação permite reavaliar, não garante inclusão. Liberar/bloquear entradas com cobertura parcial continua em P012. Critérios exatos/desempates, contratos e validação operacionais permanecem pendentes; não muda orçamento, cadências, memória ou risco.

**Impactos:** SPEC 1.34/5.21, testes exigidos do Marco 5, fontes/pauta e contextos. P011 segue para desempate de qualidade entre candidatos semelhantes. Implementação, integração contínua e eficácia não validadas.

## D036 — Ordem de desempate por qualidade

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** depois dos filtros obrigatórios, identificação e prioridade geral, entre candidatos com relevância/horizonte equivalentes, preferir snapshot de preço/livro validado mais recente; em igualdade, menor spread em pp; persistindo empate, maior profundidade monetária no lado menos abastecido (`min(bid_depth_usd, ask_depth_usd)` na banda D027); empate completo usa ID de mercado em ordem textual estável.

Comparar localmente valores verificáveis/Decimal e tempos normalizados no mesmo instante de revisão, preservando origem/atualidade da fonte D020/D022. Metadados/releitura/restart não rejuvenescem snapshot; números ausentes/invalidade não ganham prioridade por zero inventado. Não usar score ponderado, sorteio, ordem da API ou resultados das carteiras. Preservar valores, IDs/grupos, evidências/versões/horários/motivos, tetos D029/D033, mesmo conjunto B/C e histórico.

**Limites:** critérios semânticos que definem equivalência/relevância/horizonte serão completados em P011/P012. Ordenação numérica não acrescenta chamadas JEV ou parâmetros numéricos; não muda orçamento, risco, cadência, memória ou entradas parciais. A ordem é política de seleção, sem eficácia/calibração demonstradas.

**Impactos:** SPEC 1.35/5.22, testes exigidos do Marco 5, fontes/pauta e contextos. Próximo ponto: critérios de relevância para o ativo no contexto da seleção, articulados com P012; contratos/acesso/dimensionamento restantes de P011 continuam abertos. Implementação pendente.

## D037 — Quatro classes de relevância para a moeda da sessão

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** classificar notícias/mercados por ativo destino em direta (`DIRECT`), contextual com ligação justificada (`CONTEXTUAL`), sem relevância (`NOT_RELEVANT`) e indeterminada por falta de dados/evidência (`UNDETERMINED`). Direta precede contextual na seleção, mantendo filtros/tempo/tetos. Informação sem relevância fica fora do contexto utilizável com motivo; indeterminada fica pendente fora dele até esclarecimento, sem apagar observação/auditoria ou inventar neutralidade.

Relevância permanece separada de impacto, qualidade e confiança D002. Preservar classe/motivo/evidência, origem/hash, ativo, critérios/modelo/versões e disponibilidade; mesma versão B/C, sem reutilizar interpretação de outra moeda automaticamente. Processar novo/alterado e reusar classificação válida, sem JEV por candle ou aumento de orçamento. Confirmação/reprocessamento não reescrevem decisões passadas; seleção Polymarket respeita revisão D022.

**Limites:** classe direta não comprova fonte, lucro ou entrada elegível. Dúvida de relevância é distinta da associação ao acontecimento D035 e do prazo D019. Fonte indisponível, coleta válida sem item relevante e classificação pendente são estados distintos. Demais fatores, validade/reprocessamento/falhas, critérios temporais e entradas com cobertura parcial seguem P012; contratos/dimensionamento/acesso restantes de P011 continuam abertos.

**Impactos:** SPEC 1.36/5.23, testes exigidos do Marco 5, fontes/pauta e contextos de desenvolvimento/execução/TUI. Próximo ponto: relação temporal com o perfil, preservando D019. Configuração numérica, memória estatística, risco e cadências mantidos; implementação e validação semântica pendentes.

## D038 — Três grupos temporais relativos à estratégia

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** classificar relação temporal separadamente da relevância em na janela (`IN_OPERATION_WINDOW`), contexto fora dela (`BACKGROUND`, inclusive informação relevante de fato já ocorrido) e momento desconhecido (`TIMING_UNKNOWN`). Acontecimento na janela tem prioridade entre itens de mesma relevância; contexto e momento desconhecido não são descartados automaticamente por esse motivo isolado, mantendo demais filtros.

A janela de referência é a duração operacional do perfil efetivo, no inicial máximo nominal de 16 candles (~4h), distinta de candle 15m/lookback 24h/resolução/labels. Referência externa comum B/C; estado próprio e risco preservam tempo restante das posições. Separar data do acontecimento e resolução D019, com evidência e incerteza explícitas, sem afirmar ocorrência por intervalo amplo/data ausente.

Guardar extração/evidência/versões/tempos disponíveis e derivar relação localmente por relógio/perfil quando verificável, reutilizando D002 sem JEV por candle. Mudança posterior não altera decisões passadas ou renova dados antigos; composição Polymarket continua na revisão D022.

**Limites:** critérios exatos de intervalos/ambiguidade, validade/reprocessamento, demais fatores e entradas parciais seguem P012. Não foi definida ordem adicional entre contexto/momento desconhecido nem confiança por proximidade. Não muda orçamento/cadências, duração/labels/risco/memória ou TUI.

**Impactos:** SPEC 1.37/5.24, testes exigidos do Marco 5, pauta/fontes e contextos. Próximo ponto P012: impacto potencial. P011 mantém contratos/acesso/dimensionamento pendentes. Implementação e validação semântica pendentes.

## D039 — Cinco classes de direção do impacto potencial

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** classificar direção hipotética para o ativo destino em favorável (`POSITIVE`), desfavorável (`NEGATIVE`), mista (`MIXED`), neutra (`NEUTRAL`) ou indeterminada (`UNDETERMINED`), com justificativa/evidência. Mista contém efeitos favoráveis/desfavoráveis identificáveis, sem média inventada; neutra pressupõe análise válida sem efeito direcional pelos critérios; indeterminada é insuficiência de evidência. Ausência/falha/dúvida/cobertura parcial não é sinal neutro.

Separar direção de relevância, relação temporal, intensidade, qualidade e confiança D002. Não confirma fato/causalidade, previsão/retorno ou probabilidade de preço; probabilidade Polymarket continua relativa à pergunta do acontecimento. Sentimento do fornecedor não substitui a classificação. Classe não aciona BUY/SELL/veto ou mudança de risco automaticamente.

Guardar ativo/perfil, classe/motivo/evidência, fonte/hash, critérios/modelo/versões e disponibilidade, mesma base B/C. Classificar/reusar D002 sem JEV por campo/candle, sem orçamento/cadências novos ou alterações retroativas.

**Limites:** apenas direção aprovada. Intensidade/confiança/validade/falhas/conflitos e uso operacional de impacto indeterminado/entradas parciais continuam P012. Não herdar para impacto desconhecido regras de exclusão de relevância/associação; demais filtros/tetos e regras financeiras permanecem.

**Impactos:** SPEC 1.38/5.25, testes exigidos do Marco 5, fontes/pauta e contextos. Próximo ponto P012: intensidade do impacto, separada de confiança. Configuração numérica, memória e TUI preservadas; implementação/validação semântica pendentes.

## D040 — Quatro classes qualitativas de intensidade

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** classificar intensidade hipotética para o ativo/perfil em baixa (`LOW`), moderada (`MODERATE`), alta (`HIGH`) ou indeterminada (`UNDETERMINED`), com justificativa/evidência. Baixa = efeito limitado; moderada = alcance intermediário relevante; alta = possível impacto amplo/risco significativo; indeterminada = evidência insuficiente para avaliar alcance.

Separar intensidade de direção/relevância/tempo/confiança/qualidade D002. Intensidade alta pode coexistir com baixa confiança nessa avaliação, sem confirmar verdade/ocorrência do relato. Não representa percentual de preço/retorno ou probabilidade, e ausência/falha não vira baixa/zero. Direção neutra/mista não determina magnitude automaticamente.

Não altera posição/stop/risco/orçamento, cria veto ou score composto. Guardar classe/motivo/evidência/destino/perfil/versões/tempos, mesma base B/C; classificar/reusar D002 sem JEV por campo/candle ou alteração retroativa.

**Limites:** apenas taxonomia qualitativa aprovada. Critérios de alcance, confiança/qualidade/validade/conflitos/falhas e combinações/uso operacional de impacto indeterminado/entradas parciais continuam P012; não herdar exclusão de outro campo. Demais filtros/tetos, configuração numérica, memória e TUI preservados.

**Impactos:** SPEC 1.39/5.26, testes exigidos do Marco 5, fontes/pauta e contextos. Próximo ponto P012: confiança da classificação, distinta de qualidade/verdade da fonte. Implementação e validação semântica pendentes.

## D041 — Quatro classes de confiança da classificação

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** registrar confiança qualitativa na interpretação semântica em alta (`HIGH`), moderada (`MODERATE`), baixa (`LOW`) ou indeterminada (`UNDETERMINED`). Alta: clara e bem sustentada; moderada: justificável com limitações; baixa: categoria incerta por ambiguidade/detalhes faltantes; indeterminada: não foi possível avaliar confiança. Guardar motivo/evidência e objeto da classificação, separados de qualidade da fonte, direção/intensidade/relevância/tempo.

Confiança não confirma verdade/ocorrência, probabilidade Polymarket ou chance de lucro. Pode haver alta confiança na classificação de impacto indeterminado quando a falta de evidência é clara; outro campo desconhecido não obriga confiança baixa.

Preservar `confidence` numérico bruto retornado pelo JEV quando disponível, com vínculo à resposta/pergunta/modelo/versões. Ausência não vira zero; não converter automaticamente números em classes por limiares inventados, fabricar números a partir das classes ou presumir probabilidade calibrada.

Classificar/reusar D002 no mesmo processamento, mesma base B/C, com destino/perfil, evidência, versões/tempos/cutoff e auditoria; sem JEV por campo/candle ou alteração retroativa. Sem transferir thresholds BUY/SELL para classificação, criar score/veto ou alterar risco/posição.

**Limites:** referências de avaliação, eventual mapeamento numérico, qualidade/validade/reprocessamento/conflitos/falhas e tratamento operacional de baixa/indeterminada/entradas parciais continuam P012. Cadências, configuração numérica, orçamento e regras financeiras preservados.

**Impactos:** SPEC 1.40/5.27, requisitos de testes do Marco 5, fontes/pauta e contextos de desenvolvimento, execução e TUI. Próximo ponto P012: qualidade da informação e da fonte. Implementação e validação semântica pendentes.

## D042 — Três classes de qualidade observável da informação e da fonte

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** registrar qualidade suficiente (`SUFFICIENT`: origem identificável/evidência adequada), parcial (`PARTIAL`: informação disponível com limitações explícitas) ou não verificável (`UNVERIFIABLE`: dados insuficientes para avaliar qualidade). Guardar motivo/limitações e evidências observáveis, separados da confiança D041, impacto e probabilidade Polymarket.

Examinar origem/link, datas e evidência disponível, distinguindo relato/hipótese/rumor. Registrar corroboradores independentes identificáveis, republicações da mesma origem, correções e conflitos quando disponíveis. Não exigir duas fontes por item ou somar confiança por republicação; ausência de corroboração não prova falsidade. Origem oficial ou API disponível não garante verdade.

Manter filtros quantitativos Polymarket D020/D023–D028: qualidade documental não libera livro/preço inelegível. Verificações de dados locais e registro de evidência no processamento/reuso D002, sem chamada adicional apenas por campo/candle. Mesma base B/C, proveniência/versões/tempos/cutoff e auditoria, sem revisão retroativa ou promoção por restart.

**Limites:** classes e verificações gerais aprovadas; não são selo de verdade, probabilidade calibrada ou score composto. Critérios mínimos por fonte, validade/reprocessamento/conflitos/falhas e uso operacional de parcial/não verificável/entradas parciais seguem P012. Sem novos thresholds/vetos/pesos/risco, cadências, parâmetros numéricos ou orçamento.

**Impactos:** SPEC 1.41/5.28, requisitos de testes do Marco 5, fontes/pauta e contextos de desenvolvimento, execução e TUI. Próximo ponto P012: validade e reprocessamento das classificações. Implementação e validação semântica pendentes.

## D043 — Reutilização e reprocessamento das classificações

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** reutilizar interpretação concluída enquanto conteúdo/evidências, ativo/perfil e critérios/versões permanecerem compatíveis e fontes elegíveis. Reprocessar correção, informação/evidência relevante nova ou mudança de critérios que afete interpretação; preservar histórico com motivo, conteúdo/versões e disponibilidade da nova classificação. Sem revisão de decisões/snapshots passados.

Atualizar números Polymarket e relação temporal derivável de datas verificadas localmente, sem JEV apenas por consulta/candle ou expiração diária arbitrária da interpretação. Manter idade máxima de notícias 24h, preços/livros 10m e liquidez/volume 75m, separadamente e com demais filtros; esses prazos não são TTL universal da classificação. Releitura/restart/reprocessamento não renovam datas/prazos da fonte.

Versão invalidada/incompatível não substitui classificação pendente/falha; registrar estado/motivo sem fabricar neutralidade/confiança/qualidade/índices. Mesma versão disponível antes do cutoff em B/C, reuso D002 e orçamento global preservados. Respeitar configuração imutável D013 e histórico ao restaurar.

**Limites:** regra geral aprovada; contratos adicionais por fator, detecção detalhada de alterações/compatibilidade, tratamento de conflitos/correções/falhas e política de contexto parcial/orçamento/entradas seguem P012. Não define novo veto/peso, TTL numérico ou aumento de orçamento.

**Impactos:** SPEC 1.42/5.29, requisitos de testes do Marco 5, fontes/pauta e contextos de desenvolvimento, execução e TUI. Próximo ponto P012: informações conflitantes e correções. Implementação e validação pendentes.

## D044 — Informações conflitantes e correções

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** preservar relatos/fontes/origens/datas/evidências/versões e registrar divergência sobre o mesmo fato/período. Não escolher verdade por maioria/republicações, popularidade, ordem de chegada ou confiança JEV. Comparar Polymarket pela proposição/prazo: expectativa negociada não confirma fato.

Correção identificável da origem vinculada ao relato corrigido aciona reprocessamento D043, com nova interpretação disponível para decisões futuras; preservar versão anterior/auditoria e datas da fonte. Relato mais novo não é correção automática.

Manter indicação curta da divergência/evidências ao JEV, fatores separados e mesma base B/C dentro de tetos/cutoff; sem média ou soma de confiança/probabilidades. Conflito factual não é impacto mista automático D039; evidência insuficiente para direção mantém indeterminação/motivo. Reavaliação D002/D043 no orçamento, sem inferência por campo/candle ou reuso de versão invalidada.

**Limites:** tratamento geral aprovado; critérios detalhados de associação/conflito/correção, prioridade entre evidências e efeitos operacionais de conflito/parcial/indeterminado sobre entradas seguem P012. Sem novo veto/peso/threshold, cadência, risco ou orçamento.

**Impactos:** SPEC 1.43/5.30, requisitos de testes do Marco 5, fontes/pauta e contextos de desenvolvimento, execução e TUI. Próximo ponto P012: falhas de fontes e classificações; depois efeitos das limitações sobre novas entradas. Implementação e validação pendentes.

## D045 — Falhas de fontes e classificações

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** isolar falha por fonte/item com motivo/disponibilidade, distinguindo erro, vencimento, falta de cobertura, coleta válida sem item relevante, cota/orçamento esgotado e processamento pendente. Falha Marketaux permite aproveitar RSS/dados anteriores ainda válidos D016/D043; falha Polymarket não apaga notícias elegíveis.

Manter fatores com dados/classificação válidos e compatíveis antes do cutoff e mesma base/status B/C, com limitação explícita. Classificação falha fica indisponível; não enviar item bruto como substituto, fabricar fatores/neutralidade/confiança/qualidade, renovar TTL ou reutilizar versão invalidada. Recuperação segue cadências/contratos da integração e reprocessamento D043; JEV mantém D005/8.3, propósito/custo/orçamento vigentes, sem chamadas extras por campo/candle.

Falha da decisão final JEV impede nova compra e mantém HOLD seguro; cotação sem frescor/validade também impede abertura. Gerenciamento/saídas de risco continuam com cotação válida e precedências, sem fechamento compulsório apenas por falha isolada de contexto. Preservar estados/tentativas/histórico na retomada.

**Limites:** preservação/diagnóstico geral aprovados; critérios adicionais de estados/recuperação e permitir/bloquear compras B/C com contexto externo parcial/conflitante/ausente/limitado continuam P012. Sem novo orçamento/cadência, limite de tentativas das fontes ou veto de entrada parcial por esta decisão.

**Impactos:** SPEC 1.44/5.31, requisitos de testes do Marco 5, fontes/pauta e contextos de desenvolvimento, execução e TUI. Próximo ponto P012: novas compras com contexto parcial, conflitante ou ausente. Implementação e validação pendentes.

## D046 — Política geral de novas compras com contexto limitado

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** B/C podem avaliar compra quando uma fonte falhar e outra fornecer fatores relevantes válidos/classificados, com limitação explícita. Coletas válidas sem notícia/mercado relevante permitem avaliação pelos demais dados com ausência de cobertura explícita. Não exigir notícias e Polymarket simultaneamente para toda moeda nem fabricar neutralidade; falha/descoberta truncada não prova ausência.

Sem fator externo utilizável devido a falha, vencimento, orçamento ou classificação pendente, bloquear nova compra B/C e registrar HOLD/motivo. Conflito relevante não resolvido sobre evidência que fundamentaria a entrada também bloqueia compra afetada; expectativa Polymarket não é conflito factual automático D044.

Permissão de avaliação sempre exige dados técnicos/mercado/cotação fresca, resposta final JEV válida pelos thresholds vigentes e liberação do Risk Engine. Mesmos fatores/status B/C, decisões/finanças próprias. A permanece técnica; posições existentes mantêm SELL válido/saídas de risco com cotação válida, sem liquidação apenas por limitação de contexto.

**Limites:** política geral aprovada; mínimos de cobertura/ausência verificável, conflito relevante/fundamento e combinação de campos limitados permanecem P012. Classe baixa/indeterminada/parcial não cria veto isolado automático. Sem novos pesos/thresholds, alteração de risco/cadências/orçamento ou transferência de memória entre ativos.

**Impactos:** SPEC 1.45/5.32, requisitos de testes do Marco 5, fontes/pauta e contextos de desenvolvimento, execução e TUI. Próximo ponto P012: critérios de conflito relevante para a entrada. Implementação e validação pendentes.

## D047 — Três critérios conjuntos de conflito relevante para a entrada

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** bloquear compra afetada D046 quando coexistirem divergência factual não esclarecida sobre mesmo fato/período D044, ligação direta ou contextual justificada ao ativo/perfil e dependência da compra em assumir correta uma das versões contestadas.

Guardar fontes/IDs/evidências, vínculo ao fundamento da decisão, motivo/versões/disponibilidade. Mesma sinalização externa B/C com aplicação por decisão/carteira. Divergência sem relação ao fundamento permanece registrada, sem esse bloqueio automático; demais gates e risco continuam. Exemplo fictício: compra por atualização de rede supostamente ativada enquanto outro relato do mesmo fato/período afirma adiamento.

Preservar posições/SELL válido/saídas de risco, histórico/cutoff e reuso D002/D043; sem inferência extra por campo/candle, soma de confiança, peso ou ajuste financeiro.

**Limites:** contrato estruturado de fundamento/evidências, validação de vínculo/independência e casos ambíguos permanecem P012. Vínculo não avaliável não prova fundamento independente ou permite compra automaticamente. Critérios de cobertura/ausência e combinação de campos limitados continuam pendentes.

**Impactos:** SPEC 1.46/5.33, requisitos de testes do Marco 5, pauta/fontes/contextos. Próximo ponto P012: cobertura utilizável e ausência de itens relevantes. Implementação e validação pendentes.

## D048 — Cobertura utilizável e ausência de itens relevantes

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** distinguir cobertura utilizável, nenhum item relevante encontrado e cobertura não avaliável ou parcial. Cobertura utilizável exige pelo menos um fator de notícia ou Polymarket relevante ao ativo/perfil, com dados elegíveis, classificação válida/compatível e disponibilidade antes do cutoff. API saudável ou itens brutos não bastam.

Nenhum item relevante encontrado pressupõe coleta/análise concluídas corretamente no recorte configurado de moeda/temas/período, com consultas/filtros/horários/contagens/motivo registrados; zero nesse recorte não prova ausência em todas as fontes. Erro, dado vencido, pendência, cota/orçamento ou retorno/paginação truncados são limitação, não ausência comprovada.

Preservar estados por fonte/recorte e fatores ainda válidos mesmo com cobertura parcial D045/D046; mesma base B/C e disponibilidade/histórico. Mínimo de um fator é de cobertura, não autoriza compra nem prova independência/verdade/retorno. Tetos/cadências, verificação local e reuso D002/D043 preservados, sem confirmação obrigatória em duas fontes ou contexto artificial.

**Limites:** critérios temporais de coleta vazia, escopo suficiente/composição de estados e combinação de qualidade/confiança continuam P010/P011/P012; não cria TTL de resposta vazia, orçamento ou cadência novos. Critérios de relevância/qualidade/classificação e demais gates continuam obrigatórios.

**Impactos:** SPEC 1.47/5.34, requisitos de testes do Marco 5, pauta/fontes/contextos. Próximo ponto P012: fatores com baixa confiança, qualidade parcial ou impacto indeterminado. Implementação e validação pendentes.

## D049 — Fatores com limitações e proporcionalidade à POC

**Estado:** aprovado pelo usuário em 11/10/2026.

**Decisão:** confiança baixa/indeterminada entra como contexto auxiliar; compra exige fundamento verificável independente da interpretação incerta. Qualidade parcial complementa se dados essenciais forem elegíveis; não verificável fica registrada sem contar para cobertura D048 até haver evidência necessária. Direção/intensidade indeterminadas ficam desconhecidas, sem favorecer/neutrar a informação ou remover automaticamente fator com relevância/origem/dados válidos. Rótulo isolado não cria veto; premissa não verificável e gates de conflito/dados/risco permanecem.

**Orientação de escopo:** o usuário pediu proporcionalidade à POC e questionou a sequência excessiva de aprovações. Encerrar a discussão incremental de P012; detalhes técnicos rotineiros serão resolvidos na implementação, com soluções simples, documentadas/testadas. Consultar apenas escolhas que alterem objetivo, escopo ou comportamento material; preservar requisitos aprovados, testes críticos e TUI por último.

**Impactos:** SPEC 1.48/5.35, pauta e contextos atualizados. P012 encerrado para discussão; implementação, validação técnica e integrações continuam pendentes. Não altera orçamento, cadências, configuração numérica, papéis A/B/C ou limites financeiros.

## D050 — Fechamento documental da POC V1

**Estado:** consolidação solicitada pelo usuário após arquitetura/Docker e referência visual da TUI, em 11/10/2026. Documentação fechada; software/integração/homologação pendentes.

**Escopo:** preservar D001–D049; perfil inicial trend_15m_v1 e par Spot USDT por sessão, A/B/C independentes, fontes públicas e memória local amadurecida/dataset opcional. Hexagonal/motor Docker/SQLite por sessão, HTTP/TUI terminal após Marcos 1–5, sem HTML ou execução real.

**Escolhas técnicas iniciais de consolidação pelo agente sob D049:** Textual; consultas HTTP no motor; criação/restauração pelo backend/CLI acionado por adaptador Docker local; orçamento global SQLite operacional com reservas/tentativas idempotentes, sem subcotas fixas ou aumento dos limites. Validar concorrência/retomada antes do paralelo; não apresentar como aprovações anteriores de mecanismos/subcotas.

**Destinação:** P001–P013/P015/P016 passam a desenho fechado e trabalho técnico/aceite no backlog. P008 reporta dependência sem pesos/mínimos novos; outros estilos e transferência automática P014 são evolução. Não inventar segundo perfil ou misturar estatísticas. Detalhes rotineiros serão resolvidos/testados, sem microaprovações; explicitar mudanças materiais de escopo/experimento/custo.

**Impactos:** SPEC 1.49/8.2.1/15.4, escopo/backlog/índice, arquitetura/TUI e contextos alinhados. Fechar docs não declara testes do aplicativo, operação 24h, implementação ou lucratividade.

## D051 — TUI remota com REST e WebSocket

**Estado:** aprovado pelo usuário em 12/10/2026, após discutir core hospedado/token/2FA.

**Decisão:** REST para auth/config/lifecycle/consultas/dataset; WS para estados observáveis/eventos. Controle no servidor, motores/SQLite próprios; cliente sem Docker/DB. HTTPS/WSS, token expirável/revogável, TOTP 2FA/escopos, snapshot/cursor/replay. Fechar cliente mantém bot.

**Escolhas técnicas iniciais do agente:** FastAPI/Uvicorn, token opaco/refresh rotativo, proprietário inicial local e Textual, mesmo host. Substitui lifecycle local e HTTP exclusivo de D050, sem alterar finanças/orçamento.

**Impactos:** SPEC 1.50/15.4, arquitetura/TUI/execução/escopo, plano E08–E10. Software/testes pendentes.

## D052 — V1 completa com transferência automática entre moedas

**Estado:** solicitado explicitamente pelo usuário em 12/10/2026 ao pedir mapa integral, TUI V1 e transferência automática.

**Decisão:** catálogo de resultados maduros, normalização/seleção, sombra prospectiva no destino e ativação/suspensão do complemento de C. Locais mantêm símbolo/mínimos; fontes conservam origem. Nenhum treino JEV, ajuste automático de risco/thresholds, saldo transferido ou JEV por amostra.

**Defaults técnicos iniciais do agente:** 60d, fonte >=50 não neutros/grupo/até200 por seleção determinística entre ativos; validação >=30 sombras destino não sobrepostas por família/horizonte/regime, Brier melhor que baseline anterior ao outcome; locais primeiro/três padrões totais. Não são calibração empírica/prova de lucro. Contrato SPEC 10.10/TRANSFERENCIA_APRENDIZADO.

**Destinação:** P014 vira entrega E07, substituindo exclusão de transferência em D050, preservando D008/D030/invariantes locais. Catálogo contínuo separado da base inicial imutável.

**Ordem:** Marcos 1–5, runtime, transferência, REST/auth, WS, TUI, aceite. Plano E00–E11/status para execução longa sem microaprovações. Segundo estilo/HTML fora; docs não declaram software pronto.

## D053 — Limite financeiro de IA configurável e opcional

**Estado:** solicitado e alteração de core autorizada pelo usuário em 14/10/2026.
**Restrição expressa original (prazo posteriormente revisto em D054):** preparar código e testes isolados; não executar os novos
comandos/configurações nos dados reais, não construir/aplicar imagens nem
reiniciar serviços durante o ensaio atual de 24 horas.

O limite de custo observado passa a ter valor global configurável e opção de
habilitar/desabilitar. Padrão continua habilitado em US$ 0,05/dia UTC. Um único
orçamento para todas as sessões, separado do hash/configuração financeira dos
experimentos; nova sessão não multiplica ou redefine uma política global explícita.

Desabilitar o limite financeiro não remove a contagem/guarda de até 240 chamadas,
circuito de credencial, prazos/retries, risco paper ou bloqueio de recuperação.
Manter cobrança observada/unknown, histórico e contador sem reset; registrar
revisão/ator/horário e política efetiva por reserva. Só proprietário global com
permissão manage/2FA ou operador local pode alterar. CLI/API preparam a gestão;
limite legado de sessão é fallback quando não há política global explícita.

Valor positivo finito em Decimal, sem teto fixo de cinco centavos na política
explícita. Reativar abaixo do já gasto bloqueia novas chamadas. O teto observado
não garante valor absoluto da fatura em presença de envios em voo/unknown.
Aplicação futura exige atualização compatível dos motores/controle; até lá o
experimento continua com as regras/imagens e orçamento anteriores.

**Contrato:** SPEC 1.51/8.2.2; sem alteração em A/B/C, capital, estratégia, taxas,
slippage, dados de treino ou cadência. Implementação preparada não é implantação.

## D054 — Período de amostragem sob controle do usuário

**Definido pelo usuário em 14/10/2026:** remover a exigência de esperar 24 horas;
o próprio usuário gerencia o período de coleta e solicita análises.

Não há duração mínima obrigatória, espera para atualizar serviços ou necessidade
de iniciar outra contagem de 24h após atualização. Analisar as amostras existentes
no intervalo solicitado, informando cobertura, lacunas, reinícios e versões.
Preservar bancos, carteiras, decisões, custos e aprendizado. Comparações que
atravessem mudanças relevantes devem distinguir as versões e seus períodos.

O observador é uma ferramenta opcional de leitura; seu prazo configurado não
bloqueia o motor, atualizações ou análises. Seus registros históricos e detecção
de lacunas continuam válidos; tempo transcorrido não comprova eficácia.

Esta decisão substitui o mínimo de 24h do aceite e a espera temporal de D053.
Não executa por si só implantação/reinício ou configuração do orçamento; D053
permanece preparado no checkout. Regras de maturação e mínimos estatísticos da
memória continuam vigentes, independentes do tempo escolhido para a análise.

**Contrato:** SPEC 1.52, aceite operacional e plano E11. Revisão documental sem
alteração de código, serviços, observadores ou dados operacionais.

## D055 — Reaproveitar interpretação de notícia sem reclassificar por outros artigos

**Solicitado e aprovado pelo usuário em 14/10/2026:** otimizar as classificações
repetidas causadas apenas por mudança das outras notícias enviadas para comparação.

Separar interpretação intrínseca da notícia e verificação factual do conjunto.
Interpretações têm identidade por conteúdo/destino/modelo/critérios, sem pares;
conflitos usam uma única chamada compartilhada por conjunto canônico de até cinco
notícias. Trocar um artigo de cinco passa a exigir uma interpretação nova e uma
comparação, em vez de repetir as cinco classificações completas. Primeira carga
tem cinco interpretações e uma comparação; não prometer economia fixa de custo.

Corrigir conteúdo reclassifica o artigo e a comparação afetada; reordenar não
gera chamadas. Mudança do conjunto nunca reutiliza a indicação antiga de ausência
de conflito. Falha/schema inválido/orçamento mantém conflito indeterminado,
cobertura parcial e gates de compra existentes; não apagar a interpretação válida.
Falhas podem ser recuperadas em janela posterior da coleta, sem repetição por
leitura/renderização e respeitando reserva, tentativas físicas e orçamento global.

Registrar IDs/modelos/evidências/tempos das duas etapas e fator composto disponível
somente após ambas. Manter passado imutável e fonte com validade original.
Recibos adicionais ficam na auditoria, sem inflar o prompt de negociação.
Notícias usam `news_factors_v3`/`news_conflicts_v1`; Polymarket mantém contrato v2.
Usar apenas título/resumo curto disponíveis, sem geração livre ou novo provedor.

**Contrato:** SPEC 1.53/5.29.1. Implementação no checkout com testes offline;
implantação não executada nesta tarefa. Sessão/carteiras/dados reais preservados.

## D056 — Plano de perfis cadastráveis: swing, scalping e day trade

**Solicitado pelo usuário em 14/10/2026:** criar plano de implementação que siga
a arquitetura existente, pesquise estratégias a fundo e inclua perfis cadastráveis
por template com todos os parâmetros. Estilos iniciais: swing, scalping e day
trade; hold fica para um segundo momento.

Sequência combinada: observar trend_15m_v1 para validar o core, analisar e corrigir
falhas pequenas, implementar/homologar perfis e então abrir sessão dedicada a
aproximadamente um mês numa estratégia escolhida. O período inicial é escolha
do usuário, sem reinstalar o bloqueio de 24h removido em D054.

Perfis devem orientar dados, sinais A, contexto/instruções B/C, risco, agenda,
execução e aprendizado. A/B/C são comparações no mesmo perfil, não três estilos.
Reutilizar hexagonal/portas, REST/WSS, TUI cliente, controle server-side e Docker
por sessão. Cadastro parametriza famílias conhecidas, não executa código livre.

Fixar revisão/snapshot/hash na sessão; novas versões não mudam bancos ativos.
Preservar legado e dataset V1, separar protocolos/estilos e manter orçamento
global. Valores de presets e famílias específicas no plano são **propostas
técnicas experimentais**, sujeitas a validação, não decisões de calibração ou
prova de retorno. Cadastro e novos estilos ainda não foram implementados.

**Artefatos:** PLANO_PERFIS_ESTRATEGIA.md (P00–P09),
PESQUISA_PERFIS_ESTRATEGIA.md e docs/templates/perfis/ (modelo completo + três
presets independentes). **Contrato:** SPEC 1.54/4.1.1. Tarefa documental sem
alteração de código, runtime, dados operacionais ou chamadas JEV.

## D057 — Implementar cadastro genérico de perfis e bots pela TUI

**Autorizado pelo usuário em 14/10/2026:** implementar a estrutura discutida na
pesquisa/plano D056. Não criar um bot rígido de scalping ou um serviço por estilo:
configuração, instruções e família implementada dão o comportamento ao motor
comum. Permitir cadastro/duplicação/revisão/validação/publicação pela TUI, depois
escolher moeda e criar nova sessão com o usuário.

Parar imediatamente o motor atual para interromper novas chamadas pagas;
preservar sessão ETH, bancos, credenciais, capital e evidências. Atualizar o
controle sem iniciar novo motor. Sem autorização implícita para escolher moeda,
publicar cadastros do usuário ou iniciar sessões automaticamente.

Revisão publicada é imutável; snapshots/hash/originais/overrides são fixados na
sessão. Pedidos de criação interrompidos fixam a revisão antes da consulta de
metadados. Restore não depende do catálogo. Regras duras verificadas no código,
sem execução de scripts/imports/expressões vindos do template ou da IA.

Famílias suportadas: rompimento anterior, cruzamento e alinhamento de EMAs.
Templates são dados completos de pré-configuração, ainda experimentais e sem
comprovação financeira. Intervalos fixos 1m/5m/15m/1h/4h/1d, proteção independente
da IA, agenda/cadência/custos, contexto JEV compacto e aprendizado V2 separado
do legado. Permanecem paper Spot long-only, A/B/C e orçamento global existente.

**Contrato:** SPEC 1.55/4.1.1. [Guia](GUIA_PERFIS_BOTS.md). Evidências e imagens
de implantação em STATUS_DESENVOLVIMENTO.md. Funcionamento observado sem trades
não comprova eficiência financeira ou vantagem do JEV.

## D058 — Instruções dos perfis em inglês para o JEV

**Autorizado pelo usuário em 14/10/2026:** ajustar objetivos e orientações de
estratégia enviados ao JEV para inglês antes de iniciar os três novos bots.
A [TypeSafe — Language support](https://docs.typesafe.ai/models#language-support)
afirma que inglês é o idioma principal de treinamento e de melhor precisão
atual; [State](https://docs.typesafe.ai/concepts/state) confirma precisão menor
em outros idiomas. Essa orientação não demonstra ganho financeiro da POC.

Traduzir os seis campos de instrução nos três templates empacotados, cópias
documentais, template genérico e defaults do schema. Versionar instruções como
`*_instructions_en_v2` e templates `.2`; manter os números e regras existentes.
Questionários de negociação/classificação já estão em inglês, sem alteração
de critérios ou invalidação desnecessária do cache semântico D055.

Interface, nomes de exibição e documentação em português. Evidências externas
conservam o texto original; não adicionar tradução automática, nova chamada IA
ou custo por decisão. Não impor detecção heurística de idioma ao texto livre.
Versões publicadas/sessões continuam imutáveis: revisão nova para mudar seu
conteúdo, sem reescrever resultados nem substituir configuração na retomada.

Controle/imagens devem entregar os novos templates antes de continuar o guia.
Nenhum perfil é cadastrado/publicado e nenhum motor é iniciado por esta mudança.
**Contrato:** SPEC 1.56; evidências no status.

## D059 — Orçamento JEV definido no perfil e aplicado por bot

**Definido pelo usuário em 14/10/2026:** limites não devem ser globais; cada
estratégia pode justificar um gasto diferente, que será comparado ao resultado.
Implementar defaults de chamadas/custo editáveis no perfil e na criação da
sessão, com contadores próprios por bot/dia UTC. Duas sessões do mesmo perfil
recebem cópias independentes; o total agregado não deve bloquear novos bots.

Campos `ai.budget_scope=SESSION`, `max_calls_per_day` inteiro positivo,
`cost_limit_enabled` booleano e `max_observed_cost_usd_per_day` Decimal positivo.
Defaults 240/US$ 0,05/habilitado por bot, sem esses tetos globais ocultos. Custos
incluem negociação, classificação e retries físicos; reuso/cache e chamada B/C
compartilhada não duplicam cobrança. Reserva transacional antes do envio, hash
da política por run_id, idempotência, desconhecidos e recuperação preservados.

Perfil publicado e sessão são imutáveis; novas revisões mudam os padrões de
partida, ajustes na criação ficam no snapshot desse bot. Perfis cadastráveis
anteriores podem originar novas sessões SESSION sem reescrever o cadastro.
Retomada antiga preserva schema/hash e contrato anterior. Escrita global é
retirada do fluxo normal; compatibilidade antiga explicitamente identificada.
Persistência compartilhada do orçamento não significa limite compartilhado.

TUI mostra limites/uso diário da sessão. Gasto real USD é separado do resultado
paper USDT; não prometer que o lucro cobrirá IA. Não implementar aumento automático
de gasto em função de PnL. Cotas reais do provedor/Marketaux, circuito de credencial
e bloqueio de recuperação incerta continuam independentes dos limites configurados.

**Contrato:** SPEC 1.57/8.2.3. Guia: GUIA_PERFIS_BOTS.md. Nenhum novo bot iniciado
automaticamente; manter a criação guiada de ZEC, SUI e UNI, uma sessão por vez.

## D060 — Janela de 15 segundos no teste scalping ZEC

**Autorizado pelo usuário em 14/10/2026:** ajustar o parâmetro e deixar o bot
rodando ao final. O ciclo de 18:22 Brasília passou pelo filtro, mas gastou 2,3s
na preparação e restaram 5,7s da janela de 8s; o cliente requer timeout completo
de 6s e não enviou a inferência. Não confundir o HOLD operacional com escolha JEV.

Aceitar até 15s em perfis SCALPING e publicar `scalping_zec_v1` revisão 2 com
janela 15s. Preservar os demais parâmetros efetivos do teste ZEC (inclusive
timeout 6s e orçamento da sessão US$ 0,50/240 chamadas). Não ampliar intervalo
1m/5m, desativar filtros nem flexibilizar cotação/spread/desvio para forçar trade.

Parar/preservar a sessão antiga e criar uma nova com a revisão 2; cada sessão
mantém seu snapshot/hash, carteiras, custos e resultados. Não editar os registros
antigos nem simular retrospectivamente oportunidades perdidas. Deixar o novo
motor ativo. Quinze segundos são hipótese para observação; não garantem resposta,
ordem, lucro ou eficiência. **Contrato:** SPEC 1.58/4.1.1; evidências no status.
