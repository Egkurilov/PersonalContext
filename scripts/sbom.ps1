$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    New-Item -ItemType Directory -Force dist | Out-Null
    python -m uv export --locked --format cyclonedx1.5 --output-file dist/sbom-python.json | Out-Null
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm sbom --prefix frontend --sbom-format cyclonedx --sbom-type application --package-lock-only | Set-Content -Encoding utf8NoBOM dist/sbom-frontend.json
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv/Scripts/python scripts/python_licenses.py
    exit $LASTEXITCODE
} finally { Pop-Location }
