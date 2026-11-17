# 04 — Fluxo de dados

## 1. Do mercado ao sinal
```mermaid
sequenceDiagram
  participant B as Binance WS
  participant MD as marketdata
  participant R as Redis
  participant PG as Postgres
  participant EN as engine
  B->>MD: trades / ticker / book
  MD->>MD: monta candle 1m, métricas do scanner
  MD->>PG: grava candle fechado
  MD->>R: XADD md:candles, md:scanner, md:health
  R->>EN: candle fechado (consumer group)
  EN->>EN: indicadores → regime → estratégias do regime
  EN->>EN: filtro ganho ≥ N × custo
  EN->>R: XADD sig:signals (com TTL)
```

## 2. Do sinal à execução (caminho crítico)
```mermaid
sequenceDiagram
  participant R as Redis
  participant TR as trader (Risk + Execution)
  participant PG as Postgres
  participant X as Binance API
  R->>TR: sinal
  TR->>TR: descarta se TTL vencido, par stale ou kill switch ativo
  TR->>TR: Risk Engine: limites, correlação, saldo, orçamento diário
  TR->>TR: tamanho = min(ATR, ¼Kelly, teto) × fator_drawdown
  TR->>PG: grava risk_decision + order(PENDING, client_order_id)
  TR->>X: nova ordem (limit/maker preferencial)
  X-->>TR: ack ou timeout
  alt timeout / erro de rede
    TR->>X: consulta por client_order_id
  end
  X-->>TR: eventos de ordem e execuções (stream do usuário)
  TR->>PG: order_events, fills (idempotente por trade_id)
  TR->>R: XADD trd:orders, trd:fills
```
**Regra:** uma ordem só conta como executada quando o fill chega da exchange. Ack não é execução.

## 3. Da execução à contabilidade
```mermaid
sequenceDiagram
  participant R as Redis
  participant AC as accounting
  participant PG as Postgres
  R->>AC: fill
  AC->>AC: cotação USDT/BRL do momento (fonte registrada)
  AC->>PG: ledger_entries (partidas dobradas)
  AC->>PG: custo médio / tax_event se for alienação
  AC->>PG: pnl_attribution (estratégia, ativo, hora, regime, custo)
  AC->>PG: equity_snapshot, HWM, drawdown
  AC->>AC: degradação: real vs. esperado do backtest
  opt fora da tolerância
    AC->>R: ctl:commands pause_strategy + ops:alerts
  end
```

## 4. Perda de conexão e reconciliação
```mermaid
stateDiagram-v2
  [*] --> BLOCKED: boot
  BLOCKED --> RECONCILING: conexão OK + kill switch lido
  RECONCILING --> READY: saldos, ordens e execuções batem
  RECONCILING --> HALTED: divergência acima da tolerância
  READY --> BLOCKED: WS caiu / dado stale / erro de auth
  READY --> HALTED: kill switch
  HALTED --> RECONCILING: liberação manual (TOTP)
```
Em `BLOCKED`, as saídas protetoras já colocadas na exchange continuam valendo. Novas entradas ficam proibidas.

## 5. Kill switch
- **Gatilhos automáticos:** perda diária máxima, drawdown máximo, divergência na reconciliação, erros repetidos da exchange, ban de rate limit.
- **Gatilho manual:** pelo dashboard.
- **Ação padrão:** bloqueia novas entradas, cancela ordens de **entrada** abertas e mantém os stops na exchange.
- `flatten` (zerar posições) é um comando separado e explícito.
- Retomar exige ação manual com TOTP.

## 6. Pipeline de validação da estratégia
```mermaid
flowchart LR
  D["Dados históricos"] --> IS["Otimização in-sample<br/>(parâmetros limitados)"]
  IS --> OOS["Teste fora da amostra"]
  OOS --> WF["Walk-forward"]
  WF --> G{"Edge gate:<br/>expectativa > 0 após custos,<br/>n ≥ mínimo, IC,<br/>Sharpe/Sortino > BTC B&H"}
  G -- não --> X["Rejeitada"]
  G -- sim --> A["Aguarda SUA liberação<br/>para paper"]
  A --> P["Paper"] --> M{"Degradação OK<br/>por período mínimo?"}
  M -- sim --> L["Aguarda SUA liberação<br/>para live (capital limitado)"]
  M -- não --> X
```
