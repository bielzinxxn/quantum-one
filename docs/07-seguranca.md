# 07 — Plano de segurança

## Chaves da Binance
- Uma chave **só para leitura** nas Fases 3–8 e uma chave de **trading spot** só a partir da liberação de live. Nunca ativar saque, margem, futuros ou transferência universal.
- **Restrição por IP** ao IP fixo da VPS. A Binance oferece; ative.
- Tipo de chave: preferir **Ed25519** se a doc oficial confirmar suporte no CCXT para os endpoints usados. Verificar na Fase 3; se não houver suporte, usar HMAC.
- Rodízio a cada 90 dias e imediatamente em caso de suspeita de vazamento.
- Você cria as chaves. Eu só uso placeholders (`BINANCE_API_KEY=__placeholder__`).

## Segredos
- Ficam só em variáveis de ambiente, em `.env` com permissão 600 e fora do Git. O `.env.example` contém só placeholders.
- Cada contêiner recebe **apenas** os segredos de que precisa: a chave de trading vai só para o `trader`, nunca para `api` nem `dashboard`.
- Pre-commit com **gitleaks** e o mesmo check no CI.
- Logs com filtro de redação no structlog: chaves, assinaturas, tokens e `listenKey` viram `***`.

## Acesso administrativo
- Dashboard e API **sem porta pública**. Acesso via Tailscale ou WireGuard, ou túnel SSH (ADR-006).
- **Login:** senha com argon2id + **TOTP** obrigatório. Sessão em cookie `httpOnly`, `Secure`, `SameSite=Strict`, de curta duração.
- **Comandos críticos** (resume após kill, liberação de estágio, `flatten`, mudança de limites de risco) exigem TOTP de novo, **nonce** de uso único e timestamp com janela curta, o que protege contra replay.
- Toda ação administrativa vai para `audit_log` com hash encadeado, verificável por script.

## Aplicação
- Entrada validada com Pydantic em toda borda (API, eventos, respostas da exchange).
- SQL **só parametrizado** (asyncpg / SQLAlchemy Core). Proibido montar SQL com f-string; o linter tem regra para isso.
- Papéis de banco com mínimo privilégio (ver 05). A API é somente leitura.
- CORS restrito à origem do dashboard, CSRF token, rate limit no login.
- Dependências fixadas, com `pip-audit` e `npm audit` no CI e atualização mensal.

## Dados sensíveis
- O segredo TOTP fica cifrado no banco (chave mestra em variável de ambiente).
- Backups do Postgres cifrados (age) e enviados para fora da VPS. Teste de restauração mensal.
- Disco da VPS: usar criptografia em repouso se o provedor oferecer.

## Infra (VPS)
- SSH só com chave, sem root e sem senha. fail2ban, ufw negando tudo que entra exceto SSH (de preferência só pela VPN).
- Atualizações de segurança automáticas. chrony para o relógio.
- Contêineres com usuário não root, `read_only: true` onde possível, `cap_drop: ALL`, imagens com versão e digest fixados.
- Postgres e Redis só na rede interna do Compose. Redis com senha e `rename-command` para FLUSHALL, CONFIG e KEYS.

## Riscos residuais (aceitos e explícitos)
- Se a VPS for comprometida, um atacante com root lê o `.env`. A mitigação é chave sem saque e restrita ao IP: o pior caso vira operar mal com seu saldo, não roubar. O kill switch e os limites diários reduzem o estrago.
- A Binance é uma contraparte centralizada (risco de custódia). Fora do escopo do software.
