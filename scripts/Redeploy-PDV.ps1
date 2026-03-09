#Requires -Version 5.1
<#
.SYNOPSIS
  Atualiza o PDV na VPS (git pull + restart do Streamlit). Use após push para produção.

.DESCRIPTION
  Conecta na VPS via SSH, atualiza o código (git pull), libera a porta 8501 se necessário
  e reinicia o serviço pdv-streamlit. Não pede senha do banco (usa o que já está na VPS).

.PARAMETER VpsHost
  Host da VPS (ex.: srv1140258.hstgr.cloud).

.PARAMETER SshUser
  Usuário SSH (ex.: root).

.PARAMETER AppDir
  Diretório da app na VPS, relativo ao home (ex.: apps/pdv). Deve bater com o usado no deploy.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string] $VpsHost = "srv1140258.hstgr.cloud",

    [Parameter(Mandatory = $false)]
    [string] $SshUser = "root",

    [Parameter(Mandatory = $false)]
    [string] $AppDir = "apps/pdv",

    [Parameter(Mandatory = $false)]
    [string] $SshKeyPath
)

$ErrorActionPreference = "Stop"

$remote = "${SshUser}@${VpsHost}"
$sshOpt = "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"
$sshArgs = @($sshOpt + $remote)
if ($SshKeyPath -and (Test-Path $SshKeyPath)) {
    $sshArgs = @("-i", $SshKeyPath) + $sshOpt + $remote
}

# AppDir no servidor: ~/apps/pdv => /root/apps/pdv (para root)
# Usar apenas LF (sem CR) para o bash na VPS não falhar com "invalid option"
$remoteCmd = @"
set -e
INSTALL_DIR=`$HOME/$AppDir
echo '=== Redeploy PDV ==='
echo Diretorio: `$INSTALL_DIR
cd `$INSTALL_DIR || { echo 'Erro: diretorio nao existe'; exit 1; }
echo '--- Git pull ---'
git fetch origin
git reset --hard origin/main
git pull origin main
echo '--- Parar servico e liberar porta 8502 (PDV) ---'
sudo systemctl stop pdv-streamlit 2>/dev/null || true
sleep 2
sudo fuser -k 8502/tcp 2>/dev/null || true
sleep 1
echo '--- Iniciar servico ---'
sudo systemctl start pdv-streamlit
sleep 2
sudo systemctl status pdv-streamlit --no-pager
echo ''
echo '=== Fim. URL: http://pdv.srv1140258.hstgr.cloud ==='
"@
$remoteCmd = $remoteCmd -replace "`r`n", "`n" -replace "`r", ""

Write-Host "`n=== Redeploy PDV na VPS ===" -ForegroundColor Cyan
Write-Host "Host: $VpsHost | Usuário: $SshUser | App: $AppDir"
Write-Host ""

ssh-keygen -R $VpsHost 2>$null
$remoteCmd | & ssh @sshArgs "bash -s"
if ($LASTEXITCODE -ne 0) { throw "Falha no redeploy (SSH)." }

Write-Host "`nRedeploy concluído." -ForegroundColor Green
Write-Host "URL: http://pdv.srv1140258.hstgr.cloud"
