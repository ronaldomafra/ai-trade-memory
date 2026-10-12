# E02 parcial — indicadores e baseline

Em 12/10/2026, suíte completa de 67 testes e lint passaram. E02 ainda não concluída.

Implementação: Candle/validação de OHLCV/intervalos e disponibilidade; indicadores EMA/RSI/ATR/MACD, volume relativo e retornos; FeatureEngine com candles fechados/gaps/warmup, 1h consolidada e regime/tercis; baseline A determinística; deadline de entrada desde fechamento do candle.

Testes: referência EMA/MACD independente em pandas, seed Wilder conhecido, preços constantes/zero/insuficiência, candle futuro/parcial, dados ainda não recebidos, volume excluindo atual, gaps, tercis com choque atual, fronteiras de buckets e condições combinadas da baseline. RSI constante é definido como 50; volatilidade usa até 200 ATR% anteriores. Escolhas matemáticas são versionadas, sem otimizar limiares de trade.

Próxima integração: feeds REST/WS, persistência/orquestração/risco concorrente, CLI run, retomada e Docker. Não houve teste de streaming/24h/JEV ou declaração de V1 completa.
