# AGENTS.md — Contexto obrigatório do projeto

## Instrução prioritária

Leia **`docs/SPEC.md` integralmente antes de planejar, editar ou executar código**.
É o contrato funcional e técnico da POC. Não substitua decisões já
especificadas por sugestões genéricas de arquitetura de trading.

## Contextos complementares

Após ler a SPEC, consultar `docs/README.md` e os contextos de estratégias,
desenvolvimento, execução e futura TUI relacionados ao trabalho.
Desenho vigente D050–D052/SPEC 1.50: consultar `docs/ESCOPO_POC_V1.md`,
`docs/PLANO_DESENVOLVIMENTO_V1.md` e `docs/STATUS_DESENVOLVIMENTO.md`. `docs/PONTOS_A_ESCLARECER.md` guarda histórico/destinação.
Resolver detalhes rotineiros na implementação sem microaprovações. Distinguir pesquisa,
proposta e requisito vigente; perfis pesquisados não estão automaticamente
habilitados. Incorporar decisões posteriores do usuário aos documentos afetados.

## Objetivo

Construir uma POC em Python para **paper trading em um par Spot configurável por sessão com cotação USDT** com três carteiras
virtuais independentes de 100 USDT:
- A: análise técnica determinística;
- B: JEV 1.13 pelo OpenRouter, sem memória;
- C: JEV 1.13 pelo OpenRouter com Learning Engine estatístico próprio.

BTC/USDT é exemplo/default, não limite de suporte: outros ativos fazem parte da V1 conforme D030 e SPEC 4.3. Selecionar par/perfil antes da partida; manter banco, carteiras e memória por símbolo. Quantidades genéricas em Decimal e incrementos dos metadados públicos do par.

Operação contínua em motores Docker independentes da TUI terminal, integrada
após Marcos 1–5 conforme SPEC 15.4. Registrar SQLite/eventos JSONL e JSON/CSV;
HTML futuro. Interface não escreve bancos/saldos diretamente.

## Limites absolutos

- **NUNCA** implementar ou chamar operações financeiras reais.
- Exchange apenas como fonte de mercado **pública e somente leitura**.
- Apenas Spot, long-only, sem short/futuros/alavancagem.
- O JEV é inferência estruturada; não aprende seus pesos pelas chamadas.
- Learning Engine local só utiliza observações **já amadurecidas**.
- Sem dados atualizados, falha da IA ou preço incerto: não abrir posições.
- Sem frontend HTML; TUI terminal segue SPEC 15.4 após núcleo.
- Não usar floats em valores financeiros; utilizar `Decimal`.

## Forma de trabalho

1. Implementar Marcos 1–5 na ordem de `docs/SPEC.md`, depois E06–E11 do plano: runtime, transferência automática, REST/auth/2FA, WebSocket, TUI e aceite. Registrar evidências no status.
2. Escrever testes antes/depois de cada módulo crítico.
3. Não deixar funções essenciais como TODO ou mocks em caminhos de produção.
4. Se a chave OpenRouter faltar, validar tudo com testes e mocks offline,
   sem alegar que a integração real foi testada.
5. Manter `README.md` com instalação, `.env`, CLI, systemd, logs e diagnósticos.
6. Ao encerrar, informar o que foi implementado, testes, caminhos dos
   artefatos e limitações observadas.

## Referência do JEV

Endpoint correto:
`POST https://openrouter.ai/api/alpha/decisions`

Modelo: `typesafe/jev-1.13`

Não usar Chat Completions para o JEV. Persistir `usage.cost`, modelo efetivo
e IDs por chamada, com credenciais removidas dos logs.

## Fonte de verdade

Toda movimentação de carteira precisa existir em transação SQLite com
`paper_fills`, ledger, saldo e eventos. JSONL é projeção reconstruível.
**Verificar idempotência, retomada pós-crash e ausência de look-ahead.**

## V1 completa D051/D052

TUI local/remota via REST/WSS; lifecycle Docker no servidor, sem acesso do cliente a banco/daemon. Token/2FA/escopos/revogação conforme SPEC 15.4. Transferência automática integra V1 conforme 10.10, separada da memória local, com origem, validação prospectiva e gates; nunca inflar mínimos locais ou fabricar ACTIVE. Fechar TUI não para motor.
