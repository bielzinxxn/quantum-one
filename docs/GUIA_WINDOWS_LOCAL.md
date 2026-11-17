# Guia: rodar o QUANTUM ONE no seu Windows (Docker Desktop + WSL)

Esta opção é grátis e serve para validar e desenvolver. Ela **não é 24/7**: com o PC desligado ou dormindo, o sistema para. Quando voltar, ele reconecta e recupera as velas perdidas sozinho. Para paper trading e live, vamos migrar para uma VPS.

**Como usar:** copie cada bloco, cole e aperte Enter. Espere terminar antes do próximo.
**Nunca mande** o `.env`, o `private.pem` ou a API Key para ninguém, nem para o Claude.

---

## Parte 1 — Preparar o WSL (Linux dentro do Windows)

1. Abra o **PowerShell** e veja se já existe um Ubuntu:
```bash
wsl --list --verbose
```
   - Se aparecer **Ubuntu** com `VERSION 2`, pule para o item 3.
   - Se não aparecer, instale:
```bash
wsl --install -d Ubuntu-24.04
```
   Se o Windows pedir, reinicie o PC. Quando o Ubuntu abrir pela primeira vez, ele pede um **nome de usuário** e uma **senha**. Crie e **anote**; a senha não aparece enquanto você digita, e isso é normal.

2. Se o Ubuntu não abrir sozinho, abra pelo **Menu Iniciar → Ubuntu**.

3. No **Docker Desktop**: ⚙️ **Settings → Resources → WSL integration** → ative o **Ubuntu** → **Apply & restart**.

4. Abra o **Ubuntu** (Menu Iniciar → Ubuntu). A partir daqui, **todos os comandos são nessa janela do Ubuntu**, não no PowerShell. Teste o Docker:
```bash
docker compose version
```
✅ Deu certo se aparecer `Docker Compose version v2...`.

5. Instale as ferramentas (vai pedir a senha do Ubuntu):
```bash
sudo apt update && sudo apt install -y git make openssl python3
```

---

## Parte 2 — Baixar o projeto (repositório privado)

1. Crie uma chave para o Ubuntu acessar o GitHub, apertando **Enter** nas 3 perguntas sem digitar nada:
```bash
ssh-keygen -t ed25519 -C wsl-quantum-one
```
```bash
cat ~/.ssh/id_ed25519.pub
```
   Copie a linha que começa com `ssh-ed25519`. Ela é diferente da chave do PowerShell, porque o Ubuntu tem a pasta dele.

2. No navegador, abra https://github.com/bielzinxxn/quantum-one/settings/keys e clique em **Add deploy key**:
   - **Title:** `PC Windows`
   - **Key:** cole a linha
   - **NÃO** marque "Allow write access"
   - Clique em **Add key**.

3. No Ubuntu, baixe o projeto na sua pasta do Linux. Se perguntar `continue connecting?`, digite `yes`:
```bash
cd ~ && git clone git@github.com:bielzinxxn/quantum-one.git && cd quantum-one
```

---

## Parte 3 — Ligar o sistema

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
✅ Deu certo se a última linha for **`SMOKE OK`**. Se aparecer `FALHA`, me mande a saída.

---

## Parte 4 — Chave da Binance (só leitura)

1. Gere a chave no Ubuntu. A privada fica no seu PC; só a pública vai para a Binance:
```bash
mkdir -p ~/binance-keys && chmod 700 ~/binance-keys
```
```bash
openssl genpkey -algorithm ed25519 -out ~/binance-keys/private.pem && chmod 600 ~/binance-keys/private.pem
```
```bash
openssl pkey -in ~/binance-keys/private.pem -pubout
```
   Copie as **3 linhas**, de `-----BEGIN PUBLIC KEY-----` até `-----END PUBLIC KEY-----`.

2. Descubra o IP da sua internet:
```bash
curl -4 ifconfig.me
```

3. Na Binance, vá em **Perfil → Gerenciamento de API → Criar API**:
   - escolha a chave **gerada por você** (Ed25519, "Self-generated"/"Autogerada") e cole a chave pública;
   - permissões: ✅ **só "Ativar leitura"**; ❌ trading, saque, margem, futuros e transferências desmarcados;
   - **Restrição de IP:** coloque o IP do item 2;
   - salve e deixe aberta a tela com a **API Key**.

4. Grave a chave no sistema. Cole a **API Key** quando o comando pedir; ela não aparece na tela, e isso é normal:
```bash
make set-binance-key PEM=~/binance-keys/private.pem
```

5. Reinicie e teste:
```bash
make up
```
```bash
make check-binance
```
✅ Deu certo se aparecer **`[OK] política da chave atendida`** e os seus saldos.

**Atenção ao IP de casa:** a operadora pode trocar o IP da sua internet. Se um dia o `make check-binance` der erro `auth` com código `-2015`, rode `curl -4 ifconfig.me` de novo e atualize o IP na Binance.

---

## Parte 5 — Conferir (15 minutos depois)

```bash
make status
```
✅ O esperado é `"connected": true`, `"stale": 0` e `"trading_state": "BLOCKED"`. O BLOCKED é o certo: o sistema ainda não tem permissão para operar.

Depois de 1 hora com o PC ligado, cada par deve mostrar **60**:
```bash
make velas
```

---

## Dia a dia (sempre no Ubuntu, dentro de `~/quantum-one`)

| Para… | Comando |
|---|---|
| voltar para a pasta do projeto | `cd ~/quantum-one` |
| ver se está tudo bem | `make status` |
| ligar | `make up` |
| desligar | `make down` |
| ver logs (sair com Ctrl+C) | `make logs s=marketdata` |
| atualizar depois de uma fase nova | `git pull && make build && make up` |

**Se der erro:** me mande o comando, a mensagem inteira e a saída de `make status`.
