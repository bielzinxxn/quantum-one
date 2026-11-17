# Guia passo a passo: colocar o QUANTUM ONE para rodar na VPS

Este guia é para quem nunca fez isso. Faça na ordem, sem pular.

**Como usar os comandos:** cada bloco cinza é um comando. Copie, cole no terminal e aperte **Enter**. Espere terminar (o cursor volta a piscar) antes de ir para o próximo.

**Regra de ouro:** nunca mande para ninguém, nem para o Claude, o conteúdo do arquivo `.env` ou da chave `private.pem`.

---

## Parte 1 — Criar uma chave SSH no SEU computador (5 min)

A chave SSH é como uma "senha que não se digita": serve para o seu computador entrar na VPS com segurança.

1. **No Windows**, abra o **PowerShell**: tecla Windows, digite `powershell`, Enter. **No Mac**, abra o **Terminal**.
2. Rode o comando abaixo e aperte **Enter** em todas as perguntas, deixando tudo em branco:
```bash
ssh-keygen -t ed25519
```
3. Mostre a chave **pública** (é seguro mostrar esta):
```bash
cat ~/.ssh/id_ed25519.pub
```
4. Copie a linha inteira que aparecer, que começa com `ssh-ed25519`. Você vai usá-la na Parte 2.

---

## Parte 2 — Contratar a VPS (10 min)

Use qualquer provedor com **datacenter em São Paulo**, por exemplo Vultr, AWS (região `sa-east-1`) ou Hostinger. Na hora de criar o servidor, escolha:

| Opção | Escolha |
|---|---|
| Sistema | **Ubuntu 24.04 LTS** |
| Local | **São Paulo** |
| Memória | **8 GB** (4 GB funciona, mas no limite) |
| Disco | 80 GB ou mais |
| Chave SSH | cole a linha `ssh-ed25519 ...` da Parte 1 |

Quando o servidor estiver pronto, **anote o IP** (algo como `200.123.45.67`). No resto do guia, onde estiver `SEU_IP`, troque pelo IP de verdade.

---

## Parte 3 — Entrar na VPS e prepará-la (15 min)

1. No PowerShell ou Terminal do **seu computador**:
```bash
ssh root@SEU_IP
```
Se perguntar `Are you sure you want to continue connecting?`, digite `yes` e Enter. Agora você está **dentro da VPS**: os próximos comandos rodam nela.

2. Atualize o sistema (pode levar alguns minutos):
```bash
apt update && apt upgrade -y
```
Se aparecer uma tela roxa perguntando sobre serviços, aperte **Enter**.

3. Instale as ferramentas:
```bash
apt install -y git make chrony ufw
```

4. Instale o Docker, usando o script oficial da própria Docker:
```bash
curl -fsSL https://get.docker.com | sh
```

5. Crie um usuário para o sistema (não é bom usar o `root` no dia a dia). Ele vai pedir uma senha: **crie uma forte e anote**. Nas outras perguntas, só Enter:
```bash
adduser q1ops
```
```bash
usermod -aG sudo,docker q1ops
```
```bash
rsync --archive --chown=q1ops:q1ops ~/.ssh /home/q1ops
```

6. Ligue o firewall. Ele bloqueia tudo que vem de fora, menos o SSH:
```bash
ufw allow OpenSSH && ufw --force enable
```

7. Confira o relógio, que precisa estar certo para a Binance aceitar as requisições:
```bash
chronyc tracking
```
Procure a linha `System time`: o número precisa ser bem pequeno, como `0.000123 seconds`.

8. Saia da VPS:
```bash
exit
```

---

## Parte 4 — Entrar com o usuário novo e baixar o projeto (10 min)

1. No **seu computador**:
```bash
ssh q1ops@SEU_IP
```

2. Como o repositório é **privado**, a VPS precisa de permissão para baixá-lo. Crie uma chave para a VPS, apertando Enter em todas as perguntas:
```bash
ssh-keygen -t ed25519 -C vps-quantum-one
```
```bash
cat ~/.ssh/id_ed25519.pub
```
Copie a linha que aparecer.

3. No navegador, abra https://github.com/bielzinxxn/quantum-one/settings/keys e clique em **Add deploy key**:
   - **Title:** `VPS`
   - **Key:** cole a linha
   - **NÃO** marque "Allow write access" (a VPS só precisa ler)
   - Clique em **Add key**.

