# Cadastrar perfis e criar bots pela TUI

**D057–D060 · SPEC 1.58 · 14/10/2026.** Motor genérico, sessão persistida por bot,
controle por REST/WSS e execução exclusivamente em paper trading.

## Estado desta atualização

A sessão `eth-01` foi parada por solicitação do usuário para interromper novas
chamadas pagas. Banco e histórico foram preservados; existe backup anterior à
atualização em `data/backups/before-generic-profiles-20261014T165613Z/`.
Nenhum perfil, moeda ou novo bot foi escolhido/iniciado automaticamente.
Resultados operacionais não comprovam eficiência financeira do JEV.

## Cadastro pela TUI

Feche a TUI antiga e abra a versão atualizada:

```bash
uv run python -m poc tui --server http://127.0.0.1:18080
```

1. Entre com o proprietário e o código 2FA do autenticador.
2. Abra **Perfis**, pelo botão ou tecla **P**.
3. Escolha um template completo: day trade, swing ou scalping. Para duplicar
   ou revisar um cadastro, selecione o perfil existente na mesma lista.
4. Preencha ID, nome, revisão e par padrão. Outro ID cria um perfil distinto;
   mesmo ID com revisão maior cria uma evolução. Publicações anteriores não
   são sobrescritas.
5. Escolha estilo e família de entrada. As famílias implementadas são
   **rompimento de máxima anterior**, **cruzamento de EMAs** e **alinhamento
   de EMAs**. Alterar a família ajusta os campos estruturais; revise também
   as instruções do JEV.
6. Edite os **parâmetros e instruções em JSON**. O template é completo; a aba
   de referência apresenta o schema usado pelo servidor. Campos protegidos
   continuam sujeitos à validação. Use números financeiros como strings:
   `"0.35"`, por exemplo, significa 0,35%, não 35%.
   Os textos de `jev_instructions` devem ser escritos em **inglês**, conforme
   a orientação oficial sobre melhor precisão do JEV; os novos templates já
   vêm traduzidos e versionados. Nome do perfil e interface podem ficar em
   português. Recarregue o template se abriu a tela antes da atualização D058.
7. Clique **Validar**. Revise intervalo, tendência, duração máxima, horizontes
   e quantidade máxima de ciclos. Alterar valores depois dessa prévia exige
   nova validação.
8. Clique **Salvar e publicar**. O servidor registra DRAFT e publica a revisão
   para paper, com auditoria e comandos idempotentes. **Publicar não inicia
   nenhum bot e não faz chamadas ao JEV.**

Os controles ficam em uma tela com rolagem; Tab também move o foco até os
botões inferiores. O editor é explícito em JSON nesta POC, não um formulário
separado para cada um dos numerosos campos do template.

Um template ajuda a configurar, mas não cria um algoritmo por texto livre.
Família desconhecida é recusada; uma família adicional exige implementação e
testes. Hold segue fora da entrega atual.

## Criar o bot a partir de um perfil

1. Abra **Nova** e selecione o perfil/revisão publicado. Drafts e revisões
   arquivadas não aparecem como opções de partida.
2. Escolha o par Spot USDT, que pode ser diferente do par padrão do perfil.
3. Escolha um identificador de sessão novo, revise a pré-configuração e
   faça os ajustes desejados antes de iniciar.
4. Dataset inicial é opcional: campo vazio inicia sem dataset; um arquivo
   compatível é enviado ao servidor para validação/importação. Observações
   incompatíveis podem permanecer arquivadas sem entrar na memória ativa.
5. **Criar e iniciar** prepara o banco e aciona o motor Docker. É esta ação
   que começa a operação e pode consumir IA conforme oportunidades, fontes e
   orçamento deste bot. A escolha da moeda e essa partida serão feitas com o
   usuário depois da implementação.

Cada bot/sessão continua com três carteiras independentes A/B/C de 100 USDT.
O perfil orienta as três; B usa JEV, C acrescenta somente memória compatível
e já amadurecida. Não há compra, venda, saldo ou ordem financeira real.

