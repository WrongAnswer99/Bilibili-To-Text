param([string]$DownloadDirectory = '', [switch]$Check)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'register_protocol.ps1') -Force @PSBoundParameters
