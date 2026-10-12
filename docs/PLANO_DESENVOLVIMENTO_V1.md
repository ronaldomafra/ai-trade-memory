# Plano de desenvolvimento — primeira V1 completa

**Plano 1 · 12/10/2026 · SPEC 1.50 · D051/D052.**
Documento para executar o desenvolvimento em ordem. Bot/API/Docker/transferência/TUI ainda não implementados.
Ler [AGENTS.md](../AGENTS.md) e [SPEC.md](SPEC.md) integralmente antes de trabalhar.
A SPEC determina comportamento; este plano organiza construção e comprovação.
[Progresso](STATUS_DESENVOLVIMENTO.md) · [Escopo](ESCOPO_POC_V1.md) · [Decisões](DECISIONS.md).

## Entrega esperada

Aplicação Python hexagonal em Docker, paper trading 24/7, sessões independentes e TUI V1 local/remota. Cada sessão escolhe par Spot USDT, perfil implementado, ajustes permitidos e dataset opcional antes de iniciar. Restaurar recupera estado; fechar a TUI mantém o motor.

A técnica, B JEV sem memória e C JEV com memória local e transferência validada entre moedas. Cada carteira começa com 100 USDT fictícios. Catálogo inicial `trend_15m_v1`; várias moedas/sessões não exigem inventar segundo estilo. HTML, negociação real e segundo estilo sem contrato ficam fora.

REST para login/2FA, configuração, criação/restauração, consultas e datasets; WebSocket para processamento observável, cotações, posições, decisões, saúde e eventos. O servidor controla containers; cliente remoto precisa apenas do endereço e credenciais, sem Docker ou SQLite.

Transferência automática publica observações amadurecidas, seleciona padrões compatíveis, valida prospectivamente no destino e ativa/suspende o complemento de C. Não retreina o JEV, mistura saldos ou promete precisão imediata numa moeda nova. [Contrato de transferência](TRANSFERENCIA_APRENDIZADO.md).

## Ordem obrigatória

| Etapa | Entrega | Dependências |
| --- | --- | --- |
| E00 | Preparação e rastreabilidade | Docs vigentes |
| E01 | Marco 1: domínio/contabilidade offline | E00 |
| E02 | Marco 2: mercado público/A/motor contínuo | E01 |
| E03 | Marco 3: JEV/orçamento global | E02 |
| E04 | Marco 4: outcomes/memória/dataset | E03 |
| E05 | Marco 5: notícias/Poly/fatores/relatórios | E04 |
| E06 | Docker/múltiplas sessões/continuidade | E05 |
| E07 | Transferência automática entre moedas | E04–E06 |
| E08 | Core remoto REST/auth/lifecycle | E06–E07 |
| E09 | WebSocket/eventos/reconexão | E08 |
| E10 | TUI V1 completa | E08–E09 |
| E11 | Integração/24h/entrega | E00–E10 |

Marcos 1–5 permanecem consecutivos. Não antecipar interface em lugar de contabilidade, risco e recuperação.

## E00 — Preparar o projeto

- [ ] Inspecionar estado real e preservar alterações do usuário; registrar baseline no status.
- [ ] Python 3.11+, `pyproject.toml`, lockfile, `src/poc`, testes, configuração, `.env.example` e ignore de dados/segredos.
- [ ] Bootstrap, portas, configuração versionada, relógio injetável e convenções de IDs/cutoff/eventos.
- [ ] Dependências da SPEC; acrescentar FastAPI/Uvicorn, cliente WS, Textual e bibliotecas mantidas de senha/TOTP, fixadas no lockfile.
- [ ] README com instalação e comandos disponíveis; contratos futuros não são comandos já executáveis.

**Aceite:** instalação reproduzível, ajuda da CLI, configuração validada e testes/lint sem serviços externos.

## E01 — Marco 1: domínio e simulação offline

**Módulos:** domínio financeiro/técnica/risco, perfis/configuração, portas, sessões, SQLite/UoW, broker e CLI.

