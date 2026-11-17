# Binance Spot API — fatos verificados (2026-11-17)

**Fontes:**
- Documentação oficial publicada pela Binance em `github.com/binance/binance-spot-api-docs`, CHANGELOG atualizado em 2026-11-11. O site `developers.binance.com` está bloqueado no ambiente de desenvolvimento, por isso usei o espelho oficial no GitHub.
- Modelo `GetApiKeyPermissionResponse` do SDK oficial `binance/binance-connector-python`.
- Código-fonte do CCXT 4.5.92, instalado e inspecionado.

Revalide estes fatos a cada atualização do CCXT ou quando o CHANGELOG da Binance mudar.

## Limites (rest-api.md § LIMITS)
- Os limites valem **por IP**, não por chave. Os valores autoritativos estão em `GET /api/v3/exchangeInfo` → `rateLimits`. No exemplo da doc: `REQUEST_WEIGHT` 6000/min e `ORDERS` 50/10s.
- Cabeçalho de resposta `X-MBX-USED-WEIGHT-(n)(letra)`, por exemplo `X-MBX-USED-WEIGHT-1M`.
- **429:** limite excedido, obrigatório recuar. Insistir depois de 429 leva a **418, ban de IP**. A duração escala **de 2 minutos a 3 dias**. Nos dois casos, `Retry-After` vem em **segundos**.
- Contagem de ordens não preenchidas é por conta (`X-MBX-ORDER-COUNT-*`). Isso só importa a partir da Fase 8.

## Pesos usados nesta fase
| Endpoint | Peso |
|---|---|
| `GET /api/v3/time` | 1 |
| `GET /api/v3/exchangeInfo` | 20 |
| `GET /api/v3/account` (aceita `omitZeroBalances`) | 20 |
| `GET /api/v3/account/commission` | 20 |
| `GET /api/v3/openOrders` | 6 com símbolo · **80 sem símbolo** |
| `GET /api/v3/myTrades` (`limit` até 1000) | 20 sem orderId · 5 com |
| `GET /api/v3/klines` | 2 |
| `GET /api/v3/depth` | 5 com limit até 100, 25 com 101–500 |
| `GET /sapi/v1/account/apiRestrictions` | peso não confirmado (o CCXT atribui custo 0.1) |

## Segurança das requisições
- Tipos de chave aceitos: Ed25519, HMAC e RSA. **Ed25519 é a recomendação explícita da Binance** ("best performance and security"). A FAQ `faqs/api_key_types.md` diz literalmente que **"HMAC keys are deprecated"**.
- Ed25519 é criptografia assimétrica: você gera o par de chaves, envia **só a pública** para a Binance e a privada nunca sai da VPS.
- `recvWindow`: padrão de **5000 ms**, máximo de 60000. A Binance recomenda 5000 ou menos. O servidor rejeita `timestamp` mais de 1 s à frente do relógio dele.
- O CCXT trata o `secret` como Ed25519 quando ele contém "PRIVATE KEY" em PEM com menos de 120 caracteres, e assina usando a biblioteca `cryptography`.

## Permissões da chave: `GET /sapi/v1/account/apiRestrictions`
Campos: `ipRestrict`, `createTime`, `enableReading`, `enableWithdrawals`, `enableInternalTransfer`, `enableMargin`, `enableFutures`, `permitsUniversalTransfer`, `enableVanillaOptions`, `enableFixApiTrade`, `enableFixReadOnly`, `enableSpotAndMarginTrading`, `enablePortfolioMarginTrading`.

No CCXT o método é `sapi_get_account_apirestrictions`.

**Atenção:** o `canWithdraw` de `/api/v3/account` descreve a **conta**, não a chave. Para saber o que a chave pode fazer, vale o `apiRestrictions`.

## Stream de dados do usuário — MUDANÇA IMPORTANTE
- O `listenKey` (`POST/PUT/DELETE /api/v3/userDataStream`, `userDataStream.start/ping/stop`) foi **desligado em 2026-02-20 07:00 UTC** (CHANGELOG de 2026-01-21).
- O substituto é a WebSocket API (`wss://ws-api.binance.com:443/ws-api/v3`), com `userDataStream.subscribe` (sessão autenticada) ou `userDataStream.subscribe.signature`. Desde 2026-11-11 aceita `filter`.
- O CCXT 4.5.92 já usa `userDataStream.subscribe.signature` em `authenticate()` para spot. Isso confere com a doc. Vou usar na Fase 8.
- Eventos: `outboundAccountPosition`, `balanceUpdate`, `executionReport`, `eventStreamTerminated`, `externalLockUpdate`.

