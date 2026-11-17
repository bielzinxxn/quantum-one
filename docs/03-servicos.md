# 03 — Serviços

Todos rodam em contêiner com `restart: unless-stopped`, healthcheck HTTP próprio (`/health`, com estado de liveness e readiness), usuário não root e logs JSON no stdout.

## marketdata
- **Função:** assina pelo WebSocket da Binance (CCXT Pro) os trades, ticker e book (top N) dos pares do universo. Monta candles de 1m e agrega os timeframes maiores. Calcula as métricas do scanner: variação anormal, volume relativo, spread, profundidade a ±X%, volatilidade realizada.
- **Saídas:** `md:candles` (candle fechado), `md:scanner` (snapshot a cada N s), `md:health` (idade do último dado por par). Candles vão para o Postgres.
- **Dado velho:** um par sem atualização há mais de `STALE_MS` fica marcado como `stale` e é publicado assim. O `trader` bloqueia entradas nesse par.
- **Falha:** reconecta com backoff e jitter. Na volta, preenche as lacunas de candle via REST (`fetch_ohlcv`) antes de marcar o par como `fresh`. As conexões WS da Binance têm vida máxima (a confirmar na doc) e o serviço as renova de forma proativa.
- **Universo:** pares USDT com volume e profundidade mínimos, configurável. Meme coins entram numa lista separada, com filtros mais rígidos.

## engine
- **Função:** a cada candle fechado, calcula indicadores, classifica o regime (tendência, lateral ou alta volatilidade, com regra determinística versionada), avalia as estratégias habilitadas *naquele regime* e emite **sinais**.
- **Sinal:** contém estratégia e versão, par, direção (spot: comprar ou zerar), preço de referência, stop, alvo, ganho esperado e custo estimado em bps, regime, features e TTL.
- **Filtro de custo:** só emite o sinal se `ganho_esperado ≥ N × custo_total` (N = 3 por padrão).
- **Estado:** nenhum além de janelas de indicadores reconstruíveis a partir do Postgres. Pode reiniciar a qualquer momento.

## trader (núcleo crítico)
- **Função:** é o **único** processo com chave de trading. Contém:
  - **Risk Engine:** limites de exposição, perda diária, drawdown, limites por ativo e por estratégia, correlação, orçamento de trades por dia, saldo e duplicidade.
  - **Dimensionamento:** `min(tamanho_ATR, ¼·Kelly, teto_fixo) × fator_drawdown`.
  - **Alocação:** pesos entre estratégias.
  - **Execution Engine:** `client_order_id` idempotente, máquina de estados da ordem, timeouts, cancelamento, parciais e rate limit.
  - **Reconciliação:** saldos, ordens abertas e execuções versus o banco.
  - **Kill Switch.**
- **Entrada:** `sig:signals`, `ctl:commands` e `md:health`.
- **Saída:** `trd:orders`, `trd:fills` e `ops:alerts`. Grava ordens e eventos no Postgres **antes** de enviar à exchange (padrão outbox).
- **Inicialização:** começa em `BLOCKED`, lê o estado do kill switch no Postgres (se não conseguir ler, fica bloqueado), reconcilia com a exchange e só então passa a `READY`.
- **Falha:** ao reiniciar, a reconciliação resolve as ordens em voo pelo `client_order_id`. Nunca reenvia uma ordem sem antes consultar se ela já existe.

## accounting
- **Função:** consome `trd:fills` e mantém:
  - ledger de partidas dobradas;
  - P&L realizado e não realizado;
  - patrimônio, high-water mark e drawdown;
  - taxas e slippage;
  - **atribuição** por estratégia, ativo, hora, regime e custo;
  - **eventos fiscais** (custo médio em BRL, ganho por alienação, consolidação mensal).
- **Degradação:** compara as métricas rolantes de paper/live com a distribuição esperada do backtest. Fora da tolerância, publica `ctl:commands{pause_strategy}` e um alerta.
- **Relatórios:** diário, semanal e mensal, sempre com o benchmark de buy-and-hold de BTC.
- **Aportes e saques** entram em `capital_flows` e nunca contam como lucro.

## api
- **Função:** FastAPI para o dashboard. Faz leitura via repositórios (somente SELECT, com papel de banco próprio) e publica comandos (`pause`, `resume`, `kill`, `flatten`, `approve_stage`) com nonce e TOTP nos comandos críticos.
- **Não** fala com a exchange e **não** importa `execution`.
- Expõe WebSocket próprio para atualizações do dashboard, repassando os streams do Redis.

## dashboard
- Next.js, tema escuro preto e grafite, verde e vermelho para P&L, gráficos com Lightweight Charts.
- Páginas definidas no CLAUDE.md. Acesso só pela rede privada (ADR-006).

## backtest (job)
- CLI `backtest_cli` roda os mesmos módulos de estratégia, risco e contabilidade com `SimGateway` e `SimClock`.
- Gera `backtest_runs` e `edge_gate_evaluations` no Postgres e é reproduzível (hash de dados, parâmetros e código).

## postgres / redis
- **Postgres 16:** volume persistente, backup diário criptografado e enviado para fora da VPS, `candles` particionada por mês.
- **Redis 7:** AOF `everysec`, `maxmemory` com `noeviction` (streams não podem ser descartados em silêncio), streams com `MAXLEN ~` de retenção.

## Recursos estimados
8 GB de RAM e 2–4 vCPUs atendem tudo com folga. Com 4 GB funciona, mas o backtest precisa rodar fora do horário ou em outra máquina.