- [ ] Template `trend_15m_v1` fiel à SPEC; ajustes validados/persistidos antes da sessão.
- [ ] Nova/restaurar com run_id/banco exclusivos, lock e A/B/C de 100 USDT.
- [ ] Decimal, filtros por par, taxas/slippage/arredondamento, buy/sell long-only e ledger.
- [ ] Fill/saldo/ledger/eventos num commit; JSONL reconstruível.
- [ ] Stops/take/duração/trava diária persistidos com precedência da SPEC.
- [ ] Smoke offline e consultas/exportações básicas.

**Testes:** fees dentro do orçamento, saldo não negativo, precisão BTC/ETH, restore sem reset, criação/fill idempotentes, crash na transação e projeções recuperadas.

**Aceite:** percurso offline auditável com ledger reconciliado, sem TODO essencial ou cliente de ordens reais.

## E02 — Marco 2: mercado e execução contínua

**Módulos:** Binance público, indicadores/features, scheduler, orquestrador e proteção.

- [ ] Metadados de par Spot USDT elegível, símbolos/unidades genéricos.
- [ ] WS candles fechados/bookTicker; REST warmup/backfill/fallback.
- [ ] Indicadores/A com 15m/1h fechados, dados disponíveis no cutoff.
- [ ] Ciclo idempotente, prazo de decisão e nova cotação antes do fill.
- [ ] Risco ativo durante inferência/entre candles.
- [ ] Retomada após gaps/crash sem trade retroativo ou bid histórico inventado.

**Testes:** candle aberto, timestamp ausente, duplicação/atraso, fallback tardio, preço vencido, saída única, trava diária/UTC e risco durante espera JEV.

**Aceite:** A contínua com fonte pública e retomada correta. Falta de acesso real exige evidência offline e integração marcada pendente.

## E03 — Marco 3: JEV e orçamento

**Módulos:** Decisions API, schemas/prompts, validação, tentativas, SQLite operacional e conciliação.

- [ ] `POST https://openrouter.ai/api/alpha/decisions` com `typesafe/jev-1.13`; sem Chat Completions.
- [ ] Inferência estruturada; proposta/validação/fill separados.
- [ ] IDs/modelo efetivo/usage/latência/custo observado ou unknown.
- [ ] Duas tentativas físicas totais, apenas transitórias, dentro de prazo/capacidade.
- [ ] Reserva global atômica/idempotente antes de HTTP, rollover UTC e reconciliação pós-crash.
- [ ] Compartilhar B/C somente com estados/contextos equivalentes.
- [ ] Falha/invalidade/esgotamento => HOLD afetado; A/risco ativos.

**Testes:** resposta inválida, timeout/cobrança desconhecida, retry proibido, crash antes/depois do envio, concorrência entre sessões/classificações e custos sem duplicação.

**Aceite:** 240 chamadas físicas e US$ 0,05 observado/dia UTC globais. Duas sessões 15m podem demandar 384/dia antes de extras: reportar cobertura/HOLD, sem aumentar limite/cadência. Sem chave, adaptador completo/mocks, sem alegar smoke real.

## E04 — Marco 4: memória e dataset

**Módulos:** maturação, equivalência, estatísticas, contexto compacto e import/export.

- [ ] ENTRY_LONG_NET_RETURN/HOLD_VS_SELL_RETURN, horizontes 4/16 e bid observado na janela de 90s.
- [ ] Sem bid => UNAVAILABLE fora das estatísticas.
- [ ] Local por símbolo/protocolo/posição/família/horizonte; exata >=30, regime >=50, janela 60d.
- [ ] Deduplicar equivalentes A/B/C preservando origens; reportar sobreposição temporal.
- [ ] Dataset inicial opcional, schema/hash/proveniência, materialização idempotente antes da primeira decisão e reexportação acumulativa.
- [ ] Até três padrões C; B sem memória; nenhum JEV por registro.
- [ ] Porta de publicação de resultados maduros para E07, sem misturar fontes na memória local.

