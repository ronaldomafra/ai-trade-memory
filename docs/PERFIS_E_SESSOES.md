# Perfis operacionais e sessões independentes

**Escopo vigente D057/SPEC 1.55:** motor genérico e catálogo versionado de
perfis implementados, com templates de swing/scalping/day trade e famílias
parametrizáveis. Cadastro/publicação pela TUI não inicia motor; criar sessão fixa
perfil/revisão/configuração e trio A/B/C. Legado preservado, hold adiado.
[Guia](GUIA_PERFIS_BOTS.md) · [Plano](PLANO_PERFIS_ESTRATEGIA.md).
Notas históricas abaixo descrevem a evolução; não substituem o status atual.

**D030 — suporte a outros ativos na V1:** um par Spot configurável com cotação USDT por sessão, selecionado antes de iniciar; BTC é exemplo/default. Banco, trio A/B/C e memória por símbolo permanecem separados. Quantidades, metadados, feeds, prompts e contexto usam o ativo destino. Retomada mantém o par salvo; transferência estatística separada integra a V1 conforme D052/SPEC 10.10. [Contrato vigente, seção 4.3](SPEC.md). Implementação pendente.

**Requisitos definidos em 11/10/2026:** seleção do perfil antes de iniciar, dois perfis após homologação (D009), banco próprio por sessão (D010), perfil inicial `trend_15m_v1` (D011), base hexagonal/Docker (D012) e pré-configuração por estratégia com ajustes antes da sessão (D013). Implementação pendente. Perfis de uso serão escolhidos na partida; contratos do catálogo/campos editáveis em P006, operação conjunta/orçamento em P015. Consultar [arquitetura aprovada](ARQUITETURA.md); TUI por último, P007.

## Vocabulário do projeto

| Conceito | Significado |
| --- | --- |
| Perfil operacional | Estratégia com regras completas, versão, intervalos, sinais, risco e aprendizado; escolhido antes de criar sessão. |
| Variante A/B/C | Método de decisão dentro do mesmo perfil: técnica, JEV sem memória e JEV com memória. |
| Sessão | Execução persistida, identificada por `run_id`, com banco/configuração e trio A/B/C próprios. Pode durar vários dias. |
| Dia UTC ou horário de operação | Referência temporal para risco ou encerramento de um perfil; não equivale à sessão persistida. |
| Homologação | Termo usado pelo usuário para sua etapa de validação antes da operação pretendida. Não pressupõe certificação externa. |

## Seleção obrigatória na V1

Uma sessão nova exige perfil explícito. Não iniciar automaticamente a estratégia técnica porque não houve escolha, nem interpretar `HOLD` como seleção de buy and hold. O catálogo lista ID, versão, descrição e estado real do perfil; candidato pesquisado ou incompleto não está disponível para operação.

`trend_15m_v1` é o primeiro perfil aprovado em D011 e implementado: curto prazo contínuo, 24/7, entradas/saídas A da seção 7.2, decisões em 15m, tendência 1h, máximo nominal de 16 candles (~4h), risco/custos e horizontes 4/16 atuais. Sem fechamento compulsório pela virada UTC; preservar trava diária e demais saídas de risco. Homologação operacional segue as evidências no status. D056 selecionou swing, scalping e day trade para o plano de novos perfis, sem habilitá-los ainda.

Para cada perfil pretendido, definir antes de habilitar:

| Grupo | Contrato necessário |
| --- | --- |
| Identidade | ID/versão, estilo, família de sinais e estado de implementação/validação. |
| Dados | Símbolo, fontes públicas, intervalos, aquecimento, frescor e qualidade. |
| Estratégia | Algoritmo determinístico A; política/perguntas B/C e versões. |
| Tempo | Cadência, confirmação, duração máxima e eventual horário de operação/encerramento. |
| Risco/execução | Alocação, proteções, prioridades, custos, lotes, janela de decisão e preço observado. |
| Aprendizado | Famílias/horizontes e suas durações, buckets, janela, mínimos, compatibilidade de importação e cutoff. |
| IA/operação | Consumo esperado, orçamento coordenado, falhas, retomada, relatórios e testes. |

## Pré-configuração editável antes da sessão (D013)

Cada estratégia implementada terá template estruturado/versionado com parâmetros base derivados dos seus documentos. Registrar referência documental, tipos, unidades, campos editáveis e regras de validação. Escolher o perfil de uso na partida, carregar o template e permitir ajustes antes de iniciar sessão nova. A futura TUI oferece esse requisito; o mesmo caso de uso de aplicação resolve/valida os parâmetros para CLI e interface, sem duas configurações divergentes.

Persistir template/versão, parâmetros base, alterações explícitas e configuração efetiva/hash. Identificar a parametrização em relatórios/datasets. A edição de uma sessão não modifica o template original nem a configuração de outras sessões; o trio A/B/C recebe a mesma parametrização operacional.

Depois de criada, a sessão conserva os valores efetivos. Restaurar recupera essa configuração, mesmo se o template tiver evoluído; ajustes para outro experimento exigem sessão nova. Importação de aprendizado revalida compatibilidade com o protocolo efetivo, sem pressupor que o nome do perfil torna configurações equivalentes. Limites globais de IA continuam separados da parametrização do perfil.

