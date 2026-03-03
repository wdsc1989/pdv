#Requires -Version 5.1
<#
.SYNOPSIS
  Evita conflito com outra app Streamlit: coloca o PDV na porta 8502 e ajusta o Nginx.
  A outra aplicacao (ex. Contabil) continua na 8501; PDV usa 8502.
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

$PDV_PORT = "8502"

# 1) Alterar systemd: --server.port 8501 -> 8502
# 2) daemon-reload, restart pdv-streamlit
# 3) Nginx: pdv.srv1140258.hstgr.cloud -> 127.0.0.1:8502
# 4) reload nginx
$remoteCmd = @"
set -e
echo '=== PDV na porta $PDV_PORT (outra app Streamlit fica na 8501) ==='
echo ''
echo '1. Parar e liberar portas...'
sudo systemctl stop pdv-streamlit 2>/dev/null || true
sudo fuser -k 8501/tcp 2>/dev/null || true
sudo fuser -k $PDV_PORT/tcp 2>/dev/null || true
sleep 2

echo '2. Ajustar systemd: pdv-streamlit na porta $PDV_PORT'
sudo sed -i.bak 's/--server\.port 8501/--server.port $PDV_PORT/g' /etc/systemd/system/pdv-streamlit.service
grep -n ExecStart /etc/systemd/system/pdv-streamlit.service || true
sudo systemctl daemon-reload
sudo systemctl start pdv-streamlit
sleep 2
sudo systemctl status pdv-streamlit --no-pager || true

echo ''
echo '3. Nginx: config PDV -> 127.0.0.1:8502'
sudo tee /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud > /dev/null << 'NGXEOF'
server {
    listen 80;
    server_name pdv.srv1140258.hstgr.cloud;

    location / {
        proxy_pass http://127.0.0.1:8502;
        proxy_http_version 1.1;
        proxy_set_header Upgrade `$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_read_timeout 86400;
        proxy_connect_timeout 86400;
        proxy_send_timeout 86400;
    }
}
NGXEOF
sudo ln -sf /etc/nginx/sites-available/pdv.srv1140258.hstgr.cloud /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

echo ''
echo '4. Portas em uso:'
ss -tlnp | grep -E '8501|8502' || true
echo ''
echo '=== Concluido. Teste: http://pdv.srv1140258.hstgr.cloud ==='
"@

# No heredoc remoto os $ do nginx precisam ser literais; no PowerShell escapamos com `
$remoteCmd = $remoteCmd -replace "`r`n", "`n" -replace "`r", ""

# Corrigir: no bloco NGXEOF que vai pro servidor, $http_upgrade etc devem ser $ no bash (nao `$)
# No PowerShell estamos em double-quote para interpolar $PDV_PORT. Entao o NGXEOF contem \$ para o nginx
# Na verdade o here-string usa @" "@ - entao $PDV_PORT e interpolado. E dentro do NGXEOF temos `$http_upgrade
# que no PowerShell vira $http_upgrade literal. Quando mandamos pro bash, o heredoc 'NGXEOF' faz o bash
# escrever literalmente no arquivo. Entao o arquivo nginx deve ter $http_upgrade. Mas no PowerShell
# `$ produz $. Entao estamos enviando $http_upgrade no conteudo. Perfeito.
# Wait - in the remote script we have << 'NGXEOF' so the remote bash sends everything until NGXEOF to tee.
# What we have in $remoteCmd is:  proxy_set_header Upgrade `$http_upgrade;  - so we're sending
# proxy_set_header Upgrade $http_upgrade;  (backtick is PowerShell escape, so $ is literal)
# Good. But then we have  proxy_pass http://127.0.0.1:8502  - that's hardcoded 8502. Good.

Write-Host "`n=== PDV na porta 8502 (evitar conflito com outra app na 8501) ===" -ForegroundColor Cyan
Write-Host "Host: $VpsHost | Usuario: $SshUser"
Write-Host "Digite a senha SSH quando pedir.`n" -ForegroundColor Yellow

$remoteCmd | & ssh @sshArgs "bash -s"
if ($LASTEXITCODE -ne 0) { throw "Falha no SSH." }

Write-Host "`nConcluido. Abra: http://pdv.srv1140258.hstgr.cloud" -ForegroundColor Green
