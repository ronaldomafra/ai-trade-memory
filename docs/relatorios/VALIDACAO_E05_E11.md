# Revisão E05 e integração E11

12/10/2026 · aplicação 0.1.0 · SPEC 1.50. V1 ainda sem aceite completo:
JEV autenticado, contrato monetário Gamma e observação de 24h permanecem abertos.
Marketaux autenticada foi adiada pelo usuário; hospedagem pública não foi realizada.

## Contexto externo

Notícias usam `news.lookback_hours` na consulta Marketaux, chave do cache,
filtro local, expiração do fator e validade da ausência no recorte. RSS representa
somente os itens da edição coletada. URLs/reflexos de credencial são sanitizados;
duplicatas por URL ou título/fonte/publicação preservam aliases e proveniência
disponível naquele cutoff. Uma nova edição diária não é fundida à anterior.

`external_factors_v2` acrescenta seleção estruturada de horário de ocorrência
a partir de até quatro datas ISO explícitas com fuso no título/extrato. Sem
evidência, o tempo continua desconhecido; publicação e `endDate` não são proxies.
A relação com a janela configurada é derivada localmente sem nova inferência
por candle e sem alterar snapshots anteriores. Datas em linguagem natural ainda
ficam desconhecidas nesta implementação conservadora.

Gamma conserva pergunta/regras completas, IDs dos eventos, hash do conteúdo e
evidência/versionamento da associação. Um ID de evento isolado não confirma
acontecimento. O contrato local `poly_occurrence_literal_v1` verifica apenas a
mesma pergunta e regras completas literalmente iguais entre mercado/evento;
proposições idênticas não ganham grupos novos por terem IDs de evento diferentes.
Conjuntos mais amplos ou perguntas distintas ficam pendentes e não ocupam vagas.
Isso é identidade de proposição, sem data de ocorrência ou independência inferida.

Metadados inválidos, associação pendente ou unidades não verificadas falham antes
de solicitar livros/negócios/classificação. Os candidatos observados são limitados
pela descoberta; filtros e classificação precedem os tetos finais de mercados e
acontecimentos. Seleção é ordenada por relevância, relação temporal, idade, spread,
profundidade e ID, com auditoria em `prediction_selection`. Entre revisões 60m,
preços são atualizados somente para IDs acompanhados; falha não promove um novo ID.
Paginações sem avanço param e permanecem parciais.

Livros/negócios públicos compartilham slots duráveis por condição/token. Restart
reutiliza os horários originais. Variações descritivas de 5/60m só existem com livro
histórico realmente observado e disponível, identidade/frescor/spread válidos;
ausência de referência é `null`, nunca zero fabricado. Não representam chance de
lucro ou independência de participantes.

## Unidades e evidência primária

