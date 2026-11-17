# ADR-005 — Registro fiscal em BRL por fill, com regras plugáveis

**Status:** aceita (2026-11-17). A interpretação legal fica pendente de confirmação com o contador.

**Contexto:** você é PF residente no Brasil. No Brasil, a troca entre criptoativos (por exemplo, BTC → USDT) é tratada como alienação. O enquadramento da Binance (exchange nacional ou estrangeira) afeta o regime aplicável e as obrigações acessórias, e as regras mudaram nos últimos anos. **Não vou cravar alíquotas ou isenções no código.**

**Decisão:**
- Todo fill grava `brl_rate` e `brl_rate_source` no momento da execução (ex.: USDT/BRL da Binance; PTAX como fonte alternativa).
- O custo médio é mantido em BRL por ativo. Cada alienação gera um `tax_event`.
- As regras ficam em `tax_rule_sets`, versionadas e com parâmetros configuráveis (limite de isenção, alíquotas, periodicidade de apuração, fonte de câmbio). Começamos com dois perfis, `br_pf_nacional` e `br_pf_exterior`, e você escolhe qual vale depois de falar com o contador.
- Taxas pagas em BNB também são convertidas e lançadas.
- O relatório mensal exporta dados para a apuração e a declaração (data, ativo, quantidade, preço, taxas, custo médio, exchange).

**Consequências:**
- O lucro líquido "pós-imposto" é uma **estimativa** até a validação do contador.
- Se a regra mudar, cria-se nova versão do conjunto de regras sem reescrever o histórico. O recálculo é explícito.
