# Deploy do PDV na Hostinger – Passo a passo detalhado

Repositório: **https://github.com/wdsc1989/pdv**

Objetivo: publicar o PDV no subdomínio **pdv.srv1140258.hstgr.cloud**, no mesmo servidor onde você já tem outros sistemas (ex.: **n8n.srv1140258.hstgr.cloud**). Diretórios separados na VPS (como no contábil), com **PostgreSQL** criado na própria VPS como novo database.

---

## Deploy via PowerShell (tudo da sua máquina)

Você pode fazer **todo o deploy da sua máquina Windows** pelo PowerShell. O script envia os arquivos para a VPS e executa a instalação lá (diretórios separados, novo banco PostgreSQL, Nginx, systemd).

### Estrutura na VPS (como no contábil)

- Um diretório por aplicação, por exemplo:
  - `~/apps/contabil` (ou como você já tem)
  - `~/apps/pdv` ← PDV
- O **banco de dados** é um **novo database PostgreSQL** criado na VPS (usuário e banco novos, não compartilhados).

### Pré-requisitos no seu PC

- **PowerShell 5.1** ou superior (já vem no Windows).
- **OpenSSH** (cliente `ssh` e `scp`). No Windows 10/11: Configurações → Aplicativos → Recursos opcionais → “Cliente OpenSSH”.
- Ter em mãos: **host da VPS**, **usuário SSH**, **senha do SSH** (ou chave) e uma **senha para o usuário PostgreSQL** (será criado na VPS).
- Se o PowerShell reclamar de “execução de scripts”, execute uma vez: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
- **Senha do PostgreSQL:** use uma senha sem aspas simples, dois-pontos ou arroba (evita problemas na URL do `.env`).

### Um comando (pede o que faltar)

Na pasta do projeto PDV (onde está `app.py` e a pasta `scripts`):

```powershell
cd C:\Users\DELL\Documents\Projetos\PDV
.\scripts\Deploy-PDV.ps1
```

O script vai pedir (se não passar por parâmetro):

- **Host da VPS:** ex. `srv1140258.hstgr.cloud`
- **Usuário SSH:** ex. `u123456789`
- **Senha do usuário PostgreSQL:** será usada para criar o usuário/banco e o `.env`

Parâmetros opcionais (diretório e banco):

```powershell
.\scripts\Deploy-PDV.ps1 -VpsHost srv1140258.hstgr.cloud -SshUser u123456789 -AppDir "apps/pdv" -DbName pdv_db -DbUser pdv_user
# A senha do banco será pedida de forma segura
```

Com chave SSH:

```powershell
.\scripts\Deploy-PDV.ps1 -VpsHost srv1140258.hstgr.cloud -SshUser u123456789 -SshKeyPath "C:\caminho\para\sua_chave"
```

### O que o script faz na VPS

1. Cria o diretório da aplicação (ex.: `~/apps/pdv`).
2. **PostgreSQL na VPS:** cria o usuário e o **novo database** (ex.: `pdv_db`).
3. Clona o repositório (ou dá `git pull` se já existir).
4. Cria o venv, instala dependências, gera o `.env` com `DATABASE_URL` apontando para esse banco.
5. Roda `init_db.py` (tabelas + admin).
6. Configura o Nginx para **pdv.srv1140258.hstgr.cloud**.
7. Cria e ativa o serviço systemd **pdv-streamlit**.

### Exigências na VPS

- **PostgreSQL** instalado (ex.: `sudo apt install postgresql postgresql-contrib`). No mesmo servidor do contábil/n8n isso costuma já estar instalado.
- **Python 3.10+**, **Nginx**, **sudo** para o seu usuário. Se algo falhar, o script mostra a mensagem (ex.: pedir para instalar o PostgreSQL).

Depois do deploy, acesse **http://pdv.srv1140258.hstgr.cloud** e faça login com **admin** / **admin123** (altere em produção).

---

## Índice (passo a passo manual)