Rotas públicas acessadas: Gamma `/markets`, CLOB `/book`, Data `/v2/trades`.
Preço/timestamp/profundidade têm contratos explícitos; bare `size`/`volume` da
Data API v2 são cotas, campos `_usdc` são monetários. Eles não validam automaticamente
`liquidityClob` e `volume24hrClob` da Gamma. A leitura do
[CLI oficial](https://github.com/Polymarket/polymarket-cli/blob/main/src/output/markets.rs)
mostra formatação em dólares para `liquidityNum`, `volumeNum` e `volume24hr`;
isso sugere uso monetário desses campos, mas não comprova significado dos campos
CLOB, composição da liquidez ou contrato de janela requerido pelo filtro.
O [SDK oficial](https://github.com/Polymarket/py-sdk/blob/main/src/polymarket/models/gamma/market.py)
tipa métricas como Decimal, sem resolver essa semântica.

Produção mantém `GAMMA_METRIC_UNITS_UNVERIFIED`, fora dos sinais quantitativos.
Não foi inserida uma unidade presumida para fazer a integração parecer válida.
Fixtures com contrato conhecido verificam filtros, sem afirmar validação Gamma.
Referências: [livros públicos](https://docs.polymarket.com/market-data/prices-order-books),
[analytics](https://docs.polymarket.com/market-data/public-analytics),
[mercados/eventos](https://docs.polymarket.com/concepts/markets-events).
Proxy somente no ambiente local ignorado; sem credenciais neste relatório.

## Verificações concluídas

`uv run pytest -q`: **191 passaram**; `uv run ruff check .` e format limpos.
Um aviso de depreciação do TestClient Starlette/httpx permanece, sem falha.
Testes cobrem associação sem ID automático/regras longas, seleção de candidatos
válidos após os primeiros inválidos, composição entre revisões, paginação repetida,
janela ajustada, dedupe/proveniência/cutoff, deltas compartilhados e medição de idade.

Smoke integral BTC/ETH: oito ciclos/24 decisões, indicadores reais do módulo,
inferência por transporte simulado e orçamento isolado, B/C compartilhados,
quatro fills virtuais, oito ciclos duplicados ignorados, 45 labels amadurecidos e
três `UNAVAILABLE`; ledger OK. Todas as inferências/custos são simulados, zero rede.
Fixtures são excluídas de memória operacional/catálogo/dataset reutilizável.
O smoke padrão agora é `smoke-offline --scope pipeline`; `accounting` preserva E01.

`uv build` gerou wheel/sdist. Wheel instalado em venv limpa e CLI executada fora do
checkout com `--config /caminho/config/default.yaml`: smoke integral passou.
O YAML é configuração externa; a instalação do wheel não inclui o diretório do
checkout. Docker core/controle construídos; `docker compose config --quiet` válido.
Controle/TUI/WS reais e configuração do proxy TLS validada localmente estão
documentados nos relatórios E08/E09 e E10; certificado público não foi testado.

Recriações explícitas dos containers BTC/ETH em 21:54 e 21:56–21:57 UTC conservaram
bancos/bind mounts e orçamento/catálogo existentes. Hashes de carteiras/fills/ledger,
configuração, 27 decisões por sessão e watermarks permaneceram intactos na retomada;
auditoria OK, zero fills durante essa janela real. Sem remover volumes ou criar
capital novo. Imagem final dos motores:
`sha256:5336fbd8c0bd210bc557f326b2e93bc5fa15470aab11b1535fc538f74ce0b40d`.

Backup online BTC restaurado isoladamente em `/tmp/poc-e11-restored`: auditoria OK.
Reconstrução operacional marca orçamento/quota incertos e bloqueia IA/Marketaux
no dia UTC; não sobrescreve as bases atuais. Bancos distintos têm cortes próprios,
sem alegar transação conjunta.

## Dataset real

`data/datasets/e11-btc-real-r001.jsonl`: cinco exemplos BTC amadurecidos e 15 origens,
obtidos de cotações efetivamente coletadas. Labels contrafactuais não são fills ou
prova de inferência JEV válida. Importação inicial em `acceptance-v1-import-eth`
(sessão apenas preparada, não iniciada) aceitou cinco exemplos e preservou cada
carteira em 100 USDT; zero exemplos locais ETH. Os exemplos BTC ficam arquivados,
sem inflar mínimos locais ou ativar transferência automaticamente.

`data/datasets/e11-eth-accumulated-r002.jsonl` preservou cinco exemplos/15 origens
e ancestralidade do arquivo BTC, sem duplicação. Status de importação aceita
`ACTIVE` não é o estado `ACTIVE` de um padrão transferido. Gates de transferência
continuam exigindo amostras fonte e validação prospectiva não sobreposta.

## Observação em andamento

Prévia em `data/acceptance/v1-20261012`: início 19:47:37 UTC, 130 frames/~2h09,
zero falhas contábeis e zero amostras indisponíveis. Quatro alertas de idade
negativa vieram da captura do horário antes da leitura da segunda sessão; um
alerta coincidiu com reinício explícito. O observador foi corrigido para medir
idade após ler cada snapshot, sem ocultar timestamps realmente futuros. A prévia
ficou `INTERRUPTED`; todos os registros foram preservados.

Observação final da imagem congelada iniciou **12/10/2026 21:57:09 UTC**, em
`data/acceptance/v1-20261012-final`. Amostra inicial ETH estava retomando e ficou
degradada, registrada. Meta mínima **13/10/2026 21:57 UTC / 18:57 Brasília**.
Motor BTC/ETH e observador permanecem executando. `COMPLETED` indica tempo de
relógio transcorrido; aceite exige revisar saúde/cobertura/invariantes de todos
os registros. A estabilidade por 24h ainda não foi comprovada.

Após a retomada, ambos processaram o candle real de 22:00 UTC com três decisões
por sessão, WS ativo, quote fresca e clock VERIFIED. Cinco frames da observação
final em 22:01 UTC: zero falhas de invariantes/indisponibilidade; uma amostra
degradada inicial, demais recentes saudáveis. São evidências pontuais, não 24h.

O comando `observe` somente lê SQLite/Docker e grava seus artefatos. Verifica
ledger, capital, duplicidade por candle/carteira, horários da memória e da cotação
usada no fill, idade de quote/heartbeat, fontes/custos e imagem do runtime.
SIGTERM do observador não para motores. Invariantes financeiras e disponibilidade
do feed são reportadas separadamente; ausência de fonte/IA não é neutralidade.

Artefatos locais de evidência:

- `data/acceptance/v1-20261012/{samples.jsonl,observation.json,restart-proof.json,restart-proof-r002.json,real-dataset-import-proof.json}`.
- `data/acceptance/v1-20261012-final/{samples.jsonl,observation.json}`.
- `data/acceptance/v1-20261012-final/installed-smoke-proof.json`, pacote final
  instalado fora do checkout com configuração explícita.
- `data/backups/e11-running-acceptance-btc/manifest.json` e backups iniciais BTC/ETH.
- `data/sessions/acceptance-v1-{btc,eth}/poc.sqlite3`, logs e exports.
- `dist/ai_trade_memory-0.1.0{.tar.gz,-py3-none-any.whl}`.
- `/tmp/poc-e11-installed-smoke`, build/install logs e restauração isolada.

## Pendências para aceite

Resposta JEV autenticada válida não ocorreu: chave do ensaio respondeu 401 e o
circuito persistido evita repetição. Marketaux aguardará preenchimento local pelo
usuário. Contrato Gamma não verificado, classificação/associação semântica ampla
com resposta válida pendente, observação final 24h ainda em curso e TLS/hospedagem
públicos não testados. Transferência ACTIVE real/rentabilidade exigem dados futuros
suficientes; não são demonstradas por fixtures ou por cinco exemplos importados.
E03/E05/E11 permanecem abertos; nenhuma operação financeira real foi implementada.
