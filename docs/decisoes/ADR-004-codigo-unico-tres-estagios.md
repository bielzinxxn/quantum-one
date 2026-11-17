# ADR-004 — Mesmo código em backtest, paper e live

**Status:** aceita (2026-11-17)

**Contexto:** a maior fonte de divergência entre backtest e live é ter lógica duplicada.

**Decisão:**
- Estratégias, risco, alocação e contabilidade recebem `ExchangeGateway` e `Clock` por injeção.
- As implementações são três: `SimGateway` + `SimClock` (backtest), `PaperGateway` (book ao vivo, parciais e latência simulados) e `BinanceGateway` (live).
- O estágio é definido por estratégia, no banco, e só muda com a sua liberação registrada em `stage_approvals`.

**Consequências:**
- O backtest roda mais devagar que um vetorizado puro. Aceitamos isso em troca de fidelidade. Uma triagem vetorizada rápida pode existir à parte, mas não serve para o edge gate.
- O monitor de degradação compara métricas equivalentes, porque elas saem do mesmo código.
