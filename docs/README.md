# Documentação — QUANTUM ONE

Comece por [`ESTADO_DO_PROJETO.md`](ESTADO_DO_PROJETO.md).

| Documento | Conteúdo |
|---|---|
| [01-arquitetura](01-arquitetura.md) | Princípios, diagrama Mermaid, modos de operação, latência, riscos |
| [02-estrutura-de-diretorios](02-estrutura-de-diretorios.md) | Árvore do monorepo e regras de dependência |
| [03-servicos](03-servicos.md) | Responsabilidade, entradas, saídas e falhas de cada serviço |
| [04-fluxo-de-dados](04-fluxo-de-dados.md) | Diagramas de sequência: mercado → sinal → ordem → contabilidade; reconexão; kill switch; validação |
| [05-modelo-de-dados](05-modelo-de-dados.md) | Diagrama de relacionamentos e tabelas do Postgres |
| [06-comunicacao](06-comunicacao.md) | Envelope de eventos, streams, idempotência, TTL |
| [07-seguranca](07-seguranca.md) | Chaves, segredos, acesso, hardening, riscos residuais |
| [08-testes](08-testes.md) | Camadas de teste, invariantes, falhas, o que não dá para testar aqui |
| [decisoes/](decisoes/) | ADR-001 a ADR-007 |
