# API de controle e protocolo WebSocket V1

Implementação E08/E09. Paper Spot somente; o serviço de controle não é broker.
Banco por sessão e transações do motor continuam canônicos. A TUI usa apenas REST/WS.

## Transporte e proprietário

HTTP/WS somente em loopback; acesso remoto exige HTTPS/WSS. Gateway escuta em
127.0.0.1 por padrão, com Uvicorn confiando em cabeçalhos encaminhados apenas de
127.0.0.1/::1. O proxy TLS do servidor encaminha para essa porta. Motores não são
publicados externamente. Nenhuma senha, TOTP ou token aparece em URL.

Proprietário criado localmente com `bootstrap-owner --username NOME`; senha via
prompt oculto ou arquivo privado `--password-file`. Sem senha padrão, cadastro
remoto ou substituição pelo bootstrap. Senha Argon2; seed TOTP guardada no banco
de autenticação, diretório 0700/arquivo 0600, separado dos volumes dos motores.
O CLI inicial exibe a seed/URI apenas para configurar seu autenticador: não
guardar esse resultado em relatório/log público. Recuperação local:
`reset-owner-2fa --username NOME` troca seed e revoga as credenciais anteriores.

Login: POST /v1/auth/login com username/password e scopes read/manage e sessions
(default proprietário: `['*']`); retorna challenge_token válido por dois minutos.
POST /v1/auth/2fa com challenge_token/code emite access_token e refresh_token.
TOTP tem janela ±1 passo e rejeita reutilização; login/2FA dividem limite de dez
tentativas por origem a cada cinco minutos. Acesso 15 minutos, refresh sete dias,
família até 30 dias. POST /v1/auth/refresh rotaciona ambos; reuso do refresh antigo
revoga a família. POST /v1/auth/logout revoga família, sem parar motor. Tokens
persistidos apenas por hash. REST usa `Authorization: Bearer TOKEN`.

## REST

OpenAPI em /openapi.json; sem frontend HTML/Swagger. As leituras de sessão usam
SQLite somente leitura; migração é operação de preparação/partida local.

| Método/rota | Função |
| --- | --- |
| GET /health | Serviço/API/proprietário inicializado, sem credenciais |
| GET /v1/profiles | Perfil implementado, template e schema |
| GET /v1/sessions | Sessões autorizadas, reconstruídas dos bancos |
| POST /v1/sessions | Preparar perfil/par/ajustes/dataset opcional |
| POST /v1/sessions/{run_id}/start | Iniciar/retomar Docker, sem reset |
| POST /v1/sessions/{run_id}/stop | Parada explícita do motor |
| GET /v1/sessions/{run_id}/snapshot | Estado consistente e event_watermark |
| GET /v1/sessions/{run_id}/events | Histórico, after_seq ≥0, limit até 10000 |
| GET /v1/sessions/{run_id}/configuration | Configuração pública persistida, somente leitura |
| GET /v1/sessions/{run_id}/transfer | Estados/contagens de transferência |
| GET/POST /v1/datasets | Listar/enviar JSONL validado, proprietário global |
| GET /v1/datasets/{dataset_id} | Download por hash, sem caminhos arbitrários |
| POST /v1/sessions/{run_id}/learning/import | Importação inicial idempotente, antes da primeira decisão |
| POST /v1/sessions/{run_id}/learning/export | Exportar acervo válido e registrar arquivo imutável |

Preparar/start/stop exigem `Idempotency-Key`, 8–128 caracteres ASCII alfanuméricos,
underscore/hífen. A chave é persistida por proprietário; reuso com corpo diferente
é rejeitado. Repetir comando incerto com a mesma chave/corpo, sem criar novo
capital. Resposta de comando já concluído é sua resposta original, não consulta
do estado atual; consultar snapshot para o estado atual.

Preparação aceita profile_id trend_15m_v1, symbol Spot USDT, run_id opcional,
overrides e dataset_id registrado opcional. Defaults são mergeados recursivamente.
Endpoints/modelo/armazenamento/capital/modo real não são parâmetros remotos.
Valores financeiros são strings decimais. Sem edição intrassessão.

Upload até 64 MB, JSONL/schema/hash/protocolo/cutoff válidos. Fixture/futuro não
entra no aprendizado operacional. Import não muda carteiras ou B. Export não
garante amostras suficientes; zero exemplos é válido. Erros não ecoam senha,
TOTP, token ou valores inválidos de configuração.

## WebSocket /v1/stream

Autenticar na primeira mensagem em até cinco segundos, sem query string:

```json
{"type":"authenticate","access_token":"TOKEN","subscriptions":[{"run_id":"minha-sessao","after_seq":42}]}
```

Até oito sessões autorizadas por conexão; 32 conexões no processo e quatro por
proprietário. Frame de entrada até 16 KiB; controle posterior apenas
`{"type":"ping"}`, até 1 KiB. Frames de saída até 1 MiB, envio com prazo de dois
segundos. Fila de entrada do transporte limitada a oito. Sem fila ilimitada de
eventos por cliente; lotes até 100 por sessão e consulta a cada 0,5s. Cliente
lento desconecta; os eventos persistidos continuam disponíveis para replay.

| type | Conteúdo/semântica |
| --- | --- |
| snapshot | Snapshot consistente, quando after_seq omitido/null |
| ready | Cursors por run_id aceitos |
| event | Evento SQLite com run_id/event_id/event_seq; entrega pelo menos uma vez |
| live | Cotação/saúde/ciclo/última etapa observável, durable=false; aproximadamente 1s |
| pong | Resposta ao ping de aplicação |
| resync_required | Buscar snapshot REST novo antes de continuar |

Fluxo preferido: GET snapshot → guardar event_watermark → assinar depois desse
cursor → aplicar eventos por event_id/seq. Eventos criados durante o handoff
entram no replay. Cliente ignora duplicatas e exige sequência contínua, sem
misturar sessões. Cursor futuro, histórico removido ou lacuna exigem resync;
não completar com eventos inventados. Ticks/progresso efêmeros não avançam cursor.
Cliente incluído reconecta com backoff de 1 a 30s, ping/pong do transporte e
refresh serializado; cursor em memória, snapshot novo ao abrir outra TUI.

Expiração/revogação rechecadas durante a conexão: close 4001 para reautenticar,
4003 para falta de permissão (não repetir refresh), 4009 para resync, 1013 para
sobrecarga/cliente lento, 1008 para requisição inválida. Nunca transmitir
raciocínio interno do modelo. GET/renderização/assinatura não fazem inferência,
ordem ou reset. Logout, fechar gateway e perder rede não param os motores.

## Evidência e referências

Testes de permissões/auth/refresh/replay/cutoff/backpressure e API/TUI no projeto.
Ensaios locais reais em [validação E08/E09](relatorios/VALIDACAO_E08_E09.md).
Domínio público/certificado/hospedagem externa e estabilidade 24h são E11.

Documentação primária usada: [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/),
[Uvicorn](https://www.uvicorn.org/settings/),
[Argon2](https://argon2-cffi.readthedocs.io/en/stable/howto.html),
[PyOTP](https://pyauth.github.io/pyotp/).
