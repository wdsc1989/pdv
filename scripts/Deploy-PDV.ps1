#Requires -Version 5.1
<#
.SYNOPSIS
  Deploy do PDV na VPS Hostinger via PowerShell.
  Cria diretórios separados (ex.: ~/apps/pdv), banco PostgreSQL novo na VPS, Nginx e systemd.

.DESCRIPTION
  Execute a partir da pasta do projeto PDV (ou informe -ProjectPath).
  Você será solicitado a informar: host, usuário SSH, senha do banco (e opcionalmente diretório e nome do banco).
  O script envia os arquivos necessários e executa o deploy-vps.sh na VPS.

.PARAMETER VpsHost
  Host da VPS (ex.: srv1140258.hstgr.cloud).

.PARAMETER SshUser
  Usuário SSH (ex.: u123456789).

.PARAMETER AppDir
  Diretório relativo ao home na VPS (ex.: apps/pdv). Igual à ideia do contábil: um dir por app.

.PARAMETER DbName
  Nome do banco PostgreSQL a ser criado na VPS (ex.: pdv_db).

.PARAMETER DbUser
  Usuário PostgreSQL (ex.: pdv_user).

.PARAMETER DbPassword
  Senha do usuário PostgreSQL (será usada para criar o banco e no .env).

.PARAMETER ProjectPath
  Caminho da pasta do projeto PDV (onde está scripts/deploy-vps.sh). Padrão: diretório atual.

.PARAMETER SshKeyPath
  Caminho da chave SSH (opcional). Se não informar, usará senha interativa.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string] $VpsHost,

    [Parameter(Mandatory = $false)]
    [string] $SshUser,

    [Parameter(Mandatory = $false)]
    [string] $AppDir = "apps/pdv",

    [Parameter(Mandatory = $false)]
    [string] $DbName = "pdv_db",

    [Parameter(Mandatory = $false)]
    [string] $DbUser = "pdv_user",

    [Parameter(Mandatory = $false)]
    [string] $DbPassword,

    [Parameter(Mandatory = $false)]
    [string] $ProjectPath = (Get-Location).Path,

    [Parameter(Mandatory = $false)]
    [string] $SshKeyPath
)

$ErrorActionPreference = "Stop"

# Resolver caminho do projeto e do script Bash
$scriptDir = Join-Path $ProjectPath "scripts"
$bashScript = Join-Path $scriptDir "deploy-vps.sh"
if (-not (Test-Path $bashScript)) {
    Write-Error "Script não encontrado: $bashScript. Execute a partir da pasta do projeto PDV ou informe -ProjectPath."
}

# Coletar dados que faltarem
if (-not $VpsHost) { $VpsHost = Read-Host "Host da VPS (ex.: srv1140258.hstgr.cloud ou 72.61.56.204)" }
if (-not $SshUser) { $SshUser = Read-Host "Usuário SSH - apenas o nome (ex.: root ou u123456789)" }
if (-not $DbPassword) {
    $securePass = Read-Host "Senha do usuário PostgreSQL ($DbUser)" -AsSecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePass)
    try { $DbPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR) } finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR) }
}

$remote = "${SshUser}@${VpsHost}"
$sshOpt = "-o", "StrictHostKeyChecking=accept-new"
$sshArgs = @($sshOpt + $remote)
if ($SshKeyPath -and (Test-Path $SshKeyPath)) { $sshArgs = @("-i", $SshKeyPath) + $sshOpt + $remote }

# Arquivo de variáveis para o script na VPS (evita senha na linha de comando); usar LF para a VPS
$envContent = @"
APP_DIR=$AppDir
DB_NAME=$DbName
DB_USER=$DbUser
DB_PASS=$DbPassword
"@
$envContent = $envContent -replace "`r`n", "`n" -replace "`r", "`n"

$tempEnvPath = Join-Path ([System.IO.Path]::GetTempPath()) "pdv-deploy-$(Get-Random).env"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
try {
    [System.IO.File]::WriteAllText($tempEnvPath, $envContent, $utf8NoBom)

    Write-Host "`n=== Deploy PDV na VPS ===" -ForegroundColor Cyan
    Write-Host "Host: $VpsHost | Usuário: $SshUser | App: $AppDir | Banco: $DbName"
    Write-Host ""
    # Remover chave antiga do known_hosts (evita "REMOTE HOST IDENTIFICATION HAS CHANGED") e aceitar a nova
    ssh-keygen -R $VpsHost 2>$null

    # 1) Enviar arquivo de variáveis para a VPS
    Write-Host "Enviando variáveis de deploy para a VPS..." -ForegroundColor Yellow
    $scpArgs = $sshOpt + $tempEnvPath + "${remote}:/tmp/pdv-deploy.env"
    if ($SshKeyPath -and (Test-Path $SshKeyPath)) { $scpArgs = @("-i", $SshKeyPath) + $sshOpt + $tempEnvPath + "${remote}:/tmp/pdv-deploy.env" }
    & scp @scpArgs
    if ($LASTEXITCODE -ne 0) { throw "Falha ao enviar arquivo de variáveis (scp)." }

    # 2) Enviar script Bash para a VPS (converter CRLF -> LF para rodar no Linux)
    Write-Host "Enviando script de deploy para a VPS..." -ForegroundColor Yellow
    $bashContent = [System.IO.File]::ReadAllText($bashScript)
    $bashContent = $bashContent -replace "`r`n", "`n" -replace "`r", "`n"
    $tempBashPath = Join-Path ([System.IO.Path]::GetTempPath()) "deploy-pdv-vps-$(Get-Random).sh"
    [System.IO.File]::WriteAllText($tempBashPath, $bashContent, $utf8NoBom)
    try {
        $scpScriptArgs = $sshOpt + $tempBashPath + "${remote}:/tmp/deploy-pdv-vps.sh"
        if ($SshKeyPath -and (Test-Path $SshKeyPath)) { $scpScriptArgs = @("-i", $SshKeyPath) + $sshOpt + $tempBashPath + "${remote}:/tmp/deploy-pdv-vps.sh" }
        & scp @scpScriptArgs
        if ($LASTEXITCODE -ne 0) { throw "Falha ao enviar script (scp)." }
    } finally {
        if (Test-Path $tempBashPath) { Remove-Item $tempBashPath -Force }
    }

    # 3) Executar o script na VPS (pede senha SSH se não usar chave)
    Write-Host "Executando deploy na VPS (pode pedir senha SSH)..." -ForegroundColor Yellow
    $cmd = "chmod +x /tmp/deploy-pdv-vps.sh && bash /tmp/deploy-pdv-vps.sh"
    & ssh @sshArgs $cmd
    if ($LASTEXITCODE -ne 0) { throw "Falha ao executar script na VPS." }

    Write-Host "`n=== Deploy concluído com sucesso ===" -ForegroundColor Green
    Write-Host "URL: http://pdv.srv1140258.hstgr.cloud"
    Write-Host "Login: admin / admin123 (altere em produção)"
}
finally {
    if (Test-Path $tempEnvPath) { Remove-Item $tempEnvPath -Force }
}
