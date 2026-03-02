#!/bin/bash
# Corrige: pdv.srv1140258.hstgr.cloud abrindo o contábil.
# 1) Cria/sobrescreve o config do PDV (porta 8501)
# 2) Usa nome 00-pdv... para carregar antes dos outros
# 3) Tira default_server de outros e trata server_name que pega subdomínios
set -e

PDV_NAME="00-pdv.srv1140258.hstgr.cloud"
PDV_AVAILABLE="/etc/nginx/sites-available/$PDV_NAME"
PDV_ENABLED="/etc/nginx/sites-enabled/$PDV_NAME"

echo "=== Corrigir Nginx: PDV em pdv.srv1140258.hstgr.cloud ==="
echo ""

echo "0. server_name em todos os sites (para diagnostico)..."
grep -r "server_name" /etc/nginx/sites-enabled/ 2>/dev/null || true
echo ""

echo "1. Escrevendo config do PDV (proxy para porta 8501)..."
sudo tee "$PDV_AVAILABLE" > /dev/null << 'NGINX_EOF'
# PDV - Streamlit na porta 8501
server {
    listen 80;
    server_name pdv.srv1140258.hstgr.cloud;
    add_header X-Served-By PDV always;

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
echo "   Arquivo: $PDV_AVAILABLE"

echo ""
echo "2. Habilitando o site do PDV (e removendo link antigo se existir)..."
sudo rm -f /etc/nginx/sites-enabled/pdv.srv1140258.hstgr.cloud
sudo ln -sf "$PDV_AVAILABLE" "$PDV_ENABLED"
echo "   Symlink: $PDV_ENABLED -> $PDV_AVAILABLE"

echo ""
echo "3. Removendo default_server de outros sites na porta 80..."
for f in /etc/nginx/sites-enabled/*; do
  [ -f "$f" ] || continue
  echo "$f" | grep -q "pdv" && continue
  if grep -q "listen.*80.*default_server" "$f" 2>/dev/null; then
    echo "   Ajustando $f (backup .bak)"
    sudo sed -i.bak 's/listen 80 default_server;/listen 80;/' "$f"
  fi
done

echo ""
echo "4. Verificando server_name nos outros sites (wildcard pode engolir pdv)..."
for f in /etc/nginx/sites-enabled/*; do
  [ -f "$f" ] || continue
  echo "$f" | grep -q "pdv" && continue
  if grep -E "server_name.*\.srv1140258|server_name \*" "$f" 2>/dev/null; then
    echo "   ATENÇÃO: $f tem server_name que pode pegar todos os subdominios."
    echo "   Se o contabil usar .srv1140258.hstgr.cloud, altere para apenas:"
    echo "   server_name contabil.srv1140258.hstgr.cloud srv1140258.hstgr.cloud;"
  fi
done

echo ""
echo "5. Teste e reload do Nginx..."
sudo nginx -t && sudo systemctl reload nginx
echo "   Nginx recarregado."

echo ""
echo "6. Conferindo: porta 8501 (PDV) e servico..."
ss -tlnp | grep 8501 || echo "   AVISO: porta 8501 nao esta em uso (pdv-streamlit rodando?)"
systemctl is-active pdv-streamlit 2>/dev/null || true

echo ""
echo "=== Concluido. Teste: http://pdv.srv1140258.hstgr.cloud ==="
echo "Se ainda abrir o contabil, no servidor rode:"
echo "  grep -r server_name /etc/nginx/sites-enabled/"
echo "e confira se algum site usa .srv1140258.hstgr.cloud ou * (e troque para nomes especificos)."
