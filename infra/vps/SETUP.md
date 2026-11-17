# Preparação da VPS (São Paulo)

Passos manuais e revisáveis, para Ubuntu 24.04 LTS. Rode **você**, linha por linha. Nenhum script roda como root sem revisão.

## 1. Usuário e SSH
- Crie um usuário sem privilégios para operar o sistema (`adduser q1ops`) e adicione-o ao grupo `docker` depois do passo 3.
- Use SSH só com chave. Em `/etc/ssh/sshd_config`: `PasswordAuthentication no` e `PermitRootLogin no`. Depois, `systemctl restart ssh`.

## 2. Firewall, relógio e atualizações
```bash
sudo apt update && sudo apt install -y ufw fail2ban chrony unattended-upgrades
```
```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
```
```bash
sudo ufw allow OpenSSH && sudo ufw enable
```
```bash
chronyc tracking
```
O relógio importa: a Binance rejeita requisições fora do `recvWindow`. Confira se o `chronyc tracking` mostra um offset de poucos milissegundos.

## 3. Docker
Instale pelo repositório oficial: https://docs.docker.com/engine/install/ubuntu/

Atenção: o Docker escreve regras de iptables por conta própria e **ignora o ufw** para portas publicadas. Por isso o Compose só publica a API em `127.0.0.1`.

## 4. Acesso privado ao dashboard (ADR-006)
- **Opção A:** Tailscale (https://tailscale.com/kb/1031/install-linux). Depois de instalar, use `tailscale serve` apontando para `127.0.0.1:8000` e libere o SSH só pela interface do Tailscale.
- **Opção B:** túnel SSH a partir do seu computador:
```bash
ssh -N -L 8000:127.0.0.1:8000 q1ops@IP_DA_VPS
```

## 5. Projeto
```bash
git clone <seu-repo> quantum-one && cd quantum-one
```
```bash
make env && make build && make up && make smoke
```

## 6. Backup fora da VPS
- Gere um par de chaves [age](https://github.com/FiloSottile/age) **no seu computador** e coloque só a chave pública na VPS (`AGE_RECIPIENT`).
- Agende `make backup` (cron ou systemd timer) e envie `./backups` para um armazenamento externo.
- Teste a restauração uma vez por mês num Postgres descartável:
```bash
pg_restore --clean --if-exists -d <db_teste> arquivo.dump
```

## 7. Senhas do Postgres depois da instalação
Os scripts em `infra/postgres/init/` só rodam com o volume **vazio**. Para trocar uma senha depois, troque no `.env` **e** rode `ALTER ROLE q1_xxx PASSWORD '...'` no banco.

## 8. Chave de API da Binance (Fase 3: somente leitura)
A Binance recomenda chaves **Ed25519** e declara as chaves HMAC depreciadas (`faqs/api_key_types.md` na doc oficial). Com Ed25519, a chave **privada** é gerada na VPS e nunca sai de lá; a Binance só recebe a **pública**.

1. Na VPS, gere o par de chaves, sem compartilhar o arquivo privado com ninguém (nem comigo):
```bash
umask 077 && mkdir -p ~/binance-keys && cd ~/binance-keys
```
```bash
openssl genpkey -algorithm ed25519 -out private.pem
```
```bash
openssl pkey -in private.pem -pubout -out public.pem && cat public.pem
```
2. Em **API Management** na Binance, crie uma chave do tipo **Ed25519**, que a interface pode chamar de "auto-gerada" ou "self-generated", e cole o conteúdo de `public.pem`. Os nomes na interface podem mudar; o que importa é enviar só a chave pública.
3. Permissões: deixe **só leitura** (Enable Reading). **Não** habilite Spot/Margin Trading, saque, margem, futuros ou transferências.
4. Restrinja ao **IP fixo da VPS**. Em produção (`QONE_ENV=prod`) o sistema recusa chave sem restrição de IP.
5. No `.env`, coloque a API key em `BINANCE_API_KEY` e a chave **privada** numa linha só em `BINANCE_API_SECRET`:
```bash
printf 'BINANCE_API_SECRET="%s"\n' "$(awk 'BEGIN{ORS="\\n"} {print}' private.pem | sed 's/\\n$//')"
```
   Esse comando só imprime a linha pronta. Cole-a no `.env` no lugar do placeholder.
6. Valide:
```bash
make check-binance
```
   O esperado é `0`, com relógio OK, política da chave atendida, saldos listados e ordens abertas contadas.
   Os outros códigos de saída: `2` = política violada (o motivo aparece na saída), `4` = relógio, `1` = conexão/API, `3` = sem credenciais.
