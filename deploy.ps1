# =============================================================================
# deploy.ps1 - Subir mudancas do PDV para o GitHub (produção)
# Execute no PowerShell na pasta do projeto. Quando o Git pedir, digite a senha.
# =============================================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PDV - Deploy para GitHub (origin/main)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Status
Write-Host "[1/4] Status do repositorio..." -ForegroundColor Yellow
git status
if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao executar git status." -ForegroundColor Red
    exit 1
}
Write-Host ""

# 2. Adicionar tudo
Write-Host "[2/4] Adicionando todos os arquivos (git add -A)..." -ForegroundColor Yellow
git add -A
if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao executar git add." -ForegroundColor Red
    exit 1
}
Write-Host ""

# Verificar se ha algo para commitar
$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "Nenhuma alteracao para commitar. Deseja apenas dar PUSH no que ja foi commitado? (S/N)" -ForegroundColor Magenta
    $s = Read-Host
    if ($s -notmatch '^[sS]') {
        Write-Host "Deploy cancelado." -ForegroundColor Gray
        exit 0
    }
    # Pula o commit, vai direto pro push
    $skipCommit = $true
} else {
    $skipCommit = $false
}

# 3. Commit (se houver alteracoes)
if (-not $skipCommit) {
    Write-Host "[3/4] Commit..." -ForegroundColor Yellow
    Write-Host "Digite a mensagem do commit (ou Enter para usar a padrao):" -ForegroundColor Gray
    $msg = Read-Host
    if ([string]::IsNullOrWhiteSpace($msg)) {
        $msg = "Deploy: alteracoes do PDV"
    }
    git commit -m $msg
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Erro no commit (pode ser que nao haja nada para commitar)." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
} else {
    Write-Host "[3/4] Pulando commit (nenhuma alteracao)." -ForegroundColor Gray
    Write-Host ""
}

# 4. Push - aqui o Git pode pedir usuario e senha (token) no proprio PowerShell
Write-Host "[4/4] Push para origin/main..." -ForegroundColor Yellow
Write-Host "Se o Git pedir usuario/senha (ou token), digite aqui mesmo no PowerShell." -ForegroundColor Magenta
Write-Host ""
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Falha no push. Verifique:" -ForegroundColor Red
    Write-Host "  - Usuario e senha (ou Personal Access Token) do GitHub" -ForegroundColor Red
    Write-Host "  - Conexao com a internet" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Deploy concluido. Repositorio atualizado." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Em producao (servidor), execute:" -ForegroundColor Yellow
Write-Host "  cd C:\caminho\do\pdv" -ForegroundColor Gray
Write-Host "  git pull origin main" -ForegroundColor Gray
Write-Host "  (reiniciar o app se necessario)" -ForegroundColor Gray
Write-Host ""