## WebSocket de mercado (web-socket-streams.md)
- Endereço `wss://stream.binance.com:9443` (ou `:443`). Símbolos em minúsculas.
- Conexão vale **no máximo 24 h**. Há o evento `serverShutdown` (com campo `T` desde 2026-11).
- O servidor manda ping a cada 20 s e desconecta se não receber pong em 1 min.
- Até 5 mensagens recebidas por segundo, no máximo 1024 streams por conexão e 300 conexões a cada 5 min por IP.

## Streams usados pelo Market Scanner (Fase 4, web-socket-streams.md)
- **Stream combinado** `/stream?streams=a/b/c`. Cada frame chega como `{"stream": "<nome>", "data": {...}}`. É obrigatório aqui porque o payload de `depth<N>` não traz o símbolo.
- `<symbol>@kline_1m`: atualizado a cada 2000 ms. Campos `k.t`/`k.T` (abertura e fechamento), `o h l c v`, `q` (volume em quote), `n` (trades) e **`x` (vela fechada?)**.
- `<symbol>@bookTicker`: tempo real. Campos `s`, `b`/`B` (melhor compra e quantidade), `a`/`A` (melhor venda e quantidade).
- `<symbol>@depth<5|10|20>[@100ms]`: os N melhores níveis, a cada 1000 ms ou 100 ms. Campos `lastUpdateId`, `bids` e `asks` como `[preço, qtd]` em string.
- `!serverShutdown` (combinado): campo `T` = momento do desligamento. É preciso reconectar logo.
- Endpoint só de mercado, também documentado: `wss://data-stream.binance.vision`.
- Mensagem de controle (SUBSCRIBE) conta no limite de 5 mensagens por segundo. Por isso o scanner passa os streams pelo URL e não usa SUBSCRIBE.
- REST de backfill: `GET /api/v3/klines` (peso 2, `limit` até 1000). Cada linha é `[openTime, o, h, l, c, v, closeTime, quoteVol, trades, takerBase, takerQuote, ignore]`, e a **última pode ser a vela em andamento**.
- `GET /api/v3/ticker/24hr` sem `symbol`: peso 80, com o campo `quoteVolume`.
- **CCXT Pro 4.5.92:** o `watch_ohlcv` descarta `x`, `q` e `n` e converte para float. Isso motivou a ADR-009.

## Filtros de símbolo (filters.md) usados para validar ordens
- `PRICE_FILTER` (`minPrice`, `maxPrice`, `tickSize`; o valor 0 desativa a regra).
- `LOT_SIZE` (`minQty`, `maxQty`, `stepSize`) e `MARKET_LOT_SIZE`.
- `NOTIONAL` (`minNotional`, `maxNotional`, `applyMinToMarket`, `applyMaxToMarket`, `avgPriceMins`) e o legado `MIN_NOTIONAL`.
- Outros, a tratar depois: `PERCENT_PRICE_BY_SIDE`, `MAX_NUM_ORDERS`, `MAX_POSITION`, `TRAILING_DELTA`.

## Enums
- **Status do símbolo:** `TRADING`, `END_OF_DAY`, `HALT`, `BREAK`, `CANCEL_ONLY`. Só `TRADING` é negociável.
- **Tipos de ordem:** `LIMIT`, `MARKET`, `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT`, `TAKE_PROFIT_LIMIT`, `LIMIT_MAKER`. Também há `ocoAllowed`, `otoAllowed` e `opoAllowed` por símbolo. Isso responde à pendência "stops no spot": existem na exchange, e a escolha fica para a Fase 8.

## Comissões: `GET /api/v3/account/commission?symbol=`
Retorna `standardCommission`, `specialCommission` e `taxCommission` (cada um com maker, taker, buyer e seller) e `discount` (`enabledForAccount`, `enabledForSymbol`, `discountAsset` = BNB e `discount` = multiplicador).
