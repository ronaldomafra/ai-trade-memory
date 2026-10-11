# AGENTS.md — Contexto obrigatório do projeto

## Instrução prioritária

Leia **`docs/SPEC.md` integralmente antes de planejar, editar ou executar código**.
É o contrato funcional e técnico da POC. Não substitua decisões já
especificadas por sugestões genéricas de arquitetura de trading.

## Objetivo

Construir uma POC em Python para **paper trading BTC/USDT** com três carteiras
virtuais independentes de 100 USDT:
- A: análise técnica determinística;
- B: JEV 1.13 pelo OpenRouter, sem memória;
- C: JEV 1.13 pelo OpenRouter com Learning Engine estatístico próprio.

Operação contínua, sem interface gráfica. Registrar tudo em SQLite e eventos
JSONL; gerar JSON/CSV para um futuro frontend HTML.

## Limites absolutos

- **NUNCA** implementar ou chamar operações financeiras reais.
- Exchange apenas como fonte de mercado **pública e somente leitura**.
- Apenas Spot, long-only, sem short/futuros/alavancagem.
- O JEV é inferência estruturada; não aprende seus pesos pelas chamadas.
- Learning Engine local só utiliza observações **já amadurecidas**.
- Sem dados atualizados, falha da IA ou preço incerto: não abrir posições.
- Nada de frontend nesta fase.
- Não usar floats em valores financeiros; utilizar `Decimal`.

## Forma de trabalho

1. Implementar os Marcos 1–5 na ordem indicada em `docs/SPEC.md`.
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