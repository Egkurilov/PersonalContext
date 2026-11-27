$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
$previousHashSeed = [Environment]::GetEnvironmentVariable('PYTHONHASHSEED', 'Process')
$previousEpoch = [Environment]::GetEnvironmentVariable('SOURCE_DATE_EPOCH', 'Process')
$previousPath = [Environment]::GetEnvironmentVariable('PATH', 'Process')
$previousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$previousPythonHome = [Environment]::GetEnvironmentVariable('PYTHONHOME', 'Process')
$previousVenv = [Environment]::GetEnvironmentVariable('VIRTUAL_ENV', 'Process')
try {
    $epoch = (& git log -1 --format=%ct HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $epoch -notmatch '^\d+$') { throw 'Cannot determine source revision timestamp' }
    $env:PYTHONHASHSEED = '0'
    $env:SOURCE_DATE_EPOCH = $epoch
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $null, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONHOME', $null, 'Process')
    $env:VIRTUAL_ENV = (Resolve-Path -LiteralPath '.venv').Path
    & .venv/Scripts/pyinstaller --noconfirm --clean --onedir --name PersonalContext --add-data 'frontend/dist;frontend/dist' --add-data 'schemas;schemas' --add-data 'src/personalcontext/migrations/env.py;personalcontext/migrations' --add-data 'src/personalcontext/migrations/versions/*.py;personalcontext/migrations/versions' --collect-all alembic --copy-metadata alembic src/personalcontext/__main__.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/normalize_base_zip.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/normalize_packaged_text.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/prune_alembic_record.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    [Environment]::SetEnvironmentVariable('PYTHONHASHSEED', $previousHashSeed, 'Process')
    [Environment]::SetEnvironmentVariable('SOURCE_DATE_EPOCH', $previousEpoch, 'Process')
    [Environment]::SetEnvironmentVariable('PATH', $previousPath, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $previousPythonPath, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONHOME', $previousPythonHome, 'Process')
    [Environment]::SetEnvironmentVariable('VIRTUAL_ENV', $previousVenv, 'Process')
    Pop-Location
}