Uma revisão/configuração é copiada integralmente para a sessão, com hash,
instruções, parâmetros originais e ajustes. Alterar/publicar/arquivar o
catálogo não reconfigura um bot existente. Para experimentar parâmetros
novos, crie outra sessão. Restore depende da cópia salva e da capacidade
da imagem, não da disponibilidade do catálogo.

## Acompanhar e parar

**D060 — prazo do scalping:** em `app`, alterar o campo existente
`max_candle_decision_lag_seconds` de 8 para 15, sem duplicar a chave. Preservar
`ai.timeout_seconds=6`. O servidor atualizado aceita até 15s para SCALPING;
um servidor anterior retorna 422. Isso não muda candles 1m/tendência 5m nem
cadência mínima de 300s. Publicar nova revisão e criar nova sessão; a antiga
mantém a configuração original e pode ficar parada com todo o histórico.

- Dashboard identifica o intervalo correto do gráfico e da tendência.
  Decisões mostram proposta/execução e os motivos registrados.
- Configuração mostra os valores efetivos preservados no servidor.
- **Parar** interrompe o motor selecionado, preservando histórico e capital.
  Fechar a TUI ou sair da conta mantém motores em execução.
- **Retomar** usa o estado/configuração persistidos. Um container antigo cuja
  imagem mudou precisa ser recriado preservando os volumes, conforme o guia
  de atualização existente; não reutilizar imagem antiga com schema novo.
- O orçamento JEV é definido no perfil e copiado para cada bot. Chamadas,
  classificações e retries contam no dia UTC da sessão pagadora. O consumo de
  uma sessão não bloqueia outra. A política D053 é apenas compatibilidade de
  sessões antigas, sem governar os novos bots.

## Limites de IA por perfil e bot

Na seção `ai` do editor de perfil ou da pré-configuração de **Nova**, ajuste:

```json
"budget_scope": "SESSION",
"max_calls_per_day": 1000,
"cost_limit_enabled": true,
"max_observed_cost_usd_per_day": "0.50"
```

São **exemplos**, não valores aplicados automaticamente. Preserve os outros
campos de `ai`, incluindo modelo, endpoint, timeout e retries. Chamadas são um
inteiro positivo; custo em USD é texto Decimal positivo; `false` desativa somente
a trava financeira. Não existe mais o teto global oculto de 240/US$ 0,05 para
SESSION. Os defaults dos templates continuam 240 e US$ 0,05 por bot, editáveis.

O perfil define os padrões; ajustes em **Nova** valem somente para essa sessão.
Para mudar o padrão de um perfil publicado, crie outra revisão. Bots existentes
preservam seus snapshots. Duas sessões do mesmo perfil têm contagens próprias.
O perfil ZEC já publicado pode ser usado em **Nova**: o controle fornece os
campos SESSION para a nova configuração sem reescrever o cadastro anterior.
Reabra a TUI após atualizar o controle para carregar esses campos no editor.

Consulta local: `uv run python -m poc ai-budget --run-id zec-scalp-01`.
Sem `--run-id`, `ai-budget` mostra total agregado e detalhamento de bots vinculados;
não é mais um limite financeiro compartilhado. API:
`GET /v1/sessions/{run_id}/ai-budget`; `GET /v1/ai-budget` agregado.
PUT no endereço global retorna 409 e orienta configurar o perfil/sessão.
Somente o contrato legado usa `--legacy-global`/`/v1/legacy-ai-budget`.

Reuso de cache não gera despesa nova. O custo de uma requisição física
compartilhada B/C é contabilizado uma vez. Custos desconhecidos permanecem
identificados; não há garantia de teto absoluto da fatura para chamadas em voo.
Marketaux mantém a cota real da conta gratuita, independentemente dos limites JEV.

## Defaults e controles comuns

