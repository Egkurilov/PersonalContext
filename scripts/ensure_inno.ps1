$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$cache = Join-Path $workspace '.tools'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$cacheResolved = (Resolve-Path -LiteralPath $cache).Path
if (-not $cacheResolved.StartsWith($workspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Tool cache must remain inside the workspace'
}
$target = Join-Path $cacheResolved 'inno-6.7.4'
if (-not ([IO.Path]::GetFullPath($target)).StartsWith($cacheResolved + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid compiler target' }
if (-not (Test-Path -LiteralPath $target)) {
    $id = [guid]::NewGuid().ToString('N')
    $installer = Join-Path $cacheResolved "inno-$id.exe"
    $staging = Join-Path $cacheResolved "inno-$id"
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe' -OutFile $installer
    $expected = (Get-Content -LiteralPath (Join-Path $workspace '.inno-sha256') -Raw).Trim()
    if ($expected -cnotmatch '^[0-9a-f]{64}$') { throw 'Invalid Inno Setup checksum pin' }
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ine $expected) { throw 'Inno Setup checksum mismatch' }
    $result = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', '/PORTABLE=1', "/DIR=`"$staging`"") -Wait -PassThru -WindowStyle Hidden
    if ($result.ExitCode -ne 0) { throw 'Portable Inno Setup installation failed' }
    $resolvedStage = (Resolve-Path -LiteralPath $staging).Path
    if (-not $resolvedStage.StartsWith($cacheResolved + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid staging directory' }
    if ((Test-Path -LiteralPath (Join-Path $resolvedStage 'unins000.exe')) -or -not (Test-Path -LiteralPath (Join-Path $resolvedStage 'ISCC.exe'))) { throw 'Invalid portable Inno Setup' }
    [IO.Directory]::Move($resolvedStage, $target)
    Remove-Item -LiteralPath $installer
}
$resolvedTarget = (Resolve-Path -LiteralPath $target).Path
if (-not $resolvedTarget.StartsWith($cacheResolved + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid compiler directory' }
Join-Path $resolvedTarget 'ISCC.exe'
