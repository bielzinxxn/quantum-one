# Guia passo a passo (Windows + VPS nova + Binance)

Siga **na ordem**. Cada bloco cinza é um comando: copie, cole e aperte Enter.
Se algo der erro, pare e me mande a mensagem de erro. **Nunca mande chaves, senhas ou o arquivo `.env`.**

Tempo total: cerca de 1h30. **Não precisa depositar dinheiro**: nesta etapa o sistema só LÊ dados.

---

## Parte 1 — Criar sua chave de acesso no Windows (5 min)
É a "chave de casa" para entrar na VPS sem senha.

1. Aperte a tecla Windows, digite **PowerShell** e abra.
2. Rode o comando abaixo e aperte Enter em todas as perguntas, para aceitar o local padrão. Se quiser, defina uma senha para a chave.
```powershell
ssh-keygen -t ed25519 -C "quantum-one"
```
3. Mostre a parte **pública** da chave e copie a linha inteira, que começa com `ssh-ed25519`:
```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```
O arquivo sem `.pub` é a parte **privada**. Esse você nunca envia para ninguém.

---

## Parte 2 — Contratar a VPS (15 min)
Escolha um provedor que tenha datacenter em **São Paulo**, por exemplo a Vultr, que tem a região São Paulo. Confira preço e disponibilidade no site.

Configuração:
- **Sistema:** Ubuntu 24.04 LTS
- **Região:** São Paulo
- **Plano:** 8 GB de RAM, 2 a 4 vCPU e 80 GB de SSD ou mais. Com 4 GB funciona, mas fica no limite.
- **SSH Key:** cole a linha `ssh-ed25519 ...` da Parte 1. Isso é importante.

Depois de criada, anote o **IP** da VPS. Nos comandos abaixo, troque `SEU_IP` por ele.

---

## Parte 3 — Configurar a VPS (20 min)

### 3.1 Primeiro acesso (no PowerShell)
```powershell
ssh root@SEU_IP
```
Na pergunta "Are you sure you want to continue connecting", digite `yes`. A partir daqui, os comandos rodam **dentro da VPS**.

### 3.2 Atualizar e instalar o básico
```bash
apt update && apt -y upgrade
```
```bash
apt install -y ufw fail2ban chrony unattended-upgrades git make python3
```

### 3.3 Criar seu usuário (não usar root no dia a dia)
Defina uma senha quando pedir. As outras perguntas pode deixar em branco.
```bash
adduser q1ops
```
```bash
usermod -aG sudo q1ops
```
```bash
mkdir -p /home/q1ops/.ssh && cp /root/.ssh/authorized_keys /home/q1ops/.ssh/ && chown -R q1ops:q1ops /home/q1ops/.ssh && chmod 700 /home/q1ops/.ssh && chmod 600 /home/q1ops/.ssh/authorized_keys
```

### 3.4 Testar o novo usuário ANTES de bloquear o root
Abra **outra** janela do PowerShell, sem fechar a primeira, e rode:
```powershell
ssh q1ops@SEU_IP
```
Só continue se esse login funcionou. Se não funcionou, volte na primeira janela e me avise.

### 3.5 Firewall e segurança do SSH (na janela do q1ops)
```bash
sudo ufw allow OpenSSH && sudo ufw --force enable
```
```bash
printf 'PasswordAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/00-quantum.conf
```
```bash
sudo sshd -t && sudo systemctl restart ssh
```
Confira o relógio. O "System time" precisa estar perto de 0 segundos:
```bash
chronyc tracking
```

### 3.6 Instalar o Docker (repositório oficial)
```bash
sudo install -m 0755 -d /etc/apt/keyrings && sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && sudo chmod a+r /etc/apt/keyrings/docker.asc
```
```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```
```bash
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```
```bash
sudo usermod -aG docker q1ops
```
Saia (`exit`) e entre de novo com `ssh q1ops@SEU_IP`, para a permissão do Docker valer. Teste:
```bash
docker run --rm hello-world
```
O esperado é aparecer "Hello from Docker!".

---

## Parte 4 — Baixar e subir o sistema (20 min)

