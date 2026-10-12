# Validação E08/E09 — controle e eventos

12/10/2026, versão 0.1.0. SPEC 1.50. Sem operações financeiras reais.

Implementados gateway FastAPI versionado, proprietário local, Argon2/TOTP,
desafios de login, tokens por hash/expiração/rotação/revogação e escopos por
sessão. Preparação/lifecycle idempotentes; templates/ajustes validados antes
de banco/inferência. Dataset por identificador/hash, upload limitado, import
inicial e export imutável. REST lê o banco somente leitura; schema antigo exige
migração explícita. CLI serve-control/control-api/bootstrap-owner/reset-owner-2fa.

WS autenticado em frame inicial, replay SQLite/cursor/identidade/seq, snapshot
com watermark e resync. Fluxo live separado, rechecagem de autenticação, limites
de conexões/frames/lotes/tempo. Cliente REST/WS tem backoff, dedupe e refresh
serializado, sem acesso broker/Docker/SQLite. Contratos e comandos em
[API_CONTROLE_V1.md](../API_CONTROLE_V1.md).

Suíte conjunta após integrar a TUI: 162 testes; ruff limpo. Testes cobrem
Argon2/2FA/replay/expiração/escopos/logout, criação concorrente/comando repetido,
datasets/financeiras preservadas, readonly, URL/TLS, replay/duplicação/lacuna,
revogação durante WS e cancelamento do envio de cliente lento.

Ensaio nativo real em raiz isolada /tmp/poc-v1-gateway-verification, sem JEV ou
Marketaux autenticados: login 200, TOTP 200, retomada Docker 200 da sessão
gateway-runtime-btc; snapshot/run_id corretos, watermark 20, frames ready/live.
Logout 200, WS fechou 4001, REST com token revogado retornou 401. Após SIGTERM do
gateway, Docker ainda reportou running=true; encerramento posterior do controle
em container também preservou o motor. Não confundir isso com ensaio 24h.

Imagem de controle construída de base comum + CLI Docker; docker --version
funcionou dentro dela. Controle em container Linux/host network com bind da
raiz isolada, socket e GID do host leu engine-status e /health retornou 200.
Porta 8080 já ocupada por outro projeto; ensaio usou 18082. Nenhum serviço
preexistente foi parado. Caminho host/internal dos bind mounts foi testado.
Compose aceita POC_CONTROL_PORT e valida sem ativar perfis opcionais.

Caddyfile validado com imagem oficial caddy:2: Valid configuration. Isso é prova
de configuração, não publicação/domínio/certificado externo. Artefatos de
ensaio em /tmp/poc-e09-live-proof.json, logs sem access logging, screenshots
da TUI na pasta deste relatório. Segredos de ensaio em arquivos locais 0600;
nenhum valor incluído neste documento. Não foi criado proprietário de produção.

Pendências: hospedagem pública/TLS real, provas prolongadas/24h e credenciais
externas. JEV real permanece 401 do ensaio E03; token Marketaux adiado pelo
usuário. Não houve classificação semântica real válida, ativação transferida
real nem prova de rentabilidade.
