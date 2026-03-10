# Subir todas as mudanças e enviar para produção (GitHub)
# Execute no PowerShell na pasta do projeto PDV

Set-Location $PSScriptRoot

Write-Host "=== 1. Status atual ===" -ForegroundColor Cyan
git status

Write-Host "`n=== 2. Adicionando todos os arquivos ===" -ForegroundColor Cyan
git add -A

Write-Host "`n=== 3. Commit ===" -ForegroundColor Cyan
git commit -m "UI: titulos superiores removidos, menu dourado/preto, Acessorios edicao/exclusao, Buscar produto layout revertido"

Write-Host "`n=== 4. Push para origin/main ===" -ForegroundColor Cyan
git push origin main

Write-Host "`n=== Concluido. Repositorio atualizado no GitHub. ===" -ForegroundColor Green
Write-Host "Se sua producao usa git pull (VPS/servidor), conecte e execute:" -ForegroundColor Yellow
Write-Host "  cd /caminho/do/pdv  ;  git pull origin main  ;  reiniciar app (ex: systemctl restart pdv)" -ForegroundColor Yellow