**Testes:** look-ahead, bid ausente, famílias/horizontes, mínimos/neutralidade, import/export/import, arquivo alterado, crash, overlap e origem.

**Aceite:** restore conserva memória SQLite; dataset não importa capital/fills/travas. Fonte estrangeira não conta nos mínimos locais.

## E05 — Marco 5: contexto e relatórios

**Módulos:** Marketaux gratuito/RSS, Gamma/CLOB públicos, classificação/reuso, fatores e relatórios.

- [ ] Implementar SPEC 5.5–5.35: descoberta/limites, relevância ao ativo, qualidade, tempos, unidades, associação e conflitos.
- [ ] Quota gratuita efetiva e token pelo ambiente; proxy opcional em configuração secreta local.
- [ ] Mesma base B/C no cutoff; probabilidade Poly não equivale a fato confirmado.
- [ ] Fatores/evidência curta com reuso persistido; classificação JEV dentro do orçamento global.
- [ ] Diferenciar fonte indisponível, parcial, pendente e recorte validamente vazio.
- [ ] JSONL reconstruível e JSON/CSV: finanças, decisões, outcomes, memória e custo.
- [ ] Relatar C−B/B−A com cobertura e períodos de memória; sem efeito isolado fictício.

**Testes:** dado vencido/futuro, vazio vs truncado, unidade/volume/liquidez/livro, qualidade/confiança/premissa, ativo sem relação BTC, quotas/cache/restart.

**Aceite:** adaptadores completos e gates conservadores. Fixture Gamma não comprova feed real. Sem artigos integrais/segredos nos logs.

## E06 — Docker e múltiplas sessões

**Módulos:** Dockerfile/Compose, runtime server-side, manifests, saúde e backup.

- [ ] Imagem comum; um motor/container/SQLite/volume por sessão, serviços compartilhados no mesmo host.
- [ ] Preparação/partida/retomada idempotentes, lock e reconciliação.
- [ ] Volumes locais/WAL, restart unless-stopped, SIGTERM/grace e heartbeat.
- [ ] Backup consistente e restore separado; export não substitui backup.
- [ ] CLI/systemd alternativa, sem supervisores concorrentes.
- [ ] Runtime aceita apenas ações/argumentos validados; nenhum shell arbitrário da TUI.

**Testes:** kill/restart, persistência, lock/restore, daemon indisponível, dois pares e quota global.

**Aceite:** motores independentes do cliente, sem reset; privilégios Docker no servidor documentados. Sem SQLite compartilhado entre hosts.

## E07 — Transferência automática

**Módulos:** catálogo SQLite, normalizador, seleção, sombra/gates e composição da memória.

- [ ] Implementar [TRANSFERENCIA_APRENDIZADO.md](TRANSFERENCIA_APRENDIZADO.md)/SPEC 10.9–10.10.
- [ ] Publicar fontes maduras idempotentes com origem/disponibilidade real; aceitar dataset validado no catálogo.
- [ ] Features comparáveis/protocolo compatível; fontes estrangeiras nunca viram observações locais.
- [ ] Previsões sombra antes do resultado destino; score após maturação.
- [ ] Ativar/suspender automaticamente, sem mudar risco/thresholds ou pesos JEV.
- [ ] Até três padrões totais, locais primeiro; estados/score/proveniência persistidos.
- [ ] Import/export conserva origem; não importa aprovação ACTIVE para novo destino.

**Testes:** BTC→ETH, escala/retorno percentual, future/availability leak, shadow/overlap, insuficiência, ACTIVE/SUSPENDED, catálogo offline, dedupe e restore.

**Aceite:** fluxo automático e rejeição de transferência ruim comprovados com fixtures identificadas. Moeda real pode estar VALIDATING; não fabricar labels para ativar. Nenhum JEV por amostra.

## E08 — REST e autenticação remota

**Módulos:** control-api FastAPI, casos de uso, runtime port, auth e schemas públicos.

