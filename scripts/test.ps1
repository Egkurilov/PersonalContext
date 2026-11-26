$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & "$PSScriptRoot/uv.ps1" sync --locked
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/ruff check src tests scripts/*.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/mypy src/personalcontext
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm run build --prefix frontend
    exit $LASTEXITCODE
} finally { Pop-Location }
