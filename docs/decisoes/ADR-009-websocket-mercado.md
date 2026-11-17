# ADR-009 — Market Scanner: WebSocket direto (aiohttp) para dados de mercado

**Status:** aceita (2026-11-17, Fase 4)

## Contexto
O `CLAUDE.md` lista CCXT Pro e WebSockets no stack. Inspecionei o CCXT Pro 4.5.92 (`pro/binance.py`, `handle_ohlcv`). Para spot:
- o `watch_ohlcv` monta `[t, o, h, l, c, v]` com `safe_float` e **descarta o campo `x` (vela fechada)**, o volume em quote (`q`), o número de trades (`n`) e o volume comprador (`V`, `Q`);
- a reconexão é interna e não expõe evento de "reconectei". Sem esse evento, não dá para disparar o preenchimento de lacunas no momento certo.

O scanner precisa exatamente disso: saber quando uma vela fechou, detectar dado velho e preencher lacunas depois de queda.

## Decisão
1. **Streams de mercado via aiohttp WebSocket**, direto no endpoint documentado `wss://stream.binance.com:9443/stream?streams=...` (stream combinado, que é obrigatório porque o payload de `depth20` não traz o símbolo). Por símbolo, uso três streams: `kline_1m`, `bookTicker` e `depth20` (1 s). O URL é configurável. A Binance também documenta o endpoint só de mercado, `wss://data-stream.binance.vision`.
2. **REST continua no CCXT,** pela API implícita, como no ADR-008: `klines` para preencher lacunas e `ticker/24hr` para escolher o universo.
3. **Ciclo de vida da conexão, conforme a doc:**
   - o aiohttp responde ao ping do servidor automaticamente (`autoping`);
   - silêncio maior que `SCANNER_STALE_AFTER_S` derruba e reconecta;
   - o evento `serverShutdown` faz reconectar na hora;
   - a conexão é renovada antes do limite de 24 h;
   - backoff exponencial com jitter, de 1 a 60 s, respeitando o limite de 300 conexões a cada 5 minutos por IP.
4. **Lacunas:** a cada (re)conexão e a cada salto de `open_time`, busco as velas faltantes por REST. Descarto qualquer vela cujo `closeTime` ainda não passou, porque o REST devolve a vela em andamento.
5. **Profundidade:** `depth20` mostra só 20 níveis. A profundidade dentro de ±X% e a estimativa de slippage são **limites inferiores**, e marco `truncated=true` quando o 20º nível ainda está dentro da faixa. Para pares muito líquidos, como BTC, 20 níveis cobrem muito pouco preço, mas já somam muita liquidez. Para pares rasos, que são os que importam no filtro, normalmente 20 níveis cobrem a faixa inteira.
6. **Números:** velas em `Decimal`, porque são persistidas e alimentam a contabilidade e o backtest. As métricas estatísticas (z-score, volatilidade, spread) usam `float`.
7. **Velas numa tabela simples por enquanto,** com chave `(symbol, timeframe, open_time)` e índice BRIN em `open_time`. Isso diverge do "particionada por mês" do `docs/05`. Com cerca de 30 pares e 1m, são uns 16 milhões de linhas por ano, o que uma tabela simples aguenta. Particionar fica para quando o volume justificar.

## Consequências
- Mais código próprio (conexão, parsing), mas com testes contra um servidor WebSocket falso: reconexão, silêncio, `serverShutdown` e lacunas.
- Se a Binance mudar o formato de um stream, o parser falha de forma explícita; mensagem desconhecida é contada e ignorada, nunca interpretada pela metade.
