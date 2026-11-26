$uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($uvCommand) {
    & $uvCommand.Source @args
} else {
    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pythonCommand) {
        Write-Error 'Install uv or Python with the uv module before running this script.'
        exit 1
    }
    & $pythonCommand.Source -m uv @args
}
exit $LASTEXITCODE