| Template | Candle / tendência | Stop / take | Posição máxima | Avaliações admitidas |
|---|---|---|---|---|
| Day trade | 15m / 1h | 1% / 2% | 8h | Até 96/dia UTC |
| Swing | 4h / 1d | 4% / 8% | 14 dias | Até 6/dia UTC |
| Scalping | 1m / 5m | 0,35% / 1,20% | 15min | Setup local ou posição; espaçamento 300s; até 80/dia UTC |

São pré-configurações experimentais editáveis dentro do schema, sem garantia
de lucro ou número de operações. O estilo declara o horizonte; parâmetros
e famílias implementadas determinam o comportamento efetivo.

Novas compras exigem setup estrutural também em B/C, além de seus próprios
fundamentos/thresholds, cotação fresca e regras de risco. A possui confirmações
técnicas adicionais. Stops, take, duração e fechamento de agenda rodam sem
depender da resposta do JEV. Fechamento sem cotação fica pendente, bloqueando
entradas até resolução; não inventa preço.

O filtro de execução verifica spread, desvio do ask durante a inferência,
quantidade quantizada e cenários líquidos calculados pelo mesmo paper broker.
A prévia rejeita uma relação alvo/stop inviável mesmo no cenário sem spread;
o teste com a cotação real é repetido na entrada. Isso não é valor esperado.

Notícias e Polymarket seguem cadências próprias e a reutilização D055.
Interpretação semântica dos novos perfis usa escopo de evidência por ativo;
relação temporal usa a duração efetiva, limitada pela agenda. Texto de fonte
externa nunca funciona como instrução para o bot.

## CLI equivalente

```bash
uv run python -m poc profile-template --style daytrade --output meu-perfil.yaml
# Editar ID, nome, parâmetros e instruções no arquivo.
uv run python -m poc profile-validate --input meu-perfil.yaml
uv run python -m poc profile-register --input meu-perfil.yaml
uv run python -m poc profile-publish --profile meu_perfil --version 1
uv run python -m poc profiles
# A preparação ainda não inicia o motor:
uv run python -m poc prepare-session --profile meu_perfil --profile-version 1 --symbol SOLUSDT --run-id novo-bot
```

O ID `meu_perfil` deve corresponder ao arquivo editado. O símbolo acima é
apenas exemplo; não foi escolhido para uma execução nesta atualização.
YAML limitado a 128 KiB, sem aliases, anchors ou tags executáveis. O comando
de exportação não sobrescreve arquivo existente.

API correspondente: `GET /v1/profile-template?style=DAY_TRADE`,
`POST /v1/profiles/validate`, `POST /v1/profiles`,
`POST /v1/profiles/{id}/versions/{version}/publish`,
`POST /v1/profiles/{id}/versions/{version}/archive` e criação de sessão existente.
Mutações do catálogo exigem proprietário com escopo global/manage e login 2FA;
comandos persistentes exigem Idempotency-Key. GET e validação não fazem inferência.

## Compatibilidade e limites de validação

- Configuração e labels V1 preservados; runtime V2 tem schema próprio. Novos
  labels registram intervalo/duração e janela de cotação; datasets V1 continuam
  legíveis e arquivos com observações V2 usam cabeçalho V2.
- Migração 007 amplia o horizonte positivo em `decision_outcomes`, preservando
  registros e referências; não modifica ledger/fills/saldos. Abertura somente
  leitura aceita schemas 6/7; migração local ocorre na abertura gravável.
- Memória e transferência não misturam perfis/revisões/protocolos. Moedas podem
  compartilhar padrões compatíveis apenas pelos gates prospectivos existentes.
  Mínimos 30/50 e janela de 60 dias não foram reduzidos.
- Testes offline verificam execução, proteção, retomada e UI. Latência real,
  cobertura externa para a moeda escolhida e eficácia financeira dos novos
  perfis precisam ser medidas na próxima sessão. A publicação não comprova
  que o JEV consegue cumprir o deadline em todas as chamadas reais.
