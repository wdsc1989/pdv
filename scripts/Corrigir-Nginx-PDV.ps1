#Requires -Version 5.1
<#
.SYNOPSIS
  Executa corrigir-nginx-pdv.sh na VPS (uma unica conexao SSH, uma senha).
  Corrige pdv.srv1140258.hstgr.cloud para abrir o PDV em vez do contabil.
.PARAMETER VpsHost
  Host ou IP da VPS.
.PARAMETER SshPort
  Porta SSH (padrao 22). Alguns provedores usam ex.: 2222.
.PARAMETER ApenasGerarScript
  Se True, nao conecta na VPS; apenas gera um arquivo .sh para voce copiar e rodar no servidor
  (uteis quando SSH da sua rede da timeout - use o Terminal web da Hostinger ou outra maquina).
#>
param(
    [string] $VpsHost = "72.61.56.204",
    [string] $SshUser = "root",
    [int] $SshPort = 22,
    [switch] $ApenasGerarScript
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bashScript = Join-Path $scriptDir "corrigir-nginx-pdv.sh"
if (-not (Test-Path $bashScript)) { Write-Error "Nao encontrado: $bashScript"; exit 1 }

$remote = "${SshUser}@${VpsHost}"
$sshOpt = @("-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15")
if ($SshPort -ne 22) { $sshOpt += @("-p", $SshPort) }

# Converter CRLF -> LF
$content = [System.IO.File]::ReadAllText($bashScript) -replace "`r`n", "`n" -replace "`r", "`n"

if ($ApenasGerarScript) {
    $outPath = Join-Path $scriptDir "corrigir-nginx-pdv-para-colar-no-servidor.sh"
    [System.IO.File]::WriteAllText($outPath, $content, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "Arquivo gerado: $outPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "Quando tiver acesso SSH (Terminal web Hostinger, outra rede, etc.):" -ForegroundColor Cyan
    Write-Host "  1. Conecte na VPS (ssh root@72.61.56.204 ou pelo painel)" -ForegroundColor Gray
    Write-Host "  2. Copie o conteudo do arquivo acima e cole no terminal, ou use: nano /tmp/fix.sh , cole, salve (Ctrl+O, Enter, Ctrl+X)" -ForegroundColor Gray
    Write-Host "  3. Rode: chmod +x /tmp/fix.sh && bash /tmp/fix.sh" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Ou, do seu PC quando a rede permitir SSH: .\scripts\Corrigir-Nginx-PDV.ps1" -ForegroundColor Gray
    return
}

$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
Write-Host "Conectando na VPS (digite a senha SSH quando pedir)..." -ForegroundColor Cyan
$remoteCmd = "echo $b64 | base64 -d > /tmp/corrigir-nginx-pdv.sh && chmod +x /tmp/corrigir-nginx-pdv.sh && bash /tmp/corrigir-nginx-pdv.sh"
& ssh @sshOpt $remote $remoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Connection timed out = sua rede nao alcança a VPS na porta 22." -ForegroundColor Yellow
    Write-Host "Opcoes: use outra rede (ex. celular como hotspot) ou rode o script no servidor:" -ForegroundColor Yellow
    Write-Host "  .\scripts\Corrigir-Nginx-PDV.ps1 -ApenasGerarScript" -ForegroundColor Gray
    Write-Host "  Depois no Terminal web da Hostinger (ou onde tiver SSH), cole e execute o .sh gerado." -ForegroundColor Gray
    throw "Falha ao executar script na VPS."
}
Write-Host "`nPronto. Teste: http://pdv.srv1140258.hstgr.cloud" -ForegroundColor Green
