# Rodar num servidor

O Rotina **não tem login**. Em qualquer caminho abaixo, o acesso de fora passa por uma camada
que pede login ou senha antes de chegar ao app. Nunca exponha a porta 5001 direto na internet.

| Caminho | Quando usar |
|---|---|
| [Docker](#1-subir-o-app) | Qualquer máquina com Docker: VPS, servidor em casa, Raspberry Pi (64 bits) |
| [PythonAnywhere](#sem-docker-pythonanywhere) | Sem servidor próprio e sem linha de comando; tem plano grátis |
| [VPS com systemd](#sem-docker-vps-com-systemd) | Servidor Linux próprio, sem Docker |

> Vercel, Netlify e Cloudflare Pages/Workers **não servem**: o banco é um arquivo SQLite, e
> nessas plataformas o disco é temporário ou inexistente. Os dados se perderiam.

## 1. Subir o app

O `docker-compose.yml` abre a porta só para o próprio servidor (`127.0.0.1`).


```bash
git clone https://github.com/andrecccruz/rotina.git
cd rotina
cp .env.example .env        # preencha a chave da IA (opcional) e um ROTINA_SECRET
docker compose up -d --build
```

Teste no próprio servidor: `curl -I http://127.0.0.1:5001`.

- **`ROTINA_SECRET`**: um texto aleatório longo, por exemplo `openssl rand -hex 32`.
- **Dados**: ficam no volume `dados` (banco + log da IA) e sobrevivem a atualizações.
- **IA ou outro fuso**: descomente a linha do `config.json` no `docker-compose.yml`, edite o
  arquivo e rode `docker compose up -d`.
- **Atualizar**: `git pull && docker compose up -d --build`.

## 2. Acesso de fora, com login

### Opção A — Cloudflare Tunnel + Access (precisa de um domínio na Cloudflare)

O túnel liga o servidor à Cloudflare sem abrir porta no roteador ou no firewall, e o Access
pede login (código por e-mail) antes de qualquer requisição chegar ao app.

1. No painel **Cloudflare Zero Trust → Networks → Tunnels**, crie um túnel do tipo
   *Cloudflared* e copie o token para `TUNNEL_TOKEN` no `.env`.
2. No túnel, adicione um **Public hostname**, por exemplo `rotina.seudominio.com`, com o
   serviço `http://rotina:5001`.
3. Em **Access → Applications**, crie uma aplicação *Self-hosted* para o mesmo endereço,
   com uma política *Allow* só para o seu e-mail.
4. Suba o túnel junto com o app:

   ```bash
   docker compose --profile tunel up -d
   ```

Faça o passo 3 **antes** de compartilhar o endereço: sem ele, o app fica aberto.

### Opção B — Tailscale (sem domínio)

A rede do Tailscale só aceita os seus dispositivos, então ela mesma faz o papel do login.

1. Instale o Tailscale no servidor e no celular/computador, na mesma conta.
2. No `docker-compose.yml`, troque `127.0.0.1:5001:5001` pelo IP do servidor no Tailscale
   (`tailscale ip -4`), por exemplo `100.101.102.103:5001:5001`.
3. `docker compose up -d` e abra `http://100.101.102.103:5001` em qualquer dispositivo seu.

## Backup e migração (Docker)

```bash
# Copiar o banco do servidor para a pasta atual
docker compose cp rotina:/app/dados/rotina.db ./rotina-backup.db
```

Para levar um banco que você já usa no Windows para o servidor:

```bash
docker compose stop rotina
docker run --rm -v rotina_dados:/dados -v "$PWD":/origem alpine \
  sh -c "cp /origem/rotina.db /dados/rotina.db && chown 1000:1000 /dados/rotina.db"
docker compose start rotina
```

O nome do volume é `<pasta>_dados`; confira com `docker volume ls`.

## Sem Docker: PythonAnywhere

O [PythonAnywhere](https://www.pythonanywhere.com) roda apps Flask e guarda arquivos de forma
permanente, então o SQLite funciona como no seu computador. A proteção por senha do próprio
painel faz o papel do login.

1. Crie uma conta. O plano grátis (*Beginner*) serve.
2. Em **Consoles → Bash**:

   ```bash
   git clone https://github.com/andrecccruz/rotina.git
   cd rotina
   mkvirtualenv --python=python3.12 rotina
   pip install -r requirements.txt
   cp .env.example .env
   ```

   Edite o `.env` na aba **Files** e preencha `ROTINA_SECRET` com um texto aleatório longo.
3. Na aba **Web**, clique em **Add a new web app → Manual configuration → Python 3.12**.
4. Ainda na aba **Web**:
   - **Source code**: `/home/SEU_USUARIO/rotina`
   - **Virtualenv**: `/home/SEU_USUARIO/.virtualenvs/rotina`
   - **Static files**: URL `/static/` → diretório `/home/SEU_USUARIO/rotina/rotina/static`
5. Abra o **WSGI configuration file** (link na aba Web), apague o conteúdo e deixe só:

   ```python
   import sys
   sys.path.insert(0, "/home/SEU_USUARIO/rotina")
   from app import app as application
   ```

6. Na seção **Security** da aba Web, ligue **Force HTTPS** e **Password protection**, com um
   usuário e uma senha. Faça isso **antes** de abrir o endereço para alguém.
7. Clique em **Reload** e abra `https://SEU_USUARIO.pythonanywhere.com`.

Observações:
- **Plano grátis**: o app fica no ar por 3 meses. Para renovar, clique em
  *Run until 3 months from today* na aba Web.
- **IA**: no plano grátis, o acesso à internet é limitado a uma lista de sites liberados pelo
  PythonAnywhere. Se a Azure OpenAI não estiver na lista, a IA não conecta (o resto do app
  funciona normalmente). Os planos pagos não têm essa limitação.
- **Fuso**: o servidor fica em outro fuso, mas o app usa o `fuso_horario` do `config.json`.
- **Backup**: na aba **Files**, baixe `rotina/dados/rotina.db`. Para levar o banco que você
  já usa, envie o arquivo para essa mesma pasta e clique em **Reload**.
- **Atualizar**: `cd ~/rotina && git pull` no console e **Reload** na aba Web.

## Sem Docker: VPS com systemd

Para um servidor Linux (Debian/Ubuntu) sem Docker. O app roda com gunicorn como serviço do
sistema e escuta só em `127.0.0.1`.

```bash
sudo apt install -y python3-venv git
sudo git clone https://github.com/andrecccruz/rotina.git /opt/rotina
cd /opt/rotina
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt gunicorn==23.0.0
sudo cp .env.example .env          # preencha ROTINA_SECRET e, se quiser, a chave da IA
sudo useradd --system --home /opt/rotina rotina
sudo chown -R rotina:rotina /opt/rotina/dados
sudo chown rotina:rotina /opt/rotina/.env && sudo chmod 600 /opt/rotina/.env
```

Crie `/etc/systemd/system/rotina.service`:

```ini
[Unit]
Description=Rotina
After=network.target

[Service]
User=rotina
WorkingDirectory=/opt/rotina
ExecStart=/opt/rotina/.venv/bin/gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5001 app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rotina
curl -I http://127.0.0.1:5001
```

Para o acesso de fora, siga a [seção 2](#2-acesso-de-fora-com-login), com estas diferenças:
- **Cloudflare Tunnel**: instale o `cloudflared` direto no servidor
  (`sudo cloudflared service install <TOKEN>`) e use o serviço `http://127.0.0.1:5001`.
- **Tailscale**: no `ExecStart`, troque `127.0.0.1:5001` pelo IP do servidor no Tailscale.
- **nginx ou Caddy na frente**: acrescente `Environment=ROTINA_PROXY=1` na seção `[Service]`.

- **Backup**: copie `/opt/rotina/dados/rotina.db`.
- **Atualizar**: `cd /opt/rotina && sudo git pull && sudo systemctl restart rotina`.

## Proxy reverso próprio (nginx, Caddy, Traefik)

A imagem já liga `ROTINA_PROXY=1`, que faz o app usar o `X-Forwarded-Host` na proteção de
origem dos formulários. Configure o proxy para enviar esse cabeçalho (ou repassar o `Host`
original) e coloque autenticação nele, como *basic auth* ou *forward auth*.
