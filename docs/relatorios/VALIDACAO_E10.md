# Validação E10 — TUI V1

12/10/2026, versão 0.1.0, SPEC 1.50. Cliente Textual exclusivamente REST/WS:
sem banco, Docker, broker ou chaves de provedores na interface. CLI `tui --server`
não carrega o .env do servidor. Senha/TOTP em inputs ocultos, removidos após uso;
tokens somente em memória, refresh rotativo serializado e logout independente
do lifecycle. URL remota exige HTTPS e não aceita credenciais/query strings.

Implementados login/2FA/read-only, listar/selecionar, wizard perfil/par/template
JSON/ajustes/dataset opcional/transferência antes da criação, iniciar/retomar e
configuração persistida readonly. Criação usa chave idempotente estável/corpo
congelado em falha incerta; não transforma retry em capital novo. Defaults
financeiros são texto Decimal e backend valida perfil/limites.

Dashboard inspirado na referência: A/B/C, dinheiro/retorno/drawdown, candles
fechados 15m, curvas de equity, posições/fills, decisões/probabilidades/confidence
e gates, custo observado/unknown, fontes/learning/transferência. Abas de decisões,
memória/estados/origens, eventos filtráveis e configuração. Renderização de texto
externo sem markup/instruções; logs limitados a 1000 linhas, até 200 candles e
500 pontos equity por carteira. Terminais estreitos usam uma coluna/rolagem.
Não há saldo ou trade copiado da imagem de referência.

Teclado: Tab, R, N, S, D, L, O, Q, ?. Dataset local é enviado/baixado pela API;
import somente inicial, export local hash verificado/0600/sem sobrescrever.
Dados financeiros continuam no servidor. Identidade divergente é rejeitada;
quedas/ausência são exibidas, sem preencher preços/memória/retorno fictícios.
O status separa idade da cotação e recebimento do stream. Logout limpa dados
da interface; sair/perder conexão não faz stop.

## Evidência

Suíte conjunta: 166 testes após limite de corpo HTTP chunked; ruff limpo.
Casos Textual: inputs secretos, duas fases do login, wizard inválido/correção,
ETH sem dataset, BTC/ETH selecionados, vazio/read-only/resize, REST/WS degradados,
identidade errada e logout/quit sem comando de motor. Teste de dependências
impede acesso local SQLite/Docker/exchange/inferência pelo cliente.

Percurso real com gateway nativo em 18080 e diretório isolado
/tmp/poc-v1-gateway-verification, sem JEV/Marketaux autenticados:

- Login/2FA reais do proprietário temporário; consulta gateway-runtime-btc com
  três carteiras reais da sessão, watermark 81 e WS com quote pública.
- Wizard da TUI criou tui-runtime-eth/ETHUSDT sem dataset e iniciou Docker.
  Após aquecimento: 800 candles no banco, 200 apresentados, quote fresca,
  clock VERIFIED e auditoria OK; sem fills nessa janela curta.
- Dataset exportado do backend: zero exemplos válidos disponíveis. Download,
  envio/importação pela TUI na sessão preparada tui-dataset-prepared/ETHUSDT e
  reexportação funcionaram. Um vínculo de import, zero exemplos; todas as
  carteiras iguais antes/depois. Não inventar amostras para demonstrar o fluxo.
- Logout/saída da TUI não pararam o motor ETH (engine-status running=true).

Capturas reais: [dashboard BTC](tui-v1-dashboard.svg),
[terminal menor](tui-v1-terminal-pequeno.svg),
[ETH criada pela TUI após aquecimento](tui-v1-eth-criada.svg).
Provas temporárias /tmp/poc-e10-live-proof.json,
/tmp/poc-e10-create-proof.json e /tmp/poc-e10-dataset-proof.json.
Proprietário de produção não criado/alterado; segredos omitidos.

E11 permanece: estabilidade 24h, hospedagem/TLS externo e integração prolongada
com resposta JEV válida. E05 mantém pendência de unidades Gamma/seleção/semântica;
Marketaux autenticada adiada pelo usuário. Interface funcionando não valida
essas integrações, transferência ACTIVE real nem rentabilidade.

Referência primária Textual: [telas](https://textual.textualize.io/guide/screens/),
[testes](https://textual.textualize.io/guide/testing/),
[tabelas](https://textual.textualize.io/widgets/data_table/).
