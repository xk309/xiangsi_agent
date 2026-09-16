$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.env')) { throw '请先将 .env.example 复制为 .env 并填写连接配置。' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw '请先在 frontend 目录执行 npm install 和 npm run build。' }
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