4. De volta à VPS, baixe o projeto. Se perguntar `continue connecting?`, digite `yes`:
```bash
git clone git@github.com:bielzinxxn/quantum-one.git && cd quantum-one
```

---

## Parte 5 — Ligar o sistema (15 min)

Ainda na VPS, dentro da pasta `quantum-one`:

1. Gere as senhas internas automaticamente:
```bash
make env
```

2. Monte o sistema. Na primeira vez leva alguns minutos:
```bash
make build
```

3. Ligue o sistema:
```bash
make up
```

4. Rode o teste completo:
```bash
make smoke
```
✅ **Deu certo** se a última linha for `SMOKE OK`. Se aparecer `FALHA`, pare aqui e me mande a saída.

---

## Parte 6 — Criar a chave da Binance, só leitura (15 min)

1. Na VPS, gere a chave. A parte **privada** fica guardada na VPS; só a **pública** vai para a Binance:
```bash
mkdir -p ~/binance-keys && chmod 700 ~/binance-keys
```
```bash
openssl genpkey -algorithm ed25519 -out ~/binance-keys/private.pem && chmod 600 ~/binance-keys/private.pem
```
```bash
openssl pkey -in ~/binance-keys/private.pem -pubout
```
Copie as **3 linhas** que aparecerem: `-----BEGIN PUBLIC KEY-----`, a linha do meio e `-----END PUBLIC KEY-----`.

2. Descubra o IP da VPS como a Binance vai enxergá-lo:
```bash
curl -4 ifconfig.me
```

3. No site da Binance: **Perfil → Gerenciamento de API → Criar API**.
   - Escolha o tipo de chave **gerada por você** (Ed25519; pode aparecer como "Self-generated" ou "Autogerada").
   - Cole a chave **pública** do item 1.
   - Confirme com o seu 2FA.

4. Na chave criada, clique em **Editar restrições** e deixe assim:
   - ✅ **Ativar leitura** (Enable Reading)
   - ❌ **Spot & Margin Trading desmarcado**
   - ❌ **Saques desmarcados**
   - ❌ Margem, futuros e transferências: tudo desmarcado
   - **Restrição de IP:** escolha "Restringir a IPs confiáveis" e coloque o IP do item 2

   Salve. A Binance vai mostrar a **API Key**, um código longo. Deixe essa tela aberta.

5. Na VPS, grave a chave no sistema com o comando abaixo. Quando ele pedir, **cole a API Key** e aperte Enter. Ela não aparece na tela, e isso é normal:
```bash
make set-binance-key PEM=~/binance-keys/private.pem
```

6. Reinicie e teste a conexão com a Binance:
```bash
make up
```
```bash
make check-binance
```
✅ **Deu certo** se aparecer `[OK] política da chave atendida` e os seus saldos.

❌ Se aparecer `[FALHA] chave: ...`, a frase diz o que está errado (por exemplo "saque habilitado"). Corrija na Binance e rode `make check-binance` de novo.

---

## Parte 7 — Conferir o scanner (espere 15 minutos depois da Parte 6)

1. Estado geral:
```bash
make status
```
✅ No bloco `marketdata`, procure `"connected": true` e `"stale": 0`. No bloco `trader`, procure `"state": "ok"` e `"trading_state": "BLOCKED"`. BLOCKED é o certo: o sistema ainda não tem permissão para operar.

2. Velas gravadas. Depois de 1 hora ligado, cada par deve ter **60**:
```bash
make velas
```

---

## Deu erro? Me mande isto

- O **comando** que você rodou e a **mensagem de erro**, copiada inteira.
- O resultado de:
```bash
make status
```
```bash
make logs s=marketdata
```
Para sair dos logs, aperte **Ctrl+C**.

**Nunca mande:** o arquivo `.env`, o `private.pem` ou a API Key.

## Comandos do dia a dia (sempre dentro de `~/quantum-one`)

| Para… | Comando |
|---|---|
| ver se está tudo bem | `make status` |
| ligar | `make up` |
| desligar | `make down` |
| ver os logs | `make logs s=marketdata` |
| atualizar o código depois de uma fase nova | `git pull && make build && make up` |
