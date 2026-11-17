# ADR-003 — Redis Streams como barramento; Postgres como verdade local; exchange como verdade final

**Status:** aceita (2026-11-17)

**Contexto:** precisamos de comunicação assíncrona entre serviços, com reentrega e baixa operação. Kafka e RabbitMQ são pesados demais para uma VPS e para esse volume de dados.

**Decisão:**
- Usar Redis Streams com consumer groups e entrega "pelo menos uma vez".
- Consumidores idempotentes, com `processed_events` e chaves únicas (`client_order_id`, `trade_id`).
- Postgres guarda todo estado durável.
- Em caso de divergência, vale a exchange, e a reconciliação corrige o estado local.

**Consequências:**
- Perder o Redis não perde dados críticos: o boot reconcilia.
- O Redis fica com `noeviction` e AOF ligados.
- Os schemas dos eventos ficam versionados em `contracts/`.
