$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    python -m uv sync --locked
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $hooksPath = git config --get core.hooksPath
    if (-not $hooksPath) {
        git config --local core.hooksPath .githooks
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } elseif ($hooksPath -ne '.githooks') {
        Write-Warning 'Existing Git hooks path retained; run scripts/check_index.py in your existing pre-commit hook.'
    }
    npm ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python -m personalcontext
    exit $LASTEXITCODE
} finally { Pop-Location }
