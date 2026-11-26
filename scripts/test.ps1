$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & "$PSScriptRoot/uv.ps1" sync --locked --python (Get-Content .python-version -Raw).Trim()
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/check_python.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $nodeDir = & .venv/Scripts/python scripts/ensure_frontend.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($nodeDir -ne '__CURRENT__') { $env:PATH = "$nodeDir;$env:PATH" }
    & .venv/Scripts/python scripts/check_frontend.py
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
