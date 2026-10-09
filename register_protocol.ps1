param([string]$DownloadDirectory = '', [switch]$Unregister, [switch]$Check, [switch]$Force)
$ErrorActionPreference = 'Stop'
$arguments = @((Join-Path $PSScriptRoot 'register_protocol.py'))
if ($DownloadDirectory) { $arguments += @('--download-directory', $DownloadDirectory) }
if ($Unregister) { $arguments += '--unregister' }
if ($Check) { $arguments += '--check' }
if ($Force) { $arguments += '--force' }
& python.exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'Protocol registration failed; see the error above.' }
