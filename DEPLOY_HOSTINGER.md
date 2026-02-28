# Deploy do PDV na Hostinger (pdv.srv1140258.hstgr.cloud)

Repositório: **https://github.com/wdsc1989/pdv**

Este guia descreve como colocar o PDV em produção na Hostinger, no subdomínio **pdv.srv1140258.hstgr.cloud** (no mesmo servidor em que você já tem, por exemplo, **n8n.srv1140258.hstgr.cloud**).

---

## Roteiro rápido (comandos em sequência no servidor)

Conectado por SSH no servidor, execute na ordem (ajuste `USUARIO` pelo seu usuário Linux na Hostinger, ex.: `u123456789`):

```bash
# 1) Clonar o repositório
cd ~
git clone https://github.com/wdsc1989/pdv.git
cd pdv

# 2) Ambiente virtual e dependências
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3) Criar .env (edite com seus dados de banco)
cat > .env << 'EOF'
DATABASE_URL=postgresql://USUARIO:SENHA@localhost:5432/pdv_db
EOF
# Ou deixe vazio para usar SQLite: touch .env

# 4) Inicializar banco e criar admin
python init_db.py

# 5) Testar (Ctrl+C para parar)
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Depois configure o **Nginx** (seção 8) e, se quiser, o **systemd** (seção 9) para manter o app rodando.

---

## 1. Subdomínio no painel Hostinger

1. Acesse o **hPanel** da Hostinger.
2. Vá em **Domínios** (ou **Domains**) e abra o domínio **srv1140258.hstgr.cloud**.
3. Adicione um **subdomínio**: **pdv**
   - Resultado: **pdv.srv1140258.hstgr.cloud** apontando para o mesmo servidor (ou para a pasta do PDV, conforme a opção que o painel oferecer).
4. Se houver opção de **Document Root**, você pode definir algo como `/home/u123456789/domains/srv1140258.hstgr.cloud/pdv` (o caminho exato depende da sua conta).

---

## 2. Acesso SSH ao servidor

Use o usuário e o servidor que você já usa para o n8n (ex.: `u123456789@srv1140258.hstgr.cloud` ou o IP do VPS).

```bash
ssh u123456789@srv1140258.hstgr.cloud
```

---

## 3. Instalar dependências do sistema (se ainda não tiver)

No servidor (Linux):

```bash
# Python 3.10+ e venv
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# Se for usar PostgreSQL no mesmo servidor (opcional)
# sudo apt install -y postgresql postgresql-contrib
```

---

## 4. Colocar o código do PDV no servidor

**Opção A – Git (recomendado)**  
Se você enviar o repositório para GitHub/GitLab:

```bash
cd ~
# ou cd para a pasta onde ficam seus projetos, ex.: ~/domains/srv1140258.hstgr.cloud
git clone https://github.com/wdsc1989/pdv.git
cd pdv
```

**Opção B – Upload manual (SFTP)**  
Envie a pasta do projeto (exceto `.venv`, `data`, `.env`) para o servidor, por exemplo em:

`/home/u123456789/domains/srv1140258.hstgr.cloud/pdv`

---

## 5. Ambiente virtual e dependências Python

No servidor, na pasta do projeto PDV:

```bash
cd ~/pdv   # ou o caminho onde está o código

python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS

pip install --upgrade pip
pip install -r requirements.txt
```

---

## 6. Variáveis de ambiente (produção)

Crie o arquivo `.env` na **raiz do projeto PDV** (não versionado):

```bash
nano .env
```

Conteúdo mínimo para produção (ajuste com seus dados reais):

```env
# Banco de dados (PostgreSQL na Hostinger – use o que o painel fornecer)
DATABASE_URL=postgresql://usuario:senha@localhost:5432/pdv_db

# Opcional: se quiser forçar host/porta do Streamlit
# STREAMLIT_SERVER_HEADLESS=true
```

- **PostgreSQL**: crie o banco `pdv_db` e o usuário no painel Hostinger (Bancos de dados) ou via SSH se o PostgreSQL estiver no mesmo VPS.
- Se **não** definir `DATABASE_URL`, o app usa SQLite em `data/pdv.db` (funciona, mas em produção é melhor PostgreSQL).

Salve e feche (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## 7. Inicializar o banco e rodar o app

```bash
source .venv/bin/activate
python init_db.py
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

- `--server.address 0.0.0.0` permite acesso externo (Nginx na frente).
- Teste em: `http://SEU_IP:8501`. Depois configure o Nginx para usar apenas `pdv.srv1140258.hstgr.cloud`.

Para rodar em background (exemplo com `nohup`):

```bash
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > pdv.log 2>&1 &
```

Ou use **systemd** ou **supervisor** para manter o processo sempre ativo (veja seção 9).

---

## 8. Nginx como proxy reverso (recomendado)

Assumindo que o Nginx já atende **n8n.srv1140258.hstgr.cloud** em outro bloco, adicione um **novo server** para o PDV:

```bash
sudo nano /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud
```

Conteúdo sugerido (substitua `8501` se usar outra porta):

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
    }
}
```

Ativar e recarregar:

```bash
sudo ln -s /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Se a Hostinger gerar **HTTPS** para o subdomínio (Let’s Encrypt), pode haver um bloco `listen 443 ssl;` ou inclusão de certificado em outro arquivo; nesse caso, adapte o exemplo acima para usar o mesmo padrão dos outros sites no servidor.

---

## 9. Manter o PDV rodando (systemd)

Crie um serviço para o Streamlit:

```bash
sudo nano /etc/systemd/system/pdv-streamlit.service
```

Conteúdo (ajuste `User`, `WorkingDirectory` e caminho do `python`/`streamlit`):

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

Ativar e iniciar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pdv-streamlit
sudo systemctl start pdv-streamlit
sudo systemctl status pdv-streamlit
```

---

## 10. Resumo rápido

| Item | Valor |
|------|--------|
| **URL produção** | https://pdv.srv1140258.hstgr.cloud (ou http até ativar SSL) |
| **Subdomínio** | pdv.srv1140258.hstgr.cloud |
| **Porta interna** | 8501 (Streamlit) |
| **Banco** | PostgreSQL (recomendado) via `DATABASE_URL` no `.env` |
| **Outros sistemas no mesmo servidor** | Ex.: n8n.srv1140258.hstgr.cloud |

Depois do deploy, acesse **pdv.srv1140258.hstgr.cloud**, faça login com o usuário admin (criado pelo `init_db.py` ou pelo fluxo padrão do app) e configure usuários, produtos e caixa conforme necessário.
