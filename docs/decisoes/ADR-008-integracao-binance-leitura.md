# ADR-008 — Integração com a Binance (somente leitura)

**Status:** aceita (2026-11-17, Fase 3). Os fatos que embasam estas decisões estão em `docs/referencias/binance-spot-api.md`.

**Decisões:**
1. **CCXT com a API implícita para REST.** Uso `public_get_exchangeinfo`, `private_get_account`, `sapi_get_account_apirestrictions` e afins, em vez dos métodos unificados (`fetch_balance`). A API implícita devolve o JSON bruto da Binance, com números como string, que eu converto direto para `Decimal`. Os métodos unificados convertem para `float` e perderiam precisão.
2. **Política de chave verificada no boot (fail-closed).** O `trader` lê `apiRestrictions` e só segue se:
   - `enableReading` for verdadeiro;
   - saque, transferências, margem, futuros, opções e portfolio margin estiverem **desligados**;
   - na política `read_only` (Fases 3–11), também `enableSpotAndMarginTrading` estiver desligado;
   - em `QONE_ENV=prod`, `ipRestrict` for verdadeiro.

   Qualquer violação mantém o `trader` em `BLOCKED`, com o motivo exposto no healthcheck.
3. **Relógio.** Uso `recvWindow` de 5000 ms, como a Binance recomenda; o CCXT viria com 10000. Desliguei o `adjustForTimeDifference` do CCXT e meço o offset contra `GET /api/v3/time`. Se o offset passar de `CLOCK_MAX_OFFSET_MS` (1000 por padrão), a exchange fica marcada como não saudável. A causa é o relógio da VPS, e quem corrige é o chrony, não o software.
4. **Classificação de erro pelo status HTTP.** O CCXT 4.5.92 levanta `DDoSProtection` tanto para 429 quanto para 418; o teste de ponta a ponta revelou isso. O status é lido da mensagem.
5. **Orçamento de peso próprio,** além do limitador do CCXT:
   - leio o cabeçalho `X-MBX-USED-WEIGHT-1M`;
   - paro de fazer requisições acima de 80% do limite vindo do `exchangeInfo`;
   - em 429 ou 418, respeito o `Retry-After` e gravo `banned_until` no Redis. Assim `marketdata` e `trader`, que compartilham o mesmo IP, param juntos.
6. **Credenciais.** Ed25519 é o recomendado: a chave privada em PEM vai em `BINANCE_API_SECRET`, com `\n` escapados numa linha só. HMAC ainda é aceito, mas a Binance o declara depreciado, e o `check-binance` avisa.
7. **Stream de usuário:** o `listenKey` foi desligado pela Binance em 2026-02-20. Na Fase 8 vou usar a WebSocket API (`userDataStream.subscribe.signature`, que o CCXT 4.5.92 já implementa). Nesta fase, a conta é lida por REST a cada `ACCOUNT_POLL_S` (60 s), o que dá cerca de 100 de peso por minuto num limite de 6000.
8. **Divisão de responsabilidades.**
   - `marketdata` sincroniza os instrumentos (`exchangeInfo`, dado público) para `q1.instruments`.
   - `trader` lê a conta e grava `q1.balance_snapshots`.
   - Nenhum outro serviço fala com a Binance.

**Consequências:**
- A API implícita depende dos nomes de rota do CCXT. Um teste falha se algum método sumir numa atualização.
- Não houve teste com a Binance real no ambiente de desenvolvimento (rede bloqueada). A validação real é o `make check-binance` na VPS.