### 4.1 Dar à VPS permissão de LER o repositório privado
Crie uma chave só para isso:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_quantum -N "" -C "vps-quantum"
```
```bash
cat ~/.ssh/github_quantum.pub
```
Copie a linha. No GitHub, abra o repositório **quantum-one**, vá em **Settings → Deploy keys → Add deploy key**, cole a linha e deixe **"Allow write access" DESMARCADO**. Salve.

Agora diga à VPS para usar essa chave com o GitHub:
```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/github_quantum\n  IdentitiesOnly yes\n' >> ~/.ssh/config && chmod 600 ~/.ssh/config
```

### 4.2 Baixar o projeto
Se perguntar "continue connecting", digite `yes`.
```bash
git clone git@github.com:bielzinxxn/quantum-one.git && cd quantum-one
```

### 4.3 Gerar as senhas internas e subir
O build demora alguns minutos na primeira vez.
```bash
make env
```
```bash
make build
```
```bash
make up
```
```bash
make smoke
```
O esperado é a última linha mostrar **SMOKE OK**. Nesse momento ainda vai aparecer `exchange.state = credentials_missing`. Isso é normal, porque a chave da Binance vem na Parte 5.

---

## Parte 5 — Binance: conta e chave SOMENTE LEITURA (20 min)

### 5.1 Conta
1. Crie a conta em binance.com e faça a verificação de identidade (KYC).
2. Ligue a **autenticação em dois fatores (2FA)**, com um app autenticador. Sem 2FA a Binance não deixa criar chave de API.
3. **Não deposite nada.** Não é necessário nesta fase.

### 5.2 Gerar o par de chaves NA VPS
A chave privada nasce e fica na VPS. A Binance só recebe a pública.
```bash
umask 077 && mkdir -p ~/binance-keys && openssl genpkey -algorithm ed25519 -out ~/binance-keys/private.pem
```
```bash
openssl pkey -in ~/binance-keys/private.pem -pubout
```
Copie tudo o que aparecer, **incluindo** as linhas `-----BEGIN PUBLIC KEY-----` e `-----END PUBLIC KEY-----`.

### 5.3 Criar a API na Binance
1. No site da Binance: **Perfil → API Management → Create API**.
2. Escolha a opção de chave **Ed25519**. A interface pode chamar de "Self-generated" ou "auto-gerada", e os nomes podem mudar.
3. Cole a chave **pública** do passo 5.2 e confirme com o 2FA.
4. Nas permissões, deixe **somente "Enable Reading"**. NÃO marque Spot Trading, Withdrawals (saque), Margin, Futures nem transferências.
5. Em restrição de IP, escolha **"Restrict access to trusted IPs only"** e coloque o **IP da VPS**.
6. Copie o **API Key** que a Binance mostrar.

### 5.4 Colocar a chave no sistema
Na VPS, dentro da pasta `quantum-one`, gere a linha da chave privada já no formato certo:
```bash
printf 'BINANCE_API_SECRET="%s"\n' "$(awk 'BEGIN{ORS="\\n"} {print}' ~/binance-keys/private.pem | sed 's/\\n$//')"
```
Abra o arquivo de configuração:
```bash
nano .env
```
No `nano`, procure as duas linhas abaixo e troque os valores:
- `BINANCE_API_KEY=__placeholder__`: troque `__placeholder__` pelo **API Key** que a Binance mostrou.
- `BINANCE_API_SECRET=__placeholder__`: apague a linha inteira e cole a linha que o comando `printf` imprimiu.

Para salvar e sair: **Ctrl+O**, **Enter**, **Ctrl+X**.

### 5.5 Reiniciar e testar
```bash
docker compose up -d
```
```bash
make check-binance
```
O esperado é ver **[OK]** em tudo e a linha "política da chave atendida". Os saldos aparecem zerados, e tudo bem.
Se aparecer **[FALHA]**, a própria mensagem diz o motivo, por exemplo "saque habilitado" ou "sem restrição de IP". Corrija na Binance e rode de novo.

---

## Parte 6 — Conferir o Market Scanner (depois de 15 min ligado)

Estado do scanner. O esperado é `"connected": true`, `"universe"` perto de 30 e `"stale": 0`:
```bash
docker compose exec marketdata python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8080/health/ready').read().decode())"
```
Velas da última hora do BTC. O esperado é **60**:
```bash
docker compose exec postgres psql -U postgres -d quantum_one -c "SELECT count(*) FROM q1.candles WHERE symbol='BTCUSDT' AND open_time > now() - interval '1 hour';"
```

---

## Parte 7 — O que me mandar
Copie e cole aqui a **saída** destes três comandos. Se quiser, apague os valores dos saldos antes:
1. `make smoke`, só as linhas finais
2. `make check-binance`
3. Os dois comandos da Parte 6

**Nunca** cole o conteúdo do `.env`, do `private.pem` ou o API Key.

---

## Comandos úteis depois
| Para… | Comando |
|---|---|
| Entrar na VPS (no PowerShell) | `ssh q1ops@SEU_IP` e depois `cd quantum-one` |
| Ver se está tudo de pé | `make ps` |
| Ver os logs de um serviço | `make logs s=marketdata` (Ctrl+C para sair) |
| Parar tudo | `make down` |
| Ligar de novo | `make up` |
| Atualizar para a versão nova do código | `git pull && make build && make up` |
