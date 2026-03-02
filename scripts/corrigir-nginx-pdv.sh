#!/bin/bash
# Corrige: pdv.srv1140258.hstgr.cloud abrindo o contábil.
# O Contábil já usa a porta 8501; o PDV deve usar 8502 para não conflitar.
# 1) Config do PDV com proxy para 8502
# 2) Ajusta o serviço pdv-streamlit para escutar na 8502
set -e

PDV_PORT=8502
PDV_NAME="00-pdv.srv1140258.hstgr.cloud"
PDV_AVAILABLE="/etc/nginx/sites-available/$PDV_NAME"
PDV_ENABLED="/etc/nginx/sites-enabled/$PDV_NAME"

echo "=== Corrigir Nginx: PDV em pdv.srv1140258.hstgr.cloud (porta $PDV_PORT) ==="
echo "   (Contabil usa 8501; PDV usa $PDV_PORT para nao conflitar)"
echo ""

echo "0. server_name em todos os sites (para diagnostico)..."
grep -r "server_name" /etc/nginx/sites-enabled/ 2>/dev/null || true
echo ""

echo "1. Escrevendo config do PDV (proxy para porta $PDV_PORT)..."
sudo tee "$PDV_AVAILABLE" > /dev/null << NGINX_EOF
# PDV - Streamlit na porta $PDV_PORT (Contábil usa 8501)
server {
    listen 80;
    server_name pdv.srv1140258.hstgr.cloud;
    add_header X-Served-By PDV always;

    location / {
        proxy_pass http://127.0.0.1:$PDV_PORT;
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
echo "   Proxy: http://127.0.0.1:$PDV_PORT"

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
echo "6. Ajustando pdv-streamlit para porta $PDV_PORT (para nao conflitar com Contabil em 8501)..."
if [ -f /etc/systemd/system/pdv-streamlit.service ]; then
  sudo sed -i.bak "s/--server.port 8501/--server.port $PDV_PORT/g" /etc/systemd/system/pdv-streamlit.service
  sudo systemctl daemon-reload
  sudo systemctl restart pdv-streamlit
  echo "   Servico atualizado e reiniciado."
else
  echo "   AVISO: /etc/systemd/system/pdv-streamlit.service nao encontrado."
  echo "   Se o PDV rodar manualmente, use: streamlit run app.py --server.port $PDV_PORT ..."
fi

echo ""
echo "7. Conferindo: porta $PDV_PORT (PDV)..."
ss -tlnp | grep "$PDV_PORT" || echo "   AGUARDE alguns segundos e rode: ss -tlnp | grep $PDV_PORT"
systemctl is-active pdv-streamlit 2>/dev/null || true

echo ""
echo "=== Concluido. Teste: http://pdv.srv1140258.hstgr.cloud ==="
echo "PDV deve abrir na porta $PDV_PORT; Contabil continua em 8501 (srv1140258.hstgr.cloud)."
