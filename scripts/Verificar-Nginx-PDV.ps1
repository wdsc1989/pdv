#Requires -Version 5.1
<#
.SYNOPSIS
  Conecta na VPS e verifica Nginx + serviço PDV (por que pdv.srv... abre o contábil).
  Pede senha SSH uma vez e mostra a saída.
#>
param(
    [string] $VpsHost = "srv1140258.hstgr.cloud",
    [string] $SshUser = "root"
)

$remote = "${SshUser}@${VpsHost}"
$cmd = @'
echo "=== 1. Arquivos em sites-enabled ==="
ls -la /etc/nginx/sites-enabled/

echo ""
echo "=== 2. listen / default_server / server_name em cada site ==="
for f in /etc/nginx/sites-enabled/*; do
  echo "--- $f ---"
  grep -Eh "listen|default_server|server_name" "$f" 2>/dev/null || true
done

echo ""
echo "=== 3. Conteúdo do site PDV (sites-available) ==="
if [ -f /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud ]; then
  cat /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud
else
  echo "(arquivo pdv.srv1140258.hstgr.cloud nao encontrado)"
fi

echo ""
echo "=== 4. Symlink do PDV em sites-enabled? ==="
ls -la /etc/nginx/sites-enabled/ | grep pdv || echo "(nenhum link do pdv)"

echo ""
echo "=== 5. Serviço pdv-streamlit ==="
systemctl is-active pdv-streamlit 2>/dev/null || echo "inativo ou nao encontrado"
systemctl status pdv-streamlit --no-pager 2>/dev/null | head -5

echo ""
echo "=== 6. Portas 8501 (Contabil) e 8502 (PDV) ==="
ss -tlnp | grep -E "8501|8502" || echo "nenhuma das portas em uso"
'@

Write-Host "Conectando em $remote (digite a senha SSH quando pedir)..." -ForegroundColor Cyan
ssh -o StrictHostKeyChecking=accept-new $remote $cmd