1. [Pré-requisitos e informações do servidor](#1-pré-requisitos-e-informações-do-servidor)
2. [Criar o subdomínio no painel Hostinger](#2-criar-o-subdomínio-no-painel-hostinger)
3. [Conectar ao servidor por SSH](#3-conectar-ao-servidor-por-ssh)
4. [Verificar/instalar Python no servidor](#4-verificarinstalar-python-no-servidor)
5. [Clonar o repositório e instalar dependências](#5-clonar-o-repositório-e-instalar-dependências)
6. [Configurar o banco de dados](#6-configurar-o-banco-de-dados)
7. [Arquivo .env e variáveis de ambiente](#7-arquivo-env-e-variáveis-de-ambiente)
8. [Inicializar o banco e testar o app](#8-inicializar-o-banco-e-testar-o-app)
9. [Configurar Nginx (proxy reverso)](#9-configurar-nginx-proxy-reverso)
10. [HTTPS com SSL (Let's Encrypt)](#10-https-com-ssl-lets-encrypt)
11. [Serviço systemd (manter o PDV sempre rodando)](#11-serviço-systemd-manter-o-pdv-sempre-rodando)
12. [Atualizar o app no servidor](#12-atualizar-o-app-no-servidor)
13. [Resumo e troubleshooting](#13-resumo-e-troubleshooting)

---

## 1. Pré-requisitos e informações do servidor

Antes de começar, tenha em mãos:

| O que | Onde encontrar |
|-------|----------------|
| **Usuário SSH** | hPanel → **Avançado** → **SSH** (ex.: `u123456789`) |
| **Senha ou chave SSH** | A mesma que você usa para o n8n |
| **Host do servidor** | `srv1140258.hstgr.cloud` ou o IP mostrado no painel |
| **Acesso root/sudo** | Em VPS, você costuma ter; em hospedagem compartilhada, pode ser limitado |

Anote seu **usuário** (ex.: `u123456789`). Você vai usar em vários comandos como `User=` no systemd e em caminhos `/home/u123456789/...`.

---

## 2. Criar o subdomínio no painel Hostinger

1. Acesse **https://hpanel.hostinger.com** e faça login.
2. No menu lateral, vá em **Domínios** (ou **Websites** → seu domínio).
3. Clique no domínio **srv1140258.hstgr.cloud** (ou no site associado a ele).
4. Procure a opção **Subdomínios** / **Subdomains** ou **DNS** / **Gerenciar domínio**.
5. Adicione um novo subdomínio:
   - **Nome do subdomínio:** `pdv`
   - **Destino / Document Root (se pedir):** pode deixar o padrão (ex.: `public_html/pdv`) ou, se existir, algo como `domains/srv1140258.hstgr.cloud/pdv`. O app em si vai rodar via Nginx apontando para a porta do Streamlit; o Document Root só importa se você for servir arquivos estáticos por aí.
6. Salve. O DNS deve criar o registro para **pdv.srv1140258.hstgr.cloud** apontando para o mesmo IP do servidor. A propagação pode levar alguns minutos.

**Como conferir:** depois de alguns minutos, no seu PC execute `ping pdv.srv1140258.hstgr.cloud` e veja se responde com o IP do servidor.

---

## 3. Conectar ao servidor por SSH

No seu computador (Windows pode usar PowerShell, CMD ou o Terminal do VS Code):

```bash
ssh USUARIO@srv1140258.hstgr.cloud
```

Exemplo: `ssh u123456789@srv1140258.hstgr.cloud`

- Se pedir senha, use a senha do SSH que está no hPanel.
- Se usar chave: `ssh -i caminho/para/sua_chave USUARIO@srv1140258.hstgr.cloud`.

Ao conectar, você deve ver um prompt como `usuario@servidor:~$`. Os próximos passos são todos **dentro do servidor**, nessa sessão SSH.

**Descobrir seu diretório home (útil para systemd):**

```bash
echo $HOME
# Exemplo de saída: /home/u123456789
pwd
# Se você estiver em ~, será o mesmo que $HOME
```

Anote esse caminho (ex.: `/home/u123456789`) para usar no serviço systemd mais à frente.

---

## 4. Verificar/instalar Python no servidor

O PDV precisa de **Python 3.10 ou superior**.

Verificar versão:

```bash
python3 --version
```

Exemplo de saída: `Python 3.10.12` ou `Python 3.11.x`. Se for 3.10+, pode pular a instalação abaixo.

Se não tiver Python 3.10+ ou der erro "comando não encontrado":

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

Verificar se `pip` e `venv` estão disponíveis:

```bash
python3 -m pip --version
python3 -m venv --help
```

Se algum falhar, instale: `sudo apt install -y python3-venv python3-pip`.

---

## 5. Clonar o repositório e instalar dependências

Todos os comandos desta seção são no servidor, após o SSH.

**5.1 – Ir para o diretório onde o projeto ficará**

Recomendado: na sua pasta home.

```bash
cd ~
pwd
# Deve ser algo como /home/u123456789
```

**5.2 – Clonar o repositório**

```bash
git clone https://github.com/wdsc1989/pdv.git
```

Saída esperada: `Cloning into 'pdv'...` e ao final `done`.

**5.3 – Entrar na pasta do projeto**

```bash
cd pdv
pwd
# Ex.: /home/u123456789/pdv
ls -la
# Deve listar app.py, requirements.txt, config/, pages/, etc.
```

**5.4 – Criar o ambiente virtual (venv)**

```bash
python3 -m venv .venv
```

Não deve dar erro. Deve aparecer a pasta `.venv`:

```bash
ls -la .venv
```

**5.5 – Ativar o ambiente virtual**

```bash
source .venv/bin/activate
```

O prompt deve mudar e mostrar algo como `(.venv) usuario@servidor:~/pdv$`. Daqui em diante, `pip` e `python` referem-se ao ambiente isolado.

**5.6 – Atualizar pip e instalar dependências**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

A instalação pode levar 1–2 minutos. Ao terminar, verifique:

```bash
pip list
streamlit --version
```

Se aparecer a versão do Streamlit (ex.: 1.29.x), está correto.

---

## 6. Configurar o banco de dados

O PDV funciona com **SQLite** (arquivo local) ou **PostgreSQL**. Em produção na Hostinger, o ideal é PostgreSQL.

### Opção A – Usar SQLite (mais simples para testar)

Não é preciso criar banco nem usuário. O app criará o arquivo `data/pdv.db` na primeira execução. Você só precisa garantir que a pasta `data` exista (o `init_db.py` cuida disso). Pode pular para a [seção 7](#7-arquivo-env-e-variáveis-de-ambiente) e usar um `.env` vazio ou sem `DATABASE_URL`.

### Opção B – Usar PostgreSQL (recomendado em produção)

**6.1 – Onde está o PostgreSQL**

- **Banco gerenciado pela Hostinger (hPanel):** no painel, em **Bancos de dados** / **Databases**, crie um banco (ex.: `pdv_db`) e um usuário com senha. A Hostinger mostra uma **connection string** ou host, porta, nome do banco, usuário e senha. Use esses dados no `.env`.
- **PostgreSQL instalado no mesmo VPS:** você pode criar o banco manualmente:

```bash
sudo -u postgres psql -c "CREATE USER pdv_user WITH PASSWORD 'sua_senha_segura';"
sudo -u postgres psql -c "CREATE DATABASE pdv_db OWNER pdv_user;"
```

Troque `sua_senha_segura` por uma senha forte.

**6.2 – Formato da URL no .env**

```text
DATABASE_URL=postgresql://USUARIO:SENHA@HOST:PORTA/NOME_DO_BANCO
```

Exemplos:

- Banco no mesmo servidor: `postgresql://pdv_user:senha@localhost:5432/pdv_db`
- Banco remoto (Hostinger): use o host que o painel informar (ex.: `postgresql://u123_pdv:xxx@localhost:5432/u123_pdv` — o painel mostra o formato exato).

Guarde esses dados; você vai usá-los no próximo passo.

---

## 7. Arquivo .env e variáveis de ambiente

O arquivo `.env` fica na **raiz do projeto** (dentro de `~/pdv`). Ele **não** vai para o Git (está no `.gitignore`).

**7.1 – Criar o arquivo**

```bash
cd ~/pdv
nano .env
```

**7.2 – Conteúdo**

- **Se usar PostgreSQL:** coloque uma única linha (ajuste usuário, senha, host e banco):

```env
DATABASE_URL=postgresql://pdv_user:sua_senha@localhost:5432/pdv_db
```

- **Se usar SQLite:** deixe o arquivo vazio ou não defina `DATABASE_URL`. O app usará `data/pdv.db` por padrão.

**7.3 – Salvar no nano**

- `Ctrl+O` (gravar)
- `Enter` (confirmar nome do arquivo)
- `Ctrl+X` (sair)

**7.4 – Conferir**

```bash
cat .env
# Deve mostrar a linha DATABASE_URL (ou nada, se for SQLite)
# Não commite esse arquivo; ele já está no .gitignore
```

---

## 8. Inicializar o banco e testar o app

**8.1 – Garantir que está na pasta do projeto e com o venv ativo**

```bash
cd ~/pdv
source .venv/bin/activate
```

**8.2 – Inicializar o banco (cria tabelas e usuário admin padrão)**

```bash
python init_db.py
```

Saída esperada: mensagem de sucesso (e, com SQLite, criação do arquivo `data/pdv.db`). Se der erro de conexão, revise o `.env` e o PostgreSQL (usuário, senha, host, porta, nome do banco).

**8.3 – Rodar o Streamlit manualmente (teste)**

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

- `--server.port 8501` – porta em que o app responde.
- `--server.address 0.0.0.0` – aceita conexões de fora (necessário para o Nginx acessar).

Você deve ver no terminal algo como “You can now view your Streamlit app in your browser” e “Local URL” / “Network URL”.

**8.4 – Testar no navegador**

Abra no navegador: `http://IP_DO_SERVIDOR:8501` (troque pelo IP real do seu servidor ou use `http://srv1140258.hstgr.cloud:8501` se a porta 8501 estiver aberta no firewall). Deve aparecer a tela de login do PDV.

Para encerrar o teste: no terminal do SSH, `Ctrl+C`.

**8.5 – Rodar em background (opcional, até configurar o systemd)**

```bash
cd ~/pdv
source .venv/bin/activate
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > pdv.log 2>&1 &
```

O `&` coloca o processo em segundo plano. Para parar depois: `pkill -f "streamlit run app.py"` ou use o serviço systemd (seção 11).

---

## 9. Configurar Nginx (proxy reverso)

Assim, o acesso será por **http://pdv.srv1140258.hstgr.cloud** (porta 80), sem precisar abrir a porta 8501 na internet.

**9.1 – Criar o arquivo de site do Nginx**

```bash
sudo nano /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud
```

**9.2 – Colar a configuração abaixo**

Substitua apenas se você tiver usado outra porta que não 8501.

```nginx
server {
    listen 80;
    server_name pdv.srv1140258.hstgr.cloud;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_connect_timeout 86400;
        proxy_send_timeout 86400;
    }
}
```

- `proxy_pass http://127.0.0.1:8501` – encaminha todo o tráfego para o Streamlit.
- As linhas `Upgrade` e `Connection` são importantes para o WebSocket do Streamlit.
- Os timeouts longos evitam corte em uso prolongado.

Salve: `Ctrl+O`, `Enter`, `Ctrl+X`.

**9.3 – Ativar o site**

```bash
sudo ln -sf /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud /etc/nginx/sites-enabled/
```

**9.4 – Testar a configuração do Nginx**

```bash
sudo nginx -t
```

Deve aparecer: `syntax is ok` e `test is successful`.

**9.5 – Recarregar o Nginx**

```bash
sudo systemctl reload nginx
```

**9.6 – Garantir que o Streamlit está rodando**

Se você parou o teste manual, suba de novo (nohup ou, melhor, use o systemd da seção 11). Depois acesse no navegador:

**http://pdv.srv1140258.hstgr.cloud**

Deve carregar a tela de login do PDV. Se aparecer 502 Bad Gateway, o Nginx está ok mas o Streamlit não está rodando ou não está na porta 8501 — confira com `curl -I http://127.0.0.1:8501` ou `ss -tlnp | grep 8501`.

---

## 10. HTTPS com SSL (Let's Encrypt)

Para usar **https://pdv.srv1140258.hstgr.cloud**.

**10.1 – Certificado pelo painel Hostinger**

- No hPanel, em **SSL** ou **Segurança**, veja se há opção para ativar SSL no domínio/subdomínio **pdv.srv1140258.hstgr.cloud**. Se a Hostinger gerar o certificado, ela pode redirecionar HTTP → HTTPS automaticamente; nesse caso, pode ser necessário apenas ajustar o Nginx para aceitar HTTPS (às vezes a Hostinger já coloca um proxy na frente).

**10.2 – Certificado com Certbot (se você gerencia o Nginx no servidor)**

Instalar Certbot (exemplo para Ubuntu/Debian com Nginx):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pdv.srv1140258.hstgr.cloud
```

Siga as perguntas (e-mail, aceitar termos). O Certbot altera o arquivo do Nginx para escutar na porta 443 e usar o certificado. Depois teste:

**https://pdv.srv1140258.hstgr.cloud**

Renovação automática (já costuma estar agendada):

```bash
sudo certbot renew --dry-run
```

---

## 11. Serviço systemd (manter o PDV sempre rodando)

Assim, o PDV sobe após reinício do servidor e reinicia sozinho se cair.

**11.1 – Descobrir usuário e caminho**

No SSH:

```bash
whoami
# Ex.: u123456789
echo $HOME
# Ex.: /home/u123456789
```

O caminho do projeto será `$HOME/pdv`, ex.: `/home/u123456789/pdv`.

**11.2 – Criar o arquivo do serviço**

```bash
sudo nano /etc/systemd/system/pdv-streamlit.service
```

**11.3 – Colar o conteúdo abaixo**

Troque **u123456789** pelo seu usuário e **/home/u123456789** pelo seu `$HOME` se for diferente.

```ini
[Unit]
Description=PDV Streamlit App
After=network.target

[Service]
User=u123456789
Group=u123456789
WorkingDirectory=/home/u123456789/pdv
Environment="PATH=/home/u123456789/pdv/.venv/bin"
ExecStart=/home/u123456789/pdv/.venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Salve e saia.

**11.4 – Recarregar o systemd, ativar e iniciar**

```bash
sudo systemctl daemon-reload
sudo systemctl enable pdv-streamlit
sudo systemctl start pdv-streamlit
sudo systemctl status pdv-streamlit
```

O status deve mostrar `active (running)`. Se mostrar `failed`, veja os logs:

```bash
sudo journalctl -u pdv-streamlit -n 50 --no-pager
```

Ajuste caminhos ou usuário no `.service` se necessário.

**11.5 – Comandos úteis**

| Ação | Comando |
|------|--------|
| Ver status | `sudo systemctl status pdv-streamlit` |
| Parar | `sudo systemctl stop pdv-streamlit` |
| Iniciar | `sudo systemctl start pdv-streamlit` |
| Reiniciar (ex.: após atualizar código) | `sudo systemctl restart pdv-streamlit` |
| Logs em tempo real | `sudo journalctl -u pdv-streamlit -f` |

---

## 12. Atualizar o app no servidor

Quando houver alterações no repositório GitHub:

```bash
cd ~/pdv
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart pdv-streamlit
```

Confira com `sudo systemctl status pdv-streamlit` e acesse **pdv.srv1140258.hstgr.cloud** para validar.

---

## 13. Resumo e troubleshooting

### Resumo

| Item | Valor |
|------|--------|
| **URL** | https://pdv.srv1140258.hstgr.cloud (ou http até ativar SSL) |
| **Repositório** | https://github.com/wdsc1989/pdv |
| **Porta interna** | 8501 (Streamlit) |
| **Banco** | PostgreSQL (recomendado) ou SQLite via `DATABASE_URL` no `.env` |
| **Serviço** | `pdv-streamlit` (systemd) |

### Primeiro acesso

O `init_db.py` (e o app na inicialização) garante um usuário **admin** padrão:

- **Usuário:** `admin`
- **Senha:** `admin123`

**Importante:** altere a senha logo após o primeiro login em **Administração** → usuários. Em produção, não mantenha `admin123`.

### Erros comuns

| Problema | O que verificar |
|----------|------------------|
| **502 Bad Gateway** | Streamlit não está rodando. `sudo systemctl start pdv-streamlit` e `sudo systemctl status pdv-streamlit`. Confirme a porta: `ss -tlnp \| grep 8501`. |
| **Porta 8501 em uso** | Outro processo está usando. `sudo lsof -i :8501` ou `sudo ss -tlnp \| grep 8501`. Mate o processo ou mude a porta no `streamlit run` e no Nginx. |
| **Permission denied (pip/venv)** | Use o venv: `source .venv/bin/activate` antes de `pip`/`python`. Em systemd, confira `User=` e `WorkingDirectory=`. |
| **streamlit: comando não encontrado** | O systemd usa o caminho completo: `/home/.../pdv/.venv/bin/streamlit`. Confira se esse arquivo existe com `ls -la ~/pdv/.venv/bin/streamlit`. |
| **Erro de conexão com o banco** | Revise `.env`: `DATABASE_URL` correto, usuário/senha, host (localhost ou o que a Hostinger informar). Teste com `python init_db.py`. |
| **Subdomínio não resolve** | DNS pode levar alguns minutos. `ping pdv.srv1140258.hstgr.cloud`. No hPanel, confira se o subdomínio **pdv** está criado. |

### Logs

- **Systemd:** `sudo journalctl -u pdv-streamlit -n 100`
- **Nginx:** `sudo tail -f /var/log/nginx/error.log` e `access.log`
- **App (se rodou com nohup):** `tail -f ~/pdv/pdv.log`

Com isso, você tem o passo a passo completo desde o painel até o PDV no ar em **pdv.srv1140258.hstgr.cloud** com atualizações e troubleshooting.
