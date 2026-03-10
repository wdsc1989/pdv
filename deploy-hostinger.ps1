#Requires -Version 5.1
<#
.SYNOPSIS
  Deploy completo do PDV: commit + push para o GitHub e atualizacao na VPS Hostinger.
  Todas as senhas sao digitadas por voce no PowerShell quando solicitado.

.DESCRIPTION
  1) Adiciona alteracoes, faz commit e push para origin/main (quando o Git pedir, digite usuario/senha ou token).
  2) Conecta na VPS Hostinger via SSH e executa: git pull, reinicio do pdv-streamlit.
  Quando o SSH pedir, digite a senha do servidor.

.PARAMETER VpsHost
  Host da VPS (ex.: srv1140258.hstgr.cloud).

.PARAMETER SshUser
  Usuario SSH (ex.: root ou u123456789).

.PARAMETER AppDir
  Diretorio da app na VPS relativo ao home (ex.: apps/pdv).

.PARAMETER SkipPush
  Se informado, nao faz git add/commit/push; apenas atualiza a VPS (redeploy).

.PARAMETER SkipRedeploy
  Se informado, nao conecta na VPS; apenas faz push para o GitHub.

.PARAMETER SshKeyPath
  Caminho da chave SSH (opcional). Se nao informar, o SSH pedira a senha no terminal.

.EXAMPLE
  .\deploy-hostinger.ps1
  .\deploy-hostinger.ps1 -VpsHost srv1140258.hstgr.cloud -SshUser root
  .\deploy-hostinger.ps1 -SkipPush   # so atualiza a VPS (codigo ja commitado)
  .\deploy-hostinger.ps1 -SkipRedeploy   # so envia para o GitHub
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
    [switch] $SkipPush,

    [Parameter(Mandatory = $false)]
    [switch] $SkipRedeploy,

    [Parameter(Mandatory = $false)]
    [string] $SshKeyPath
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PDV - Deploy completo (GitHub + Hostinger)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- Parte 1: Git (push para GitHub) ----------
if (-not $SkipPush) {
    Write-Host "[1/2] Git - enviar alteracoes para o GitHub" -ForegroundColor Yellow
    Write-Host ""

    git status
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Erro ao executar git status." -ForegroundColor Red
        exit 1
    }
    Write-Host ""

    Write-Host "Adicionando todos os arquivos (git add -A)..." -ForegroundColor Gray
    git add -A
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Erro ao executar git add." -ForegroundColor Red
        exit 1
    }

    $status = git status --porcelain
    if ([string]::IsNullOrWhiteSpace($status)) {
        Write-Host "Nenhuma alteracao para commitar. Deseja apenas dar PUSH no que ja foi commitado? (S/N)" -ForegroundColor Magenta
        $s = Read-Host
        if ($s -notmatch '^[sS]') {
            Write-Host "Push cancelado. Deseja continuar para o redeploy na VPS mesmo assim? (S/N)" -ForegroundColor Magenta
            $s2 = Read-Host
            if ($s2 -notmatch '^[sS]') { exit 0 }
            $SkipPush = $true
        } else {
            Write-Host "Fazendo apenas push (sem novo commit)..." -ForegroundColor Gray
        }
    }

    if (-not $SkipPush) {
        Write-Host ""
        Write-Host "Digite a mensagem do commit (ou Enter para padrao):" -ForegroundColor Gray
        $msg = Read-Host
        if ([string]::IsNullOrWhiteSpace($msg)) {
            $msg = "Deploy: alteracoes do PDV"
        }
        git commit -m $msg
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Erro no commit." -ForegroundColor Red
            exit 1
        }
    }

    Write-Host ""
    Write-Host "Quando o Git pedir, digite seu USUARIO e SENHA (ou token) do GitHub aqui no PowerShell." -ForegroundColor Magenta
    Write-Host ""
    git push origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Falha no push. Verifique usuario/senha (ou token) do GitHub e conexao." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
    Write-Host "Push concluido." -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "[1/2] Git - pulado (SkipPush)" -ForegroundColor Gray
    Write-Host ""
}

# ---------- Parte 2: Redeploy na VPS Hostinger ----------
if (-not $SkipRedeploy) {
    Write-Host "[2/2] Hostinger VPS - atualizar codigo e reiniciar PDV" -ForegroundColor Yellow
    Write-Host "Host: $VpsHost | Usuario: $SshUser | App: $AppDir" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Quando o SSH pedir, digite a SENHA do servidor aqui no PowerShell." -ForegroundColor Magenta
    Write-Host ""

    $remote = "${SshUser}@${VpsHost}"
    $sshOpt = "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"
    $sshArgs = @($sshOpt + $remote)
    if ($SshKeyPath -and (Test-Path $SshKeyPath)) {
        $sshArgs = @("-i", $SshKeyPath) + $sshOpt + $remote
    }

    $remoteCmd = @"
set -e
INSTALL_DIR=`$HOME/$AppDir
echo '=== Redeploy PDV na Hostinger ==='
echo Diretorio: `$INSTALL_DIR
cd `$INSTALL_DIR || { echo 'Erro: diretorio nao existe'; exit 1; }
echo '--- Git pull ---'
git fetch origin
git reset --hard origin/main
git pull origin main
echo '--- Atualizar dependencias (pip) ---'
source .venv/bin/activate 2>/dev/null || true
pip install -r requirements.txt -q 2>/dev/null || true
echo '--- Parar e liberar porta 8502 ---'
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

    try {
        ssh-keygen -R $VpsHost 2>$null
        $remoteCmd | & ssh @sshArgs "bash -s"
        if ($LASTEXITCODE -ne 0) {
            throw "Falha no redeploy (SSH). Verifique usuario/senha e se o diretorio $AppDir existe na VPS."
        }
    } catch {
        Write-Host ""
        Write-Host "Erro: $_" -ForegroundColor Red
        Write-Host "Dica: confira host ($VpsHost), usuario ($SshUser), senha SSH e se OpenSSH esta instalado." -ForegroundColor Yellow
        exit 1
    }
    Write-Host ""
    Write-Host "Redeploy na VPS concluido." -ForegroundColor Green
} else {
    Write-Host "[2/2] Redeploy na VPS - pulado (SkipRedeploy)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Deploy completo finalizado." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "  URL: http://pdv.srv1140258.hstgr.cloud" -ForegroundColor Cyan
Write-Host ""
