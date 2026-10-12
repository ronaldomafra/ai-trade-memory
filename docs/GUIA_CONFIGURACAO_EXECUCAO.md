# Guia de configuração e execução

Aplicação 0.1.0 · SPEC 1.50 · Atualizado em 12/10/2026.

Este roteiro configura o servidor, inicia motores Docker e conecta a TUI. Cada
sessão tem um par Spot USDT, banco próprio e três carteiras virtuais de 100 USDT.
O perfil disponível é `trend_15m_v1`: decisões em candles fechados de 15m,
tendência de 1h e duração máxima inicial de 16 candles. BTCUSDT e ETHUSDT são
exemplos; o par escolhido precisa existir na fonte pública Binance.

Todas as negociações são simuladas. A Binance fornece somente dados públicos;
configure credenciais de OpenRouter/Marketaux, sem chaves de corretora.
O processamento com JEV pode gerar cobrança real no OpenRouter.

Para a primeira execução, siga **Preparar o ambiente → Configurar credenciais →
Iniciar o controle Docker → Conectar a TUI**. As outras seções cobrem operação,
datasets, recuperação e acesso remoto. O [status](STATUS_DESENVOLVIMENTO.md)
registra o aceite e as integrações ainda pendentes.

## Preparar o ambiente

No servidor Linux, disponibilize Python 3.11+, uv, Docker Engine e o plugin Compose
(`docker compose`). O usuário que executa o projeto precisa acessar o daemon Docker
e escrever no diretório dos dados. O controle usa o socket local Docker para criar
motores; a TUI cliente precisa apenas da aplicação Python e de acesso à API.

