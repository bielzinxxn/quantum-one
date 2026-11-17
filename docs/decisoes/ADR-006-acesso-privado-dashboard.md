# ADR-006 — Dashboard e API sem exposição pública

**Status:** aceita provisoriamente (2026-11-17). Você não respondeu sobre exposição, então adotei o padrão seguro.

**Contexto:** o dashboard tem controles de kill, resume e flatten. Expor isso na internet aumenta muito a superfície de ataque.

**Decisão:**
- Nenhuma porta pública além de SSH.
- Acesso ao dashboard via Tailscale (preferido) ou túnel SSH.
- Mesmo dentro da VPN, há login com argon2id + TOTP e reautenticação nos comandos críticos.

**Consequências:**
- É preciso instalar o cliente Tailscale (ou equivalente) no seu computador e no celular.
- Se um dia quiser acesso público, isso vira uma nova ADR, com reverse proxy, TLS, WAF e rate limit.
