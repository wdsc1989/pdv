#!/bin/bash
# Executar na VPS (via SSH a partir do PowerShell).
# Variáveis: APP_DIR, DB_NAME, DB_USER, DB_PASS (via arquivo /tmp/pdv-deploy.env enviado pelo PowerShell)
set -e

# Carregar variáveis enviadas pelo deploy (PowerShell faz SCP do arquivo antes)
if [ -f /tmp/pdv-deploy.env ]; then
  set -a
  source /tmp/pdv-deploy.env
  rm -f /tmp/pdv-deploy.env
  set +a
fi

APP_DIR="${APP_DIR:-apps/pdv}"
DB_NAME="${DB_NAME:-pdv_db}"
DB_USER="${DB_USER:-pdv_user}"
DB_PASS="${DB_PASS:?Defina DB_PASS no arquivo de deploy}"

# Remover \r se o .env foi enviado com CRLF (Windows)
APP_DIR="${APP_DIR//$'\r'/}"
DB_NAME="${DB_NAME//$'\r'/}"
DB_USER="${DB_USER//$'\r'/}"
DB_PASS="${DB_PASS//$'\r'/}"

REPO_URL="https://github.com/wdsc1989/pdv.git"
# Contábil usa 8501; PDV usa 8502 para não conflitar na mesma VPS.
STREAMLIT_PORT=8502
SERVER_NAME="pdv.srv1140258.hstgr.cloud"

# Usuário e home (quem está rodando o script via SSH)
LINUX_USER="$(whoami)"
HOME_DIR="${HOME:-/home/$LINUX_USER}"
INSTALL_DIR="$HOME_DIR/$APP_DIR"

echo "=== Deploy PDV ==="
echo "Diretório da aplicação: $INSTALL_DIR"
echo "Banco: $DB_NAME | Usuário DB: $DB_USER"
echo ""

# Exigir PostgreSQL instalado na VPS (criação do novo database)
if ! sudo -u postgres psql -c "SELECT 1" &>/dev/null; then
  echo "Erro: PostgreSQL não encontrado ou inacessível na VPS. Instale com: sudo apt install postgresql postgresql-contrib"
  exit 1
fi

# 1) Estrutura de diretórios (como no contábil: um dir por app)
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 2) PostgreSQL: criar usuário e banco (novo database na VPS)
echo "--- Criando banco PostgreSQL ---"
# Escapar aspas simples na senha para o comando psql
DB_PASS_SAFE="${DB_PASS//\'/\'\'}"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
  echo "Usuário PostgreSQL '$DB_USER' já existe."
else
  sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS_SAFE';"
  echo "Usuário PostgreSQL '$DB_USER' criado."
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
  echo "Banco '$DB_NAME' já existe."
else
  sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
  echo "Banco '$DB_NAME' criado."
fi

# 3) Código: clone ou pull
echo "--- Código do repositório ---"
if [ -d .git ]; then
  git fetch origin
  git reset --hard origin/main
  git pull origin main
else
  git clone "$REPO_URL" .
fi

# 4) Ambiente virtual e dependências
echo "--- Ambiente Python ---"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
set +e
source .venv/bin/activate
set -e
python3 -m pip install --upgrade pip -q
python3 -m pip install -r requirements.txt -q

# 5) Arquivo .env (DATABASE_URL com o banco criado aqui na VPS)
# Codificar usuário e senha para URL (ex.: senha com @ quebra a URL)
url_encode() {
  local s="$1"
  s="${s//%/%25}"
  s="${s//@/%40}"
  s="${s//:/%3A}"
  s="${s//\//%2F}"
  echo "$s"
}
DB_USER_ENC=$(url_encode "$DB_USER")
DB_PASS_ENC=$(url_encode "$DB_PASS")
DATABASE_URL="postgresql://${DB_USER_ENC}:${DB_PASS_ENC}@localhost:5432/${DB_NAME}"
echo "DATABASE_URL=$DATABASE_URL" > .env

# 6) Inicializar banco (tabelas + admin padrão)
echo "--- Inicializando banco ---"
python init_db.py

# 7) Nginx: arquivo de site
echo "--- Configurando Nginx ---"
sudo tee /etc/nginx/sites-available/$SERVER_NAME > /dev/null << 'NGINX_EOF'
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
NGINX_EOF

sudo ln -sf /etc/nginx/sites-available/$SERVER_NAME /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 8) Systemd: serviço para o Streamlit
echo "--- Configurando systemd ---"
sudo tee /etc/systemd/system/pdv-streamlit.service > /dev/null << SYSTEMD_EOF
[Unit]
Description=PDV Streamlit App
After=network.target

[Service]
User=$LINUX_USER
Group=$LINUX_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/.venv/bin"
ExecStart=$INSTALL_DIR/.venv/bin/streamlit run app.py --server.port $STREAMLIT_PORT --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

sudo systemctl daemon-reload
sudo systemctl enable pdv-streamlit
sudo systemctl stop pdv-streamlit 2>/dev/null || true
sudo fuser -k 8502/tcp 2>/dev/null || true
sleep 2
sudo systemctl start pdv-streamlit

echo ""
echo "=== Deploy concluído ==="
echo "URL: http://$SERVER_NAME"
echo "Login padrão: admin / admin123 (altere em produção)"
echo "Diretório: $INSTALL_DIR"
echo "Serviço: sudo systemctl status pdv-streamlit"
