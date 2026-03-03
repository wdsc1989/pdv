#Requires -Version 5.1
<#
.SYNOPSIS
  Corrige 502 Bad Gateway: para o Streamlit, libera a porta 8501 e inicia de novo na VPS.
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

$cmd = "sudo systemctl stop pdv-streamlit 2>/dev/null; sleep 2; sudo fuser -k 8501/tcp 2>/dev/null; sleep 1; sudo systemctl start pdv-streamlit; sleep 2; echo '=== Status ==='; sudo systemctl status pdv-streamlit --no-pager; echo ''; echo '=== Ultimos logs ==='; sudo journalctl -u pdv-streamlit -n 20 --no-pager"

Write-Host "`n=== Corrigir 502 - PDV na VPS ===" -ForegroundColor Cyan
Write-Host "Host: $VpsHost | Usuario: $SshUser"
Write-Host "Digite a senha SSH quando pedir.`n" -ForegroundColor Yellow

& ssh @sshArgs $cmd
if ($LASTEXITCODE -ne 0) { throw "Falha no SSH." }

Write-Host "`nConcluido. Teste: http://pdv.srv1140258.hstgr.cloud" -ForegroundColor Green
