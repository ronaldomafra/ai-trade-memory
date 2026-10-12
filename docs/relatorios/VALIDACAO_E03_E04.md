# Validação E03/E04 — 12/10/2026

110 testes passaram; lint/formatação limpos. E03 cobre protocolo Decisions/choice/noul, probabilidades e confidence separados, retries só transitórios (máximo 2), orçamento atômico entre 12 concorrentes/rollover, reservas após crash, resposta global sobrevivendo falha de projeção local, reuso B/C e custo físico único, 401/402/403 com circuito, dados sensíveis removidos.

Smoke real Decisions respondeu HTTP 401. Tentativa fb960bc7fc0f91683c41cbb5c4b310d4d81a6539e9ce28cb1e90b628b3740417 foi registrada em data/operational/ai-budget.sqlite3, custo NULL/unknown, sem modelo/generation ID retornados. Não houve sucesso autenticado nem trade. A credencial rejeitada fica em circuito fechado até substituição local.

E04 cobre maturação estrita, janela de 90s sem bid/UNAVAILABLE, dedupe 3 origens, corte temporal, mínimos 30/50, família/símbolo/protocolo/idade, neutros/uncerteza, arquivo acumulativo/hash, importação atômica/retomada sem reabrir arquivo alterado e conservação do capital. Todos os exemplos de aprendizado dos testes são sintéticos e ficam em diretórios temporários pytest; nenhuma amostra real reutilizável foi fabricada.

Execução nativa após integração: verification-market-btc, 8s, Binance real fresca, clock VERIFIED, auditoria sem erros/zero fills, parada limpa. Não houve candle novo nessa janela. Mercado contínuo 24h, JEV válido, Marketaux autenticada, fontes externas/transferência/TUI continuam pendentes. Token Marketaux será preenchido depois pelo usuário; a ausência não bloqueia desenvolvimento offline.
