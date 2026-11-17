# ADR-001 — Binance spot, pares USDT, sem alavancagem

**Status:** aceita (2026-11-17)

**Contexto:** você definiu Binance, mercado spot, PF no Brasil e VPS em São Paulo. O CLAUDE.md proíbe alavancagem automática.

**Decisão:**
- Uma única exchange (Binance) e somente spot. O universo de negociação são os pares cotados em **USDT**, por terem mais liquidez que os pares em BRL.
- Sem venda a descoberto: a estratégia só "compra" ou "zera".
- A integração passa pelo `ExchangeGateway`, para que outra exchange possa ser adicionada no futuro sem tocar em estratégias ou risco.

**Consequências:**
- Mean reversion e momentum só operam o lado comprado. Em mercado de baixa, a estratégia fica em caixa (USDT), e isso é aceitável.
- Cada operação em USDT precisa da conversão para BRL para fins fiscais (ADR-005).
- O saldo parado em USDT tem risco de contraparte da stablecoin, que fica registrado como risco aceito.