D056 agora especifica esse fluxo em P01/P07/P08: novo perfil a partir de template completo, validação, cadastro versionado, publicação e seleção na nova sessão. Perfis disponibilizados precisam de contratos/implementação/validação próprios. Isso não habilita um estilo apenas por editar um intervalo; hold permanece fora desta etapa.

Alterar só o intervalo no YAML não implementa outro estilo. Regras específicas de um novo perfil precisam de aprovação e testes; o perfil atual continua reproduzindo seu contrato. Mudanças após observar resultados abrem outra sessão/versionamento, sem reescrever resultados passados.

## Um banco por sessão

O diretório previsto é `data/sessions/RUN_ID/`, com `poc.sqlite3`, logs e exportações. Registrar identidade, perfil/versão, configuração efetiva imutável e caminhos. As três carteiras e os dados canônicos da sessão ficam nesse banco. Datasets portáveis podem reunir origens de outros bancos, mantendo IDs e compatibilidade; importação não transforma sessões distintas em um único histórico financeiro.

**Nova sessão:** criar identidade/banco novos, selecionar/validar perfil e iniciar A/B/C com 100 USDT cada. Importação opcional alimenta somente a memória de C antes da primeira decisão. Nunca sobrescrever sessão existente para começar novamente.

**Restaurar sessão:** abrir banco escolhido e recuperar perfil/configuração, saldos, posições, ledger, ciclos, risco diário, chamadas/tentativas, memória, importações e cursores. Reavaliar risco no preço atual. Não repor capital, trocar perfil, importar novamente arquivo alterado ou negociar retroativamente. Banco ausente/inválido produz erro de restauração, sem criar automaticamente outra sessão. Lock impede dois motores no mesmo banco.

Os comandos legados abaixo possuem implementação; perfil/dados/credenciais precisam estar preparados conforme o guia. Os comandos novos de cadastro constam como planejados em P07:

```bash
python -m poc profiles --config config/default.yaml
python -m poc run --config config/default.yaml --new-session --profile trend_15m_v1
python -m poc run --config config/default.yaml --resume RUN_ID
```

Criação e restauração são modos distintos; rejeitar seleção ambígua. Ao restaurar, configuração/perfil do banco são a fonte de verdade, e argumentos conflitantes são rejeitados. Comandos de dados identificam a sessão por `--run-id RUN_ID`, sem selecionar silenciosamente a mais recente. A futura TUI poderá usar o mesmo serviço, mas fase, telas e controles serão definidos por último.

## Dois perfis após homologação

Cada perfil escolhido terá sessão própria e trio A/B/C. Dois perfis significam seis carteiras virtuais independentes, sem compartilhar caixa, posições, travas ou memória estatística. Avaliar C−B e B−A dentro de cada perfil; relatórios entre perfis identificam diferenças de regra, período e regime. Não comparar A de um estilo com C de outro para atribuir o efeito exclusivamente à memória.

Feeds e fatores externos podem ser reutilizados quando forem compatíveis e disponíveis no instante correto. O orçamento de IA continua global, mesmo com bancos separados. Antes de iniciar duas sessões ao mesmo tempo, definir e testar coordenação/reserva entre motores, prioridade/distribuição e contabilização única por chamada física. Não dobrar automaticamente os limites de 240 chamadas/dia e US$ 0,05 observado/dia.

Dois perfis de 15m, com duas chamadas B/C separadas por ciclo, exigiriam nominalmente `2 × 96 × 2 = 384` chamadas de decisão/dia, antes de classificação/repetições. Esse caso exige discutir capacidade e política em P015; não mudar silenciosamente cadência ou orçamento. Não assumir que todos os estados/prompt de perfis diferentes permitem compartilhar uma resposta JEV.

## Pontos preservados

- P006/D013: templates/configuração antes da sessão definidos; completar catálogo, regras e campos editáveis. Escolha dos perfis de uso na partida; primeiro template aprovado em D011.
- P016/D012: base hexagonal e execução com Docker aprovadas; container não altera identidade ou estado da sessão. Implementação/validação pendentes.
- P015: operação conjunta, coordenação de orçamento, distribuição de chamadas e critérios de homologação de cada perfil/sessão.
- P008/P014: dependência entre avaliações de candles consecutivos e detalhes de transferência de memória; origem/deduplicação aprovadas em D014, preservando separação de perfis incompatíveis.
- P007: TUI por último; registrar desejo de criar/restaurar sessões sem antecipar fase ou controles.

Validar seleção, isolamento dos bancos, criação sem sobrescrita, restauração sem reset, perfil/configuração imutáveis, ausência de trades retroativos e orçamento global concorrente antes da operação correspondente. Novos templates documentais não criam perfis executáveis nem alteram sessões existentes.

Ao criar sessão, resolver `market.symbol` ou `--symbol SYMBOL` juntamente com `--profile PROFILE_ID`; validar antes de criar carteiras. Por exemplo, sessões BTCUSDT e ETHUSDT podem usar o mesmo `trend_15m_v1`, cada uma com trio A/B/C e banco próprio. Comparação entre ativos não substitui C−B dentro de cada sessão. CLI/futura TUI usam o mesmo contrato; retomada mantém par/perfil/configuração salvos. Operação conjunta aguarda coordenação P015; novos estilos continuam com contratos próprios.
