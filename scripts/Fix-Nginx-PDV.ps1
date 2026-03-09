#Requires -Version 5.1
<#
.SYNOPSIS
  Corrige 502: aplica config Nginx para pdv.srv1140258.hstgr.cloud -> 127.0.0.1:8502 (PDV). Contábil usa 8501.
  Execute e digite a senha SSH quando solicitado.
#>
param(
    [string] $VpsHost = "srv1140258.hstgr.cloud",
    [string] $SshUser = "root",
    [string] $SshKeyPath
)

$ErrorActionPreference = "Stop"
$remote = "${SshUser}@${VpsHost}"
$sshOpt = "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"
$sshArgs = @($sshOpt + $remote)
if ($SshKeyPath -and (Test-Path $SshKeyPath)) { $sshArgs = @("-i", $SshKeyPath) + $sshOpt + $remote }

# Script remoto: diagnostico + aplicar config PDV (proxy 8502) + reload nginx
# Usar here-string com '@' para nao expandir $http_upgrade etc no PowerShell
$remoteCmd = @'
set -e
echo "=== Diagnostico: PDV na porta 8502 ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8502 || true
echo ""
echo "=== Nginx sites-enabled (server_name / proxy_pass) ==="
grep -rh "server_name\|proxy_pass" /etc/nginx/sites-enabled/ 2>/dev/null || true
echo ""
echo "=== Aplicando config PDV (proxy 127.0.0.1:8502) ==="
sudo tee /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud > /dev/null << 'NGXEOF'
server {
    listen 80;
    server_name pdv.srv1140258.hstgr.cloud;

    location / {
        proxy_pass http://127.0.0.1:8502;
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
NGXEOF
sudo ln -sf /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
echo ""
echo "Nginx recarregado. Teste: http://pdv.srv1140258.hstgr.cloud"
'@
$remoteCmd = $remoteCmd -replace "`r`n", "`n" -replace "`r", ""

Write-Host "`n=== Corrigir Nginx - PDV (502 Bad Gateway) ===" -ForegroundColor Cyan
Write-Host "Host: $VpsHost | Usuario: $SshUser"
Write-Host "Digite a senha SSH quando pedir.`n" -ForegroundColor Yellow

$remoteCmd | & ssh @sshArgs "bash -s"
if ($LASTEXITCODE -ne 0) { throw "Falha no SSH ou Nginx." }

Write-Host "`nConcluido. Abra: http://pdv.srv1140258.hstgr.cloud" -ForegroundColor Green
