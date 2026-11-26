$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    Write-Host "PersonalContext: preparing Python dependencies"
    & "$PSScriptRoot/uv.ps1" sync --locked --python (Get-Content .python-version -Raw).Trim()
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/check_python.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/check_frontend.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "PersonalContext: checking Git hooks"
    $hooksPath = git config --get core.hooksPath
    if (-not $hooksPath) {
        git config --local core.hooksPath .githooks
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } elseif ($hooksPath -ne '.githooks') {
        Write-Warning 'Existing Git hooks path retained; run scripts/check_index.py in your existing pre-commit hook.'
    }
    Write-Host "PersonalContext: installing frontend dependencies"
    npm ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "PersonalContext: building frontend"
    npm run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "PersonalContext: starting application"
    & .venv/Scripts/python -m personalcontext --demo
    exit $LASTEXITCODE
} finally { Pop-Location }
