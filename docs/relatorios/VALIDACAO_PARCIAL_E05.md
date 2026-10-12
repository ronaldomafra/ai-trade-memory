# E05 parcial — 12/10/2026

121 testes/lint/build passaram. Marketaux/RSS testados offline; quota compartilhada/cache/restart, corte temporal e atualizações preservam datas e origem. Gamma/CLOB parsers e filtros têm casos de unidades não verificáveis, books inválidos/futuros, profundidade/spread e tetos de ocorrência.

Leituras reais pelo proxy: documentação/Gamma/CLOB/Data v2 HTTP 200. Gamma market 559651 (Xi Jinping out before 2027), token Yes associado por posição explícita nas arrays; books/trades lidos sem autenticação de carteira. Quantitativo ainda não elegível sem unidade Gamma verificável, sem inferir recência pelo lastTradePrice. Real RSS: Cointelegraph 30 itens, CoinDesk indisponível. Coleta real não prova classificação JEV ou eficácia.

Referências primárias consultadas: [Marketaux API](https://www.marketaux.com/documentation), [plano gratuito](https://www.marketaux.com/pricing), [Polymarket livros](https://docs.polymarket.com/market-data/prices-order-books), [analytics](https://docs.polymarket.com/market-data/public-analytics), [trades públicos v2](https://docs.polymarket.com/api-reference/feeds/list-trades), [pUSD](https://docs.polymarket.com/concepts/pusd). A documentação v2 separa cotas de USD; o adaptador registra essa distinção e falha conservadoramente onde falta contrato.

Pendentes: coordenação periódica no motor, classificação semântica estruturada/cache/gates e relatórios completos; nenhuma notícia bruta/artigo integral deve ser enviada à decisão. Token Marketaux e JEV autenticado válido seguem validações externas, sem bloquear os módulos offline.
