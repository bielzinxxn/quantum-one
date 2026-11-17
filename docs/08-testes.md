# 08 — Plano de testes

**Ferramentas:**
- Backend: pytest, pytest-asyncio, Hypothesis, testcontainers (Postgres e Redis reais), freezegun/`SimClock`.
- Frontend: vitest e Playwright.
- Comando único: `make test`. A cobertura de *branch* é exigida nos módulos críticos.

## Camadas
| Camada | O que cobre | Exemplos |
|---|---|---|
| **Unitário** | Funções puras | indicadores, regime, regras de entrada e saída, filtro N×custo, custo médio |
| **Referência (golden)** | Indicadores e métricas contra valores conhecidos | RSI/MACD/ATR versus série de referência calculada de forma independente; Sharpe/Sortino/PF versus cálculo manual |
| **Propriedade (Hypothesis)** | Invariantes que nunca podem quebrar | tamanho ≤ min(ATR, ¼Kelly, teto); exposição nunca acima do limite; ledger com soma zero por transação; tamanho cai com drawdown; nunca aumenta posição perdedora |
| **Contrato da exchange** | CCXT **real** contra um servidor Binance falso (`tests/fakes/`), que valida as assinaturas HMAC e Ed25519 no formato da doc oficial | parse de saldo, ordens, fills, comissão e filtros (tick/step/notional); erros 429, 418, -1021 e -2015; backoff compartilhado; rotas implícitas exigidas do CCXT |
| **Integração** | Serviços com Postgres e Redis reais | sinal → risco → ordem (PaperGateway) → fill → ledger → atribuição |
| **Falhas (fault injection)** | Simulador de exchange hostil | WS cai no meio da ordem; timeout com ordem aceita; fill parcial seguido de cancelamento; evento duplicado ou fora de ordem; dado stale; Redis reinicia; trader morto com `kill -9` em pleno envio |
| **Determinismo do backtest** | Reprodutibilidade | mesmo dado + parâmetros + código produzem o mesmo hash de resultado |
| **Edge gate** | O portão não deixa passar estratégia ruim | estratégia aleatória sintética **deve** ser rejeitada; estratégia com edge sintético conhecido deve passar |
| **Fiscal** | Exemplos numéricos fechados | custo médio com várias compras; venda parcial; troca cripto-cripto como alienação; taxa paga em BNB; mês acima e abaixo da isenção (parâmetros confirmados por você com o contador) |
| **API / segurança** | Borda | login sem TOTP falha; nonce reutilizado é rejeitado; papel `app_api` não consegue INSERT em `orders`; logs sem segredos (teste varre a saída) |
| **Frontend** | Telas e controles | renderização das páginas; botão de kill pede TOTP; P&L verde/vermelho correto |
| **E2E paper** | Compose inteiro com dados ao vivo | roda N horas sem erro, reconecta e reconcilia sozinho |

## Metas
- `risk/`, `execution/`, `accounting/`: **≥ 90% de branch coverage** e 100% dos invariantes cobertos por propriedade.
- Demais módulos: ≥ 75%.
- Nenhum teste toca a Binance real por padrão. Testes com rede ficam marcados como `@pytest.mark.live_readonly` e são opcionais.

## O que não dá para testar aqui (e como você testa)
- **Conectividade real com a Binance:** você roda `make check-binance` na VPS com a chave somente leitura (Fase 3).
- **API de ordens:** a Binance tem **Spot Testnet** para validar o contrato de ordens sem dinheiro. Ela tem liquidez e preços irreais, então não serve para medir estratégia.
- **Latência real SP–Tóquio e slippage:** só medindo em paper na própria VPS. O paper registra latência e slippage observados, que realimentam o modelo de custo do backtest.
- **Regras fiscais:** a lógica é testada; a interpretação legal depende do seu contador.

## Critério geral de aceite por fase
`make test` verde, cobertura mínima atingida, nenhum segredo nos logs e o critério objetivo da fase validado por você.