- [ ] Gateway único/REST versionada/OpenAPI; motores internos mantêm autoridade financeira.
- [ ] Proprietário criado localmente por CLI, senha com hash adequado, 2FA TOTP e recuperação local documentada.
- [ ] Token opaco expirável/revogável, refresh rotativo, hashes persistidos e escopos read/manage por sessão.
- [ ] Login/2FA/refresh/logout, perfis, criar/retomar/snapshot/histórico, datasets e transferência.
- [ ] Idempotency-Key persistida para comandos, sem sessão/capital duplicados.
- [ ] Upload JSONL limitado/validado; identificadores opacos, sem caminho arbitrário/import financeiro.
- [ ] Lifecycle Docker exclusivamente no servidor; HTTPS remoto, localhost HTTP apenas em desenvolvimento identificado.

**Testes:** senha/TOTP/replay, rate limit, token expirado/revogado, escopo errado/outra sessão, traversal/upload, crash no provisionamento e snapshot consistente.

**Aceite:** cliente remoto cria/restaura/importa/exporta sem Docker/DB. GET não opera/chama IA. Sem edição de sessão ativa ou credenciais padrão.

## E09 — WebSocket e reconexão

**Módulos:** event hub, protocolo, assinaturas e cliente WS.

- [ ] WSS autenticado/autorizações por sessão; rechecagem de expiração/revogação.
- [ ] Etapas observáveis: coleta/features/espera JEV/validação/risco/fill/maturação/transferência. Não transmitir raciocínio interno do modelo.
- [ ] Eventos duráveis run_id/event_id/seq; tick/progresso efêmeros separados.
- [ ] REST snapshot+watermark consistente, replay desde cursor e dedupe cliente.
- [ ] Resync quando histórico indisponível; reconexão com backoff/ping/pong.
- [ ] Mensagens/filas/conexões limitadas; cliente lento não bloqueia motor. Coalescer preço, não evento financeiro durável.

**Testes:** race snapshot/assinatura, duplicação/ordem, gateway/motor reiniciado, cursor vencido, backpressure e revogação durante WS.

**Aceite:** cliente recompõe estado sem perder fills/gerar IA; desconexão não para bot. Não persistir todo tick para desenhar.

## E10 — TUI V1

**Módulos:** Textual, telas/formulários, gráficos e clientes REST/WS.

- [ ] Conexão local/remota e login/2FA, segredos fora de histórico/logs.
- [ ] Listar/selecionar sessões/saúde; nova/restaurar sem reset.
- [ ] Wizard perfil/par/defaults/ajustes/dataset opcional/transferência antes da criação.
- [ ] Dashboard da [referência preservada](referencias/tui-dashboard-referencia.png): carteira, candles, curvas A/B/C, posições/fills, decisão/gates, IA/memória/custo e eventos.
- [ ] Origem local/transferida, fontes/destino/contagens/score/VALIDATING/ACTIVE/SUSPENDED e motivos.
- [ ] Import/export, filtros, ajuda, teclado, resize/abas e estados vazios/degradados.
- [ ] Última atualização/desconexão explícitas; sair/logout não para motores.

**Testes:** interação Textual, resize, wizard inválido/sem dataset, outra moeda, duas sessões, read-only, erro REST/queda WS, identidade errada e fechamento.

**Aceite:** fluxos integrados ao backend; nenhum saldo da imagem ou mock em produção. Capturas de terminal e roteiro de uso.

## E11 — Integração, hospedagem e entrega

- [ ] Instalação limpa, suíte apropriada completa, lint e config.
- [ ] Compose integrado/control-api/motores/volumes/reverse proxy TLS, portas de motores privadas.
- [ ] Percurso TUI→REST→motor→evento→WS→TUI: sessão, restore, dataset e transferência.
- [ ] Duas sessões/pares, quotas globais, rede/SIGTERM/crash/token revogado e backup/restore.
- [ ] Pelo menos 24h em paper com fontes disponíveis e logs/cobertura/custos registrados; senão aceite operacional pendente.
- [ ] Transferência funcional com fixtures identificadas; ativações reais apenas com dados válidos.
- [ ] README com instalação/.env/CLI/TUI/Docker/systemd/logs/diagnóstico/restore efetivamente testados.
- [ ] Relatório final: versão/config, testes, chamadas reais vs mocks, artefatos e limitações.

