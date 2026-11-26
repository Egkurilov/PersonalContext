$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & "$PSScriptRoot/test.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & "$PSScriptRoot/sbom.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/pyinstaller --noconfirm --clean --onedir --name PersonalContext --add-data 'frontend/dist;frontend/dist' --add-data 'src/personalcontext/migrations;personalcontext/migrations' --collect-all alembic --copy-metadata alembic src/personalcontext/__main__.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/smoke_frozen.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
    if (-not $compiler) {
        $compiler = @("$env:LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe", "${env:ProgramFiles(x86)}/Inno Setup 6/ISCC.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $compiler) { throw 'Inno Setup 6 compiler ISCC.exe not found' }
    & $compiler /Qp installer/PersonalContext.iss
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/smoke_installer.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $hash = (Get-FileHash dist/PersonalContext-Setup.exe -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -Encoding ascii dist/PersonalContext-Setup.exe.sha256 "$hash  PersonalContext-Setup.exe"
    exit 0
} finally { Pop-Location }
