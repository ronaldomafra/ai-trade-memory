# Orçamento JEV por bot — D059

14/10/2026 · SPEC 1.57. Usuário definiu limites próprios por estratégia/perfil,
em vez de um teto global que pudesse bloquear os outros bots.

## Resultado

Perfis cadastráveis têm `ai.budget_scope=SESSION`, `max_calls_per_day`,
`cost_limit_enabled` e `max_observed_cost_usd_per_day`. Defaults continuam
240 chamadas, US$ 0,05 e guarda financeira habilitada, agora por bot, editáveis
no perfil ou antes de criar a sessão. Não há clamp global de 240/US$ 0,05.

Cada sessão recebe cópia imutável dos parâmetros. Mesmo perfil em duas sessões
não mistura os contadores. Alterar revisão publicada não reconfigura sessão
existente; retomada não zera consumo. Total geral é relatório, não teto comum.

Reservas transacionais e recibos por run_id no SQLite operacional, com hash da
política. Decisão, classificação e retries físicos entram no pagador; reuso e
compartilhamento B/C não somam outra despesa. Falha de orçamento do pagador não
envenena a classificação compartilhada para outro bot com capacidade.

Novas sessões de perfis cadastráveis anteriores recebem a configuração SESSION
na cópia efetiva, sem reescrever o catálogo. Union explícita no schema conserva
os campos/hashes antigos durante restore. Legado mantém sua política anterior,
separada dos novos bots; não se permite downgrade para contornar uma política
SESSION já vinculada. Bloqueio de recuperação incerta e circuito de credencial
continuam proteções independentes.

TUI permite editar `ai` e mostra chamadas/custo do dia UTC do bot. API:
GET `/v1/sessions/{run_id}/ai-budget`; GET `/v1/ai-budget` é agregado.
PUT global retorna 409; compatibilidade antiga tem endereço explícito
`/v1/legacy-ai-budget`. CLI `ai-budget --run-id ID` consulta somente leitura
do banco da sessão; sem ID mostra agregado. Flags de alteração antigas exigem
`--legacy-global` e não interferem nos novos bots.

## Verificação

- **297 testes passaram em 37,68s**, com um aviso de depreciação Starlette/httpx.
  Após o último ajuste de leitura readonly na CLI, **12 testes direcionados
  passaram em 1,72s**. Ruff check/format e diff limpos.
- Novos testes verificam disputa concorrente, isolamento por bot, limites acima
  de 240, custo independente, toggle financeiro, crash/replay, desconhecidos,
  mudança UTC, imutabilidade, recuperação e rejeição de downgrade de escopo.
- Integração verifica configuração no perfil e overrides de sessão, permissões
  de leitura por sessão, retirada da escrita global e uso de cadastro antigo
  sem reescrever definição/hash. TUI publica parâmetros de orçamento editados.
- Classificação com HTTP simulado comprova que um bot esgotado não bloqueia
  outro e que o cache resultante pode ser reutilizado sem nova chamada.
- Docker `--network none` carregou/validou os três templates `.3`, com
  orçamento SESSION. Não foram necessárias chamadas pagas aos provedores.

Gasto real USD continua separado do resultado paper USDT. Custo observado não
garante teto absoluto de fatura com chamadas em voo ou cobrança desconhecida.
Nenhuma previsão de lucro cobrindo IA, nem aumento automático por PnL.

## Implantação e preservação

Controle atualizado às **19:37:32 UTC**, `/health` HTTP 200.

- Imagem controle: `sha256:9499a7a928fdddf978499e32de83d0bdde106a668c0e3b3edc2cfd8d3a82e8ee`.
- Imagem de novos motores: `sha256:45b90f6fa49a76dddf67c0eb0d6af7bf6d203b9b2d256b572c956f080831f66f`.
- Backup: `data/backups/before-session-ai-budgets-20261014T193726Z/`, seis bancos
  SQLite individualmente consistentes. Diretórios 0700, arquivos 0600; sem
  alegação de atomicidade entre bancos. `evidence.json` guarda contagens/hashes.
- Comparação pós-atualização: linhas anteriores idênticas em runs/decisions/
  outcomes/fills/ledger/ai_calls da ETH, tentativas/políticas/recibos/circuitos
  do orçamento e versões/eventos do catálogo. Auditoria ETH OK; schema 7 já
  existia no backup imediatamente anterior à implantação.
- O perfil publicado `scalping_zec_v1` revisão 1 continua intacto. Cópia de
  configuração para a próxima sessão validada com SESSION, sem criar sessão.
  Continua somente `eth-01`, parada. Nenhum novo bot foi iniciado.

Login autenticado na TUI operacional não foi executado pelo agente: credenciais
do proprietário foram preservadas, e fluxos API/TUI usaram fixtures isoladas.
Reabrir a TUI carrega os novos campos. [Guia](../GUIA_PERFIS_BOTS.md).