**Aceite:** SPEC 18 e todas as etapas completas, sem TODO/mock essencial em produção. Fonte/chave ausente ou 24h não realizado é pendência explícita. Homologação posterior do usuário; software pronto não comprova lucro.

## Organização dos módulos e dados

```text
src/poc/
  domain/                # finanças, risco, técnica, features, learning/transfer
  application/           # sessões, ciclos, contexto, outcomes, reporting
  application/ports.py   # mercado, IA, UoW, catálogo, runtime e eventos
  adapters/inbound/      # CLI, scheduler, REST e WS
  adapters/outbound/     # fontes, SQLite, arquivos e Docker
  presentation/tui/      # telas/gráficos/clientes REST-WS
  bootstrap.py           # composição engine/control-api
tests/                   # unit, integration, contract, tui, acceptance
config/ deploy/ docs/
```

Nomes podem evoluir, preservando fronteiras. Não criar microserviço por indicador. Engine executa aplicação/domínio no próprio processo; controle coordena acesso remoto/runtime.

| Persistência | Autoridade |
| --- | --- |
| `data/sessions/RUN_ID/poc.sqlite3` | Finanças/eventos/ciclos/memória local e estado de transferência da sessão. |
| `data/operational/budget.sqlite` | Reservas/tentativas/custos globais, sem saldos. |
| `data/operational/control.sqlite` | Auth, comandos idempotentes e registro operacional; não copia ledger. |
| `data/learning/catalog.sqlite` | Read model de observações maduras/proveniência/disponibilidade, sem finanças. |
| `data/sessions/RUN_ID/{logs,exports}/` | Projeções e JSON/CSV/datasets. |

Bancos no mesmo host/volumes locais; não presumir transação entre bancos. Falha do catálogo recupera por outbox/reconciliação, sem comprometer commit financeiro.

## Condução de uma execução longa

1. Ler contrato/status, verificar repositório real e começar primeira etapa aberta.
2. Implementar módulos completos/testes críticos/migrações; preservar dados/alterações.
3. Corrigir verificações relevantes antes de marcar etapa concluída.
4. Registrar no status arquivos, comandos, resultados, artefatos, pendências e próxima ação; atualizar README.
5. Prosseguir pelos itens independentes sem microaprovações. Chave ausente impede smoke real, não todos os módulos offline.
6. Não ajustar orçamento/risco/estratégia para contornar testes; explicitar mudança material.
7. Entregar evidências; não declarar V1 completa com módulo essencial ou aceite obrigatório faltante.

Prompt para iniciar a implementação posteriormente:

> Leia AGENTS.md e docs/SPEC.md integralmente, depois docs/PLANO_DESENVOLVIMENTO_V1.md e docs/STATUS_DESENVOLVIMENTO.md. Implemente a V1 completa na ordem E00–E11, incluindo TUI remota REST/WebSocket, autenticação/2FA, sessões Docker e transferência estatística automática entre moedas. Preserve o contrato de paper trading e os limites. Registre progresso/evidências a cada etapa e continue pelos itens independentes sem microaprovações. Identifique integrações reais não testadas e aceite operacional pendente.

Este documento não inicia o bot, provisiona servidor ou consome chamadas JEV.

## Referências técnicas

FastAPI permite adaptar WS no serviço: [documentação oficial](https://fastapi.tiangolo.com/advanced/websockets/). Textual oferece testes de interação: [guia oficial](https://textual.textualize.io/guide/testing/).
Protocolo/autenticação seguem [RFC 6455](https://www.rfc-editor.org/rfc/rfc6455), [OWASP WebSocket Security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html) e [RFC 6238/TOTP](https://www.rfc-editor.org/info/rfc6238/). Fontes sustentam mecanismos, não validam nossa implementação ou trading.