Instalação das ferramentas: [uv](https://docs.astral.sh/uv/getting-started/installation/),
[Docker no Ubuntu](https://docs.docker.com/engine/install/ubuntu/) e
[plugin Compose no Linux](https://docs.docker.com/compose/install/linux/).

Execute os exemplos na raiz do checkout. Neste computador:

```bash
cd /home/ronaldo/projetos/pessoal/ai-trade-memory
uv --version
docker version
docker compose version
docker info --format '{{.ServerVersion}}'
uv sync --locked --python 3.11
uv run python -m poc --help
uv run python -m poc config-check
```

`config-check` deve retornar `"valid": true` e `"mode": "PAPER_ONLY"`.
Para verificar o pipeline sem rede, inferência ou cobrança:

```bash
uv run python -m poc smoke-offline --scope pipeline
```

O smoke cria uma sessão identificada como fixture e retorna seus caminhos,
auditoria e contagens. Ela não pode ser iniciada como motor de mercado real;
seus exemplos não entram no aprendizado operacional. A suíte de desenvolvimento:

```bash
uv run pytest -q
uv run ruff check .
```

## Configurar credenciais e diretório de dados

Crie o arquivo local se ainda não existir, preservando configurações anteriores:

```bash
cp -n .env.example .env
chmod 600 .env
```

Edite `.env` com um editor local. Exemplo com placeholders, sem credenciais reais:

```dotenv
OPENROUTER_API_KEY=
MARKETAUX_API_TOKEN=
POLYMARKET_PROXY_URL=
POC_DATA_DIR=./data
POC_CONTROL_PORT=18080
```

| Variável | Configuração |
| --- | --- |
| `OPENROUTER_API_KEY` | Chave válida do OpenRouter para inferência JEV. Sem ela, B/C mantêm diagnóstico de indisponibilidade e não executam entradas por IA. |
| `MARKETAUX_API_TOKEN` | Token da API gratuita Marketaux. Pode ficar vazio inicialmente; RSS continua disponível conforme cobertura. |
| `POLYMARKET_PROXY_URL` | Vazio para acesso direto; proxy opcional somente para Polymarket. Formato `http://USUARIO:SENHA@HOST:PORTA`. Caracteres reservados nas credenciais precisam de percent-encoding. |
| `POC_DATA_DIR` | Raiz usada pelos comandos locais. Exemplos deste guia usam `./data`. |
| `POC_CONTROL_PORT` | Porta do controle em Compose. Exemplos usam `18080`; a CLI nativa recebe a porta via `--port`. |
| `POC_HOST_DATA_DIR` | Caminho absoluto no host montado em `/data` do controle Docker. Definido nos exports da próxima seção. |
| `POC_UID`, `POC_GID`, `DOCKER_GID` | Identidades/permissão do container de controle, definidas nos exports. |
| `POC_PUBLIC_HOST` | Nome DNS próprio, necessário apenas no fluxo remoto com TLS. |

As quatro primeiras variáveis funcionais são lidas do `.env` na partida dos comandos
do servidor. Variáveis já exportadas no shell têm precedência. Compose também lê
o `.env`. A TUI não carrega as chaves dos provedores; autentica com usuário/senha/2FA.

Ao trocar credenciais, reinicie processos nativos e recrie containers com os mesmos
volumes, conforme **Atualizar código ou credenciais**. Um `docker restart` mantém
as variáveis antigas do container. Não coloque segredos em YAML, datasets ou logs.

### Verificar o JEV

Após configurar uma chave válida, o diagnóstico abaixo pode enviar **uma tentativa
física**, sujeito ao circuito e orçamento. Não opera carteiras; pode ser cobrado:

```bash
uv run python -m poc smoke-openrouter
```

Modelo/endpoint são fixos: `typesafe/jev-1.13` e
`POST https://openrouter.ai/api/alpha/decisions`. Não configure Chat Completions.
Confira `error_code`, `validation`, modelo efetivo, ID e custo retornados.
HTTP 401/402/403 abre circuito persistido da credencial; trocar uma chave inválida
é diferente de apagar o circuito/orçamento. O ensaio anterior respondeu 401;
uma resposta autenticada válida continua pendente.

## Escolher a pré-configuração da sessão

[config/default.yaml](../config/default.yaml) contém os defaults. A TUI apresenta
os campos permitidos no wizard; a CLI aceita um YAML próprio com `--config`.
Revise antes de criar a sessão, pois a retomada preserva a configuração aceita:

| Campo | Pré-configuração inicial |
| --- | --- |
| `strategy.max_allocation_pct` | `"20.0"`, máximo do patrimônio por compra. |
| `strategy.stop_loss_pct` / `take_profit_pct` | `"1.5"` / `"3.0"`. |
| `strategy.daily_loss_guard_pct` | `"5.0"`, trava por carteira até próximo dia UTC. |
| `strategy.max_holding_candles` | `16`, aproximadamente 4h no perfil inicial. |
| `simulation.trading_fee_pct_per_side` / `slippage_pct_per_side` | `"0.10"` / `"0.05"`. |
| `news.api_poll_minutes` / `poll_minutes` | `30` para Marketaux / `10` para RSS. |
| `news.lookback_hours` | `24`. |
| `polymarket.prices_poll_minutes` / `markets_poll_minutes` | `5` para preços/livros / `60` para descoberta/metadados. |
| `learning.initial_dataset_path` | `null` no YAML para iniciar sem dataset; na TUI, campo de arquivo opcional. |
| `learning.transfer.enabled` | `true`, condicionado aos gates de validação. |
| `ai.max_calls_per_day` / `max_observed_cost_usd_per_day` | `240` / `"0.05"`, limites globais. |

Os números de risco são parâmetros experimentais. Capital de 100 USDT por carteira,
modo paper, fonte pública e intervalos do perfil permanecem fixos. Campos desconhecidos
ou valores fora do contrato são recusados. Valores monetários/percentuais financeiros
devem ser strings decimais em YAML/JSON; contagens usam inteiros e flags usam booleanos.

## Iniciar o controle Docker

Execute esta etapa com a mesma raiz de dados que será usada pela CLI e pelos
motores. Os exemplos montam `data` do checkout; um diretório personalizado exige
ajustar os dois caminhos para apontarem à mesma raiz no host.

```bash
export POC_UID="$(id -u)"
export POC_GID="$(id -g)"
export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
export POC_DATA_DIR="$PWD/data"
export POC_HOST_DATA_DIR="$PWD/data"
export POC_CONTROL_PORT=18080
mkdir -p "$POC_DATA_DIR/operational" "$POC_DATA_DIR/learning"
docker build -t ai-trade-memory:0.1.0 .
docker compose --profile control build control_api
```

Na primeira configuração, crie o proprietário localmente:

```bash
uv run python -m poc bootstrap-owner --username meu-usuario
```

Informe uma senha de pelo menos 12 caracteres no prompt oculto. O comando exibe
seed/URI TOTP: cadastre-a em seu aplicativo autenticador. Guarde-a de forma privada;
não redirecione esse resultado para logs. O bootstrap não substitui um proprietário
já existente. Quem já o configurou deve usar sua conta atual.

Inicie somente o serviço de controle:

```bash
docker compose --profile control up -d control_api
docker compose --profile control ps control_api
curl --fail http://127.0.0.1:18080/health
```

`/health` verifica a API e a configuração do proprietário; não comprova saúde dos
motores. Um motor é provisionado quando uma sessão é iniciada. Os exports acima
valem para aquele shell; ao abrir outro, repita-os ou salve os valores operacionais
correspondentes no `.env` local.

## Conectar a TUI e iniciar uma sessão

Em outro terminal, na raiz do projeto:

```bash
uv run python -m poc tui --server http://127.0.0.1:18080
```

1. Informe usuário/senha e selecione **Entrar**.
2. Informe o código TOTP atual de seis dígitos e selecione **Validar 2FA**.
3. Selecione **Nova** ou pressione `N`.
4. Escolha `trend_15m_v1`, par `BTCUSDT` ou `ETHUSDT` e um identificador novo,
   por exemplo `btc-01`. Campo vazio permite ao servidor gerar o identificador.
5. Revise a pré-configuração JSON. Ajustes validados são aceitos antes da criação;
   percentuais monetários usam strings, como `"stop_loss_pct": "1.5"`.
6. Deixe dataset vazio para começar sem histórico ou informe um arquivo JSONL
   local da máquina que executa a TUI. Ela o envia ao servidor antes da partida.
7. Confira `learning.transfer.enabled` na pré-configuração e selecione
   **Criar e iniciar**.

O servidor consulta metadados públicos do par, prepara o banco, aceita o dataset
opcional e inicia seu container. Aguarde o aquecimento dos indicadores/candles.
Veja identidade, frescor, relógio, estados das fontes e motivos de HOLD no dashboard;
saldo inicial e ausência de trades não representam falha por si sós.

Selecione uma sessão existente e use **Retomar** ou `S` para iniciar seu motor
parado preservando banco/configuração/carteiras/histórico. Sessão nova cria outro
trio de 100 USDT; retomada não reinicia capital. O perfil e o par de uma sessão
existente não são trocados pela restauração.

| Tecla | Ação |
| --- | --- |
| `N` | Nova sessão e configuração inicial. |
| `S` | Iniciar/retomar a sessão selecionada. |
| `D` | Importar/exportar dataset. |
| `R` | Atualizar/reconectar os dados. |
| `L` / `O` | Login / logout. |
| `Tab` | Navegar pelos controles. |
| `?` | Ajuda. |
| `Q` | Sair da TUI. |

No login, modo somente leitura permite acompanhar sessões e impede comandos de
gestão. Tokens ficam na memória da TUI e são renovados pela API. **Sair da TUI,
fazer logout ou parar o controle não para os motores Docker.**

## Criar e operar sessões pela CLI

Alternativa ao wizard, usando os mesmos dados do servidor. Não precisa executar
novamente se essas sessões já foram criadas pela TUI:

```bash
uv run python -m poc prepare-session --profile trend_15m_v1 --symbol BTCUSDT --run-id btc-01
uv run python -m poc start-engine --run-id btc-01
uv run python -m poc engine-status --run-id btc-01
uv run python -m poc status --run-id btc-01
```

Para outro par, prepare outro banco:

```bash
uv run python -m poc prepare-session --profile trend_15m_v1 --symbol ETHUSDT --run-id eth-01
uv run python -m poc start-engine --run-id eth-01
```

Ambos compartilham orçamento/cache/catálogo, mantendo carteiras e memória local
separadas. O perfil inicial continua o mesmo; scalping, hold e outros estilos ainda
exigem implementação própria. A configuração efetiva e seu hash ficam no banco.

Para ajustar parâmetros por CLI, copie `config/default.yaml` para um YAML próprio,
edite antes da preparação e use `--config config/minha-sessao.yaml` em
`config-check` e `prepare-session`. A partida/retomada usa os valores aceitos no
banco; editar o template depois não altera aquela sessão. `POC_DATA_DIR` precisa
continuar apontando à raiz onde o banco foi preparado.

Parada explícita e retomada:

```bash
uv run python -m poc stop-engine --run-id btc-01
uv run python -m poc start-engine --run-id btc-01
```

### Usar os motores fixos do Compose

`compose.yaml` também oferece `engine_btc`/`engine_eth`, vinculados especificamente
a `session-btc`/`session-eth`. Prepare esses IDs antes de iniciar os serviços:

```bash
uv run python -m poc prepare-session --profile trend_15m_v1 --symbol BTCUSDT --run-id session-btc
uv run python -m poc prepare-session --profile trend_15m_v1 --symbol ETHUSDT --run-id session-eth
mkdir -p data/operational data/learning
docker compose --profile parallel up -d engine_btc engine_eth
docker compose --profile parallel ps
docker compose logs --tail 100 engine_btc
```

Esses serviços fixos usam `./data` do checkout. Não misture diretório personalizado
do controle com seus volumes fixos sem ajustar o Compose. Para parada/retomada
desses serviços, prefira `docker compose stop engine_btc` e
`docker compose up -d engine_btc`. Use apenas um supervisor por sessão.
Não execute simultaneamente motor nativo, serviço fixo e container dinâmico
para o mesmo banco.

## Importar exportar e transferir aprendizado

Sem dataset, a sessão começa sem memória inicial. Com dataset válido, somente C
pode usar exemplos compatíveis; importação não altera saldos, posições ou B.

Quando houver exemplos maduros na sessão fonte, exporte para um arquivo novo.
O comando não sobrescreve uma revisão existente:

```bash
uv run python -m poc export-learning --run-id btc-01 --output data/datasets/btc-r001.jsonl
```

Para importar por CLI, prepare a sessão e importe **antes de iniciá-la ou da
primeira decisão**:

```bash
uv run python -m poc prepare-session --profile trend_15m_v1 --symbol ETHUSDT --run-id eth-02
uv run python -m poc import-learning --run-id eth-02 --input data/datasets/btc-r001.jsonl
uv run python -m poc start-engine --run-id eth-02
```

O arquivo de entrada precisa existir e ter sido exportado pelo formato validado
do projeto. Também pode ser selecionado no wizard ou por
`learning.initial_dataset_path` no YAML antes da preparação. Na restauração, o
motor usa o conteúdo já aceito no SQLite, sem reler o arquivo.

Para gerar a revisão seguinte após uso/importação na sessão destino:

```bash
uv run python -m poc export-learning --run-id eth-02 --output data/datasets/eth-r002.jsonl
uv run python -m poc transfer-status --run-id eth-02
```

Na TUI, `D` abre importação/exportação com caminhos locais do cliente; download
verifica o hash. Dataset sem exemplos é válido quando ainda não há labels maduros.
Os horizontes iniciais são 4/16 candles; faltar bid válido na janela de maturação
produz `UNAVAILABLE`, fora da memória. Não use smoke/fixtures como aprendizado real.

Transferência automática publica exemplos maduros no catálogo compartilhado.
Dados BTC importados para ETH continuam com origem BTC; não aumentam os mínimos
locais ETH. Padrões estrangeiros exigem pelo menos 50 exemplos fonte não neutros e
30 avaliações futuras não sobrepostas na moeda destino, com Brier melhor que o
baseline salvo. Acompanhe os estados; importação aceita não garante transferência
`ACTIVE`. Regras completas em [TRANSFERENCIA_APRENDIZADO.md](TRANSFERENCIA_APRENDIZADO.md).

## Consultar saúde logs e resultados

```bash
uv run python -m poc engine-status --run-id btc-01
uv run python -m poc status --run-id btc-01
uv run python -m poc validate-data --run-id btc-01
uv run python -m poc report --run-id btc-01
uv run python -m poc export --run-id btc-01 --format all
docker compose --profile control logs --tail 100 control_api
```

`engine-status` descreve o container; `status` mostra dados financeiros, saúde e
cobertura. `validate-data` deve retornar `"ok": true` e lista de erros vazia.
Confira heartbeat recente, `quote_fresh`, relógio `VERIFIED`, atualização dos candles
e motivos das decisões. `ws_connected=false` pode coexistir com cotações REST
frescas; o que autoriza execução é validade/frescor, não conexão isoladamente.

Para logs de um container dinâmico, use o ID retornado por `engine-status`:

```bash
docker logs --tail 100 ID_DO_CONTAINER
```

| Caminho sob a raiz dos dados | Conteúdo |
| --- | --- |
| `sessions/RUN_ID/poc.sqlite3` | Banco canônico da sessão, finanças, decisões e aprendizado. |
| `sessions/RUN_ID/logs/AAAA-MM-DD/events.jsonl` | Eventos UTC projetados do SQLite. |
| `sessions/RUN_ID/exports/` | Dashboard JSON, fills, ledger, equity, decisões, custos e transferência CSV. |
| `operational/ai-budget.sqlite3` | Reservas, tentativas e custos globais JEV. |
| `operational/source-cache.sqlite3` | Coletas, quota, conteúdo e classificações reutilizáveis. |
| `learning/catalog.sqlite3` | Catálogo separado para transferência. |
| `control/` | Conta/2FA, comandos e registro de datasets do controle. |
| `datasets/` e `backups/` | Arquivos exportados e backups nos caminhos escolhidos. |

JSONL e exportações são reconstruíveis. Para reprojetar eventos:

```bash
uv run python -m poc export-events --run-id btc-01 --rebuild
```

### Diagnóstico de falhas

| Sintoma | Verificação e ação |
| --- | --- |
| TUI não conecta | Confira `/health`, porta, processo/serviço `control_api` e URL raiz, sem sufixo `/v1`. |
| 2FA rejeitado | Use novo código TOTP; sincronize relógio do servidor/celular. Código usado não pode ser reutilizado. |
| `Docker daemon is unavailable` ou permissão | Verifique `docker info`, acesso do usuário ao socket e `DOCKER_GID` do controle. |
| Banco ausente ou sessão não aparece | Confira `run_id` e a mesma raiz host/CLI/controle; prepare a sessão antes da partida. |
| Sessão já em execução/lock | Consulte supervisor/container atual; opere o mesmo motor e preserve o banco. |
| B/C só HOLD | Consulte `reason_code`, fontes/classificação, chave JEV, orçamento, indicadores e cotação. HOLD também é ação válida. |
| `AI_CIRCUIT_OPEN` / 401 | Corrija a credencial local e recrie/reinicie os processos; preserve orçamento/auditoria. |
| `AI_BUDGET_EXCEEDED` | Limite global atingido; registre cobertura e aguarde o próximo dia UTC. |
| `MARKETAUX_TOKEN_NOT_CONFIGURED` | Preencha o token local quando disponível; RSS continua com sua cobertura própria. |
| `GAMMA_METRIC_UNITS_UNVERIFIED` | Filtro conservador atual; reduzir o piso não valida a unidade dos dados. |
| Memória/transferência insuficiente | Aguarde exemplos maduros e validação; não force ativação. |
| Importação recusada | Confira primeira decisão, schema/hash, cutoff, compatibilidade e tamanho máximo de 64 MiB. |
| Imagem mudou e start foi recusado | Recrie o container parado preservando volumes, conforme seção de atualização. |

Recuperação do autenticador é local no servidor e revoga tokens anteriores:

```bash
uv run python -m poc reset-owner-2fa --username meu-usuario
```

## Fazer backup e restaurar

Faça backup online pelo comando do projeto, inclusive com motor ativo:

```bash
uv run python -m poc backup --run-id btc-01 --output data/backups/btc-01-r001
```

Use um destino novo. O backup inclui banco da sessão e bases operacionais/catálogo
existentes, com hashes e auditoria. Cada SQLite tem seu corte consistente próprio;
uma cópia comum do arquivo ativo não substitui esse procedimento. A pasta de
autenticação `control` e o `.env` não integram esse backup de sessão.

Restaure em uma raiz separada, preservando o mesmo identificador:

```bash
POC_DATA_DIR="$PWD/data-restaurada" uv run python -m poc restore-backup \
  --run-id btc-01 --input data/backups/btc-01-r001
POC_DATA_DIR="$PWD/data-restaurada" uv run python -m poc validate-data --run-id btc-01
POC_DATA_DIR="$PWD/data-restaurada" uv run python -m poc status --run-id btc-01
```

Destino existente é recusado. Se o orçamento operacional precisar ser reconstruído,
novas chamadas JEV/Marketaux ficam bloqueadas naquele dia UTC por capacidade
incerta; risco e fontes públicas continuam. Valide a recuperação antes de substituir
o serviço parado; não inicie outra cópia do mesmo `run_id` em paralelo.

## Atualizar código ou credenciais

Preserve a raiz dos dados e faça backup. Após atualizar o checkout:

```bash
uv sync --locked --python 3.11
docker build -t ai-trade-memory:0.1.0 .
docker compose --profile control build control_api
docker compose --profile control up -d --force-recreate control_api
```

Os motores já existentes continuam usando a imagem/ambiente com que foram criados.
Para um motor dinâmico, pare explicitamente, confirme o ID e remova **apenas seu
container parado**, preservando os bind mounts/bancos:

```bash
uv run python -m poc stop-engine --run-id btc-01
uv run python -m poc engine-status --run-id btc-01
# Substitua pelo container_id da sessão; running deve ser false.
docker rm ID_DO_CONTAINER
uv run python -m poc start-engine --run-id btc-01
uv run python -m poc validate-data --run-id btc-01
```

O próximo start recria o container com a imagem local e variáveis atuais. Execute
os comandos no servidor com a configuração local atual; não remova os diretórios
de dados nem os bancos de orçamento/cache para contornar falhas.

Serviços fixos usam o próprio Compose para recriação:

```bash
docker compose up -d --force-recreate engine_btc
docker compose --profile parallel up -d --force-recreate engine_eth
```

Recriar/parar o controle não recria os motores dinâmicos. Ao atualizar uma sessão
parada, o runtime rejeita container de imagem antiga até sua recriação.

## Conectar de outro computador

O controle remoto exige HTTPS/WSS; HTTP simples é aceito apenas em loopback.
Configure um domínio próprio apontando ao servidor e disponibilize as portas
TCP 80/443 para o proxy TLS. Motores e socket Docker permanecem acessíveis somente
no servidor.

Com os exports/permissões do roteiro Docker, substitua o domínio abaixo:

```bash
export POC_PUBLIC_HOST=jev.seudominio.example
export POC_CONTROL_PORT=18080
docker compose --profile control --profile remote up -d control_api tls_proxy
```

O Caddy encaminha ao controle em `127.0.0.1:18080`. Configure DNS/TLS do domínio
real antes do uso externo; `.example` é placeholder. A configuração do proxy foi
validada localmente, mas hospedagem/certificado públicos ainda não foram testados.
Condições de emissão/renovação em [Caddy HTTPS automático](https://caddyserver.com/docs/automatic-https).

No computador cliente, instale as dependências Python do projeto e conecte:

```bash
uv run python -m poc tui --server https://jev.seudominio.example
```

Use login e 2FA da mesma conta. O cliente não precisa de Docker, acesso ao banco ou
chaves dos provedores. REST cuida de comandos/snapshots/datasets e WebSocket traz
eventos/atualizações, com reconexão e renovação de token automáticas. Detalhes em
[API_CONTROLE_V1.md](API_CONTROLE_V1.md).

## Executar diretamente no terminal ou com systemd

Alternativa para execução nativa, sem Docker para aquele motor:

```bash
uv run python -m poc run --new-session --profile trend_15m_v1 --symbol ETHUSDT --run-id eth-local-01
```

O processo ocupa o terminal. `Ctrl+C` encerra o motor nativo; retome sem reset:

```bash
uv run python -m poc run --resume eth-local-01
```

Para API privada de diagnóstico, acrescente `--serve --host 127.0.0.1 --port 8081`.
Essa API de motor não é a API autenticada de controle para a TUI. O comando
`stop-engine` administra Docker; motor nativo é encerrado pelo processo/supervisor.

Há um template em [deploy/jev-paper-trading@.service](../deploy/jev-paper-trading@.service).
Antes de instalar, ajuste usuário, `WorkingDirectory`, `ExecStart`, `EnvironmentFile`
e `ReadWritePaths` para a localização do projeto/dados. O template usa `/opt` e
`ProtectHome=true`; para um checkout sob `/home`, precisa adaptar essa proteção ou
instalar o projeto em `/opt`. Depois de preparar o banco da sessão:

```bash
sudo cp deploy/jev-paper-trading@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jev-paper-trading@eth-local-01
sudo journalctl -u jev-paper-trading@eth-local-01 -f
sudo systemctl stop jev-paper-trading@eth-local-01
```

Use um único supervisor por sessão. Para o fluxo principal TUI/lifecycle, use
os motores Docker; systemd nativo é alternativa operacional com configuração própria.

## Observar a execução e entender os limites atuais

O orçamento JEV é global: até 240 tentativas e US$ 0,05 de custo observado por dia
UTC, incluindo classificação/retries e todas as sessões. Duas sessões não dobram
o orçamento. Custo ausente fica desconhecido; esse teto observado não garante uma
fatura máxima quando o provedor não informa cobrança. Marketaux tem quota compartilhada
de até 100 requisições diárias no contrato gratuito implementado.

Para coletar evidência periódica sem parar motores ou enviar inferências, use
uma pasta nova e mantenha o processo do observador ativo:

```bash
uv run python -m poc observe --run-id btc-01 --run-id eth-01 \
  --output data/acceptance/meu-ensaio-r001 --duration-hours 24 --poll-seconds 60
```

`observation.json` acompanha progresso e `samples.jsonl` registra saúde/auditoria.
Parar esse observador não para os motores. `COMPLETED` indica tempo decorrido;
revise degradações, fontes, custos e invariantes antes do aceite.

Na revisão de 12/10/2026: 191 testes passaram; aceite de 24h ainda em andamento,
JEV autenticado respondeu 401, Marketaux aguarda token local e unidades Gamma
ainda não permitem sinais quantitativos. Sem fatores externos utilizáveis,
entradas B/C ficam bloqueadas; A e proteção continuam conforme dados válidos.
Não há prova de rentabilidade ou transferência ACTIVE real. Referência:
[validação E05/E11](relatorios/VALIDACAO_E05_E11.md).
