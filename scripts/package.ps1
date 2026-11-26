$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
$previousHashSeed = [Environment]::GetEnvironmentVariable('PYTHONHASHSEED', 'Process')
$previousEpoch = [Environment]::GetEnvironmentVariable('SOURCE_DATE_EPOCH', 'Process')
try {
    $epoch = (& git log -1 --format=%ct HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $epoch -notmatch '^\d+$') { throw 'Cannot determine source revision timestamp' }
    $env:PYTHONHASHSEED = '0'
    $env:SOURCE_DATE_EPOCH = $epoch
    & .venv/Scripts/pyinstaller --noconfirm --clean --onedir --name PersonalContext --add-data 'frontend/dist;frontend/dist' --add-data 'schemas;schemas' --add-data 'src/personalcontext/migrations;personalcontext/migrations' --collect-all alembic --copy-metadata alembic src/personalcontext/__main__.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/prune_alembic_record.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    [Environment]::SetEnvironmentVariable('PYTHONHASHSEED', $previousHashSeed, 'Process')
    [Environment]::SetEnvironmentVariable('SOURCE_DATE_EPOCH', $previousEpoch, 'Process')
    Pop-Location
}
