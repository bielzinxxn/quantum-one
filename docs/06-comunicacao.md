# 06 — Comunicação entre módulos

## Visão
- **Entre processos:** Redis Streams com consumer groups. Entrega "pelo menos uma vez", com consumidores idempotentes.
- **Dentro do `trader`:** chamadas diretas e síncronas (async) entre Risk Engine e Execution. O risco não passa por fila e por isso não pode ser contornado.
- **Estado durável:** Postgres. O Redis é transporte e cache; perdê-lo não perde verdade, porque o boot reconcilia com a exchange e com o Postgres.

## Envelope (Pydantic, em `contracts/`)
```json
{
  "event_id": "uuid7",
  "type": "signal.created",
  "schema_version": 1,
  "ts": "2026-11-17T12:00:00.000Z",
  "source": "engine",
  "correlation_id": "uuid7 (sinal → decisão → ordem → fill)",
  "payload": { }
}
```
O `correlation_id` liga sinal, decisão de risco, ordem, fill e lançamento contábil. É ele que torna cada operação rastreável de ponta a ponta.

## Streams
| Stream | Produtor | Consumidores | Conteúdo |
|---|---|---|---|
| `md:candles` | marketdata | engine | candle fechado |
| `md:scanner` | marketdata | api, engine | métricas do scanner |
| `md:health` | marketdata | trader, api | frescor por par |
| `sig:signals` | engine | trader | sinais com TTL |
| `trd:orders` | trader | accounting, api | mudanças de estado de ordem |
| `trd:fills` | trader | accounting, api | execuções confirmadas pela exchange |
| `ctl:commands` | api, accounting | trader, engine | pause/resume/kill/flatten/pause_strategy |
| `ops:alerts` | todos | api, notificador | alertas |

**Implementado na Fase 4:** `contracts/envelope.py` (UUIDv7 em `core/ids.py`) e `bus/publisher.py`. Os payloads de mercado estão em `contracts/market.py`, e cada entrada do stream tem um campo `data` com o envelope em JSON.

## Semântica e garantias
- **Idempotência:**
  - cada consumidor grava `event_id` em `processed_events` na mesma transação do efeito;
  - `fills` é UNIQUE por `(exchange, trade_id)`;
  - ordens são UNIQUE por `client_order_id`, gerado **antes** do envio e determinístico a partir de `risk_decision_id`.
- **Ordem:** um único consumidor por grupo no `trader` processa sinais em série. Isso evita corrida entre duas entradas que juntas furariam o limite.
- **Ordem de `md:candles`:** não é garantida entre vela do stream e vela de backfill (`payload.backfill`). O consumidor ordena por `open_time` e deduplica por `(symbol, timeframe, open_time)`.
- **TTL de sinal:** sinal mais velho que `ttl_ms` é descartado e registrado. O sistema nunca executa decisão velha.
- **Pendentes:** mensagens não confirmadas (XPENDING) são reprocessadas no boot (XAUTOCLAIM). Depois de K tentativas, vão para `dlq:*` e geram alerta.
- **Comandos de controle:** também ficam gravados no Postgres (`kill_switch_events`, `audit_log`). O estado do kill switch é lido do **Postgres** no boot. Se não for possível ler, o sistema assume ativo (fail-closed).
- **Retenção:** `XADD ... MAXLEN ~` por stream, dimensionada para cerca de 24 h. O histórico fica no Postgres.

## Exchange (fora do barramento)
- Só o `trader` (ordens e conta) e o `marketdata` (dados públicos) falam com a Binance, sempre através do `ExchangeGateway`.
- O limitador por peso é compartilhado via Redis entre os dois processos, porque o limite da Binance é por IP.
- **Timeouts:** cada chamada tem timeout. Timeout **não** significa falha da ordem: o resultado é consultado pelo `client_order_id` antes de qualquer nova ação.
