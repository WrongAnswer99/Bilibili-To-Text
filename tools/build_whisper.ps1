param([ValidateSet('cuda','cpu')][string]$Backend = 'cuda')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cmakeCommand = Get-Command cmake.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$cmake = if ($cmakeCommand) { $cmakeCommand.Source } else { Join-Path $env:USERPROFILE 'scoop/apps/cmake/current/bin/cmake.exe' }
$compilerCommand = Get-Command g++.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$compilerDir = if ($compilerCommand) { Split-Path -Parent $compilerCommand.Source } else { Join-Path $env:USERPROFILE 'scoop/apps/mingw/current/bin' }
if (-not (Test-Path -LiteralPath $cmake) -or -not (Test-Path -LiteralPath (Join-Path $compilerDir 'g++.exe'))) {
    throw 'Building requires CMake and MinGW-w64 (g++); add them to PATH.'
}
$oldPath = $env:PATH
try {
    $env:PATH = $compilerDir + ';' + (Split-Path -Parent $cmake) + ';' + $oldPath
    $build = Join-Path $root ("build-" + $Backend)
    & $cmake -S $root -B $build -G 'MinGW Makefiles' "-DWHISPER_BACKEND=$Backend"
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed' }
    & $cmake --build $build --parallel 8
    if ($LASTEXITCODE -ne 0) { throw 'Whisper bridge build failed' }
    & $cmake --build $build --target test
    if ($LASTEXITCODE -ne 0) { throw 'Native regression checks failed' }
    Write-Host 'Project-local Whisper engine ready in runtime.'
} finally { $env:PATH = $oldPath }
