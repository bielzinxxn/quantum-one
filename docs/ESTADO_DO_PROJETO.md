# Estado do projeto — QUANTUM ONE
Atualizado: 2026-11-17 · Fase atual: **4 (Market Scanner) — aguardando "aprovado, próxima fase"**

**Concluídas:** Fases 1–3 (aprovadas). Fase 4 entregue: 178 testes unitários + 36 de integração + smoke de 10 pontos verdes (6 rodadas
seguidas sem falha); cobertura 94%. Sem teste contra a Binance real (rede bloqueada aqui): validar na VPS (ver critério de aceite da fase).

**Decisões:** ADR-001 spot USDT · ADR-002 trader escritor único · ADR-003 Streams/Postgres · ADR-004 código único · ADR-005 fiscal BRL ·
ADR-006 VPN · ADR-007 contêineres · ADR-008 Binance leitura (CCXT implícito, política de chave, relógio, orçamento de peso) ·
ADR-009 scanner com WebSocket direto (aiohttp) — CCXT Pro descarta o flag de vela fechada; stream combinado kline_1m+bookTicker+depth20,
backfill REST, profundidade/slippage como limite inferior (depth20), velas em tabela simples + BRIN (partição adiada).

**Estrutura:** `backend/src/quantum_one/{core,contracts,db,bus,exchange/binance,marketdata,services,api}`, migrations 0001–0003,
`tests/{unit/{exchange,marketdata},integration,fakes}` (REST e WS falsos), `infra/`, `docs/{decisoes,referencias}`.

**Pendências:**
- Capital inicial (Fase 7) · enquadramento fiscal (contador) · canal de alertas · fonte on-chain para meme coins (módulo 5).
- Retenção de `scanner_snapshots`/`candles` (job de limpeza) · limiares das flags do scanner a calibrar com dados reais.
- Fase 8: stream de usuário via WebSocket API e stop na exchange · Fase 12: hash do `audit_log` · repositório remoto/CI.

**Riscos abertos:** latência SP–Tóquio · ban por rate limit (mitigado) · overfitting · custódia Binance/USDT · incerteza fiscal ·
formato dos streams pode mudar (parser falha fechado e conta mensagens desconhecidas) · ordem de `md:candles` não garantida (documentado).

**Próxima fase:** 5 — Análise quantitativa (RSI, MACD, VWAP, EMA, ATR, Bollinger, retornos/vol) e regime de mercado determinístico.
