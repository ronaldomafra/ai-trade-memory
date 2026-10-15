# Escopo da POC V1 completa

**D050–D056 · SPEC 1.54 · 14/10/2026.** Módulos disponíveis e homologação no status; extensão de perfis planejada, sem implementação nesta tarefa.
[Plano ordenado](PLANO_DESENVOLVIMENTO_V1.md) · [Progresso](STATUS_DESENVOLVIMENTO.md).

## Incluído

- Python hexagonal, paper Spot long-only, fontes públicas somente leitura e Decimal.
- `trend_15m_v1`, 15m/1h, duração máxima 16 candles, par Spot USDT por sessão; BTC default/exemplo.
- Extensão D056 após revisão do core: cadastro/templates completos de swing, scalping e day trade, com instruções JEV e contratos de execução próprios. [Plano P00–P09](PLANO_PERFIS_ESTRATEGIA.md); ainda não implementada.
- A técnica/B JEV/C mesmo JEV mais memória; 100 USDT por carteira.
- Sessão/run_id/config imutável, banco/volume/container próprios, restore sem reset/retrotrade.
- Marketaux gratuito/RSS/Polymarket, fatores/evidência curta/reuso/gates conforme SPEC.
- Decisions API JEV, custo/tentativas auditados, orçamento global compartilhado.
- Memória local madura/dataset JSONL opcional/acumulativo; transferência automática entre moedas separada, validada e rastreável conforme 10.10.
- Controle remoto REST/WS, token/2FA, lifecycle Docker no servidor, HTTPS/WSS na hospedagem.
- TUI Textual completa: login, sessões, wizard, restore, dashboard/gráficos A/B/C, decisões/custo/memória/transferência, import/export/eventos. Sair mantém bot.
- SQLite canônico, commit financeiro atômico, JSONL reconstruível, JSON/CSV, backups/restore e observação no período escolhido pelo usuário (D054), sem mínimo de 24h.

## Limites e sequência

Marcos 1–5 primeiro; depois runtime, transferência, REST/auth, WS, TUI e aceite E06–E11. Transferência estava fora de D050 e agora integra a entrega por solicitação D052. Os defaults novos de validação são escolhas técnicas iniciais do agente, a testar.

Memória local mantém mínimos 30/50 e janela 60d; total três padrões, locais primeiro. Fontes estrangeiras não inflacionam contagens locais; moeda nova pode aguardar validação destino sem uso transferido.

Orçamento global: SQLite operacional com reservas idempotentes/conciliação, até 240 chamadas físicas/dia UTC e limite financeiro default habilitado em US$ 0,05 observado/dia, incluindo classificação/retries. D053/SPEC 1.51 permite configurar/desabilitar o limite financeiro global, preservando a guarda de chamadas e todo registro de gasto. Código preparado sem aplicação ao ensaio atual. Sem subcotas fixas inicialmente. Duas sessões não multiplicam capacidade: 384 chamadas nominais/dia antes de extras para dois perfis 15m; falta => HOLD B/C, risco ativo e cobertura reportada. Unknown não vira zero nem garante teto absoluto da fatura.

Fora: ordens reais, credenciais de exchange, short/futuros/alavancagem, HTML, RAG/banco vetorial, treino de pesos, hold nesta etapa, famílias sem contrato/código/testes, cluster/múltiplos hosts e subcotas avançadas. Dependência entre candles locais é reportada, sem novos pesos/mínimos locais.

Detalhes rotineiros são implementação/testes sem microaprovações. Mudança material de risco/experimento/custo deve ser explicitada. D054 remove a espera de 24h para análises/atualizações e o reinício obrigatório dessa contagem; preservar resultados e versões. Conclusão documental não equivale a software/integração/homologação.
