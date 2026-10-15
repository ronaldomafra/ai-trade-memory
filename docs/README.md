# Documentação da V1 completa

**SPEC 1.58 · D050–D060.** Perfis genéricos, catálogo versionado e cadastro pela TUI implementados; templates e testes não provam eficácia financeira. Sessão ETH parada pelo usuário; escolhidos ZEC/scalping, SUI/day trade e UNI/swing para criação guiada. D058: objetivos/orientações JEV em inglês. D059: orçamento JEV próprio por bot, configurado no perfil/criação. D060: scalping aceita prazo de 15s; teste ZEC revisão 2 ativo, anterior preservado e parado. Estado de implantação no status. D054 mantém amostragem escolhida pelo usuário.

Ler SPEC integralmente; executar plano na ordem e registrar evidências no status. Decisões D051/D052 prevalecem sobre restrições históricas de HTTP exclusivo/lifecycle no cliente e transferência fora da V1.

| Documento | Uso |
| --- | --- |
| [GUIA_CONFIGURACAO_EXECUCAO.md](GUIA_CONFIGURACAO_EXECUCAO.md) | Passo a passo de instalação, .env, Docker/TUI, sessões, datasets, diagnóstico e recuperação. |
| [SPEC.md](SPEC.md) | Contrato funcional/técnico, limites e aceite. |
| [PLANO_DESENVOLVIMENTO_V1.md](PLANO_DESENVOLVIMENTO_V1.md) | Sequência E00–E11, entregáveis/testes/aceite e execução longa. |
| [PLANO_PERFIS_ESTRATEGIA.md](PLANO_PERFIS_ESTRATEGIA.md) | Extensão D056, ordem P00–P09, cadastro/versionamento, regras, JEV, aprendizado e homologação. |
| [PESQUISA_PERFIS_ESTRATEGIA.md](PESQUISA_PERFIS_ESTRATEGIA.md) | Pesquisa de swing/scalping/day trade com fontes, famílias e limites. |
| [PESQUISA_MOEDAS_POR_PERFIL_20261014.md](relatorios/PESQUISA_MOEDAS_POR_PERFIL_20261014.md) | Triagem de 32 pares, candidatos por perfil, dados, fontes e limites para o teste extenso. |
| [templates/perfis/README.md](templates/perfis/README.md) | Modelo completo e três presets YAML, tipos/unidades/campos e validações. |
| [VALIDACAO_PERFIS_GENERICOS_20261014.md](relatorios/VALIDACAO_PERFIS_GENERICOS_20261014.md) | Entrega D057, 288 testes, imagens, preservação da ETH e limites da validação. |
| [VALIDACAO_ORCAMENTO_POR_BOT_20261014.md](relatorios/VALIDACAO_ORCAMENTO_POR_BOT_20261014.md) | D059, limites próprios por bot, 297 testes, implantação e preservação dos dados. |
| [STATUS_DESENVOLVIMENTO.md](STATUS_DESENVOLVIMENTO.md) | Progresso real/evidências/pendências/próxima ação. |
| [ESCOPO_POC_V1.md](ESCOPO_POC_V1.md) | Entrega e exclusões. |
| [BACKLOG_IMPLEMENTACAO.md](BACKLOG_IMPLEMENTACAO.md) | Mapa técnico associado ao plano. |
| [DECISIONS.md](DECISIONS.md) | Histórico D001–D059. |
| [GUIA_PERFIS_BOTS.md](GUIA_PERFIS_BOTS.md) | Cadastro, configuração, publicação e criação de bots na TUI/CLI/API. |
| [PONTOS_A_ESCLARECER.md](PONTOS_A_ESCLARECER.md) | Histórico/destinação P001–P016. |
| [ARQUITETURA.md](ARQUITETURA.md) | Hexagonal/Docker/controle remoto/REST-WS/bancos. |
| [CONTEXTO_TUI.md](CONTEXTO_TUI.md) | Fluxos/login/dashboard e referência visual. |
| [TRANSFERENCIA_APRENDIZADO.md](TRANSFERENCIA_APRENDIZADO.md) | Catálogo/normalização/validação/gates/estados. |
| [DATASET_APRENDIZADO.md](DATASET_APRENDIZADO.md) | Import/export/proveniência/acumulação. |
| [PERFIS_E_SESSOES.md](PERFIS_E_SESSOES.md) | Perfil/template/config/banco/restore. |
| [ESTRATEGIAS.md](ESTRATEGIAS.md) | Pesquisa sem habilitar estilo adicional. |
| [FONTES_DE_CONTEXTO.md](FONTES_DE_CONTEXTO.md) | Notícias/Poly/evidências/contratos. |
| [CONTEXTO_DESENVOLVIMENTO.md](CONTEXTO_DESENVOLVIMENTO.md) | Invariantes e validação. |
| [CONTEXTO_EXECUCAO.md](CONTEXTO_EXECUCAO.md) | Operação/falhas/retomada/aceite. |

Preservar fixture Gamma e imagem originais. Pesquisa/fixtures não são resultados operacionais; distinguir comandos implementados do contrato e das validações ainda pendentes.
