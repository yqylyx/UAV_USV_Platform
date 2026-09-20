[CmdletBinding()]
param([string]$Npm = 'npm.cmd', [switch]$Start)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$npmExe = (Get-Command $Npm -CommandType Application -ErrorAction Stop).Source
if (!(Test-Path -LiteralPath (Join-Path $repo 'frontend/node_modules'))) { throw 'Install locked dependencies first: npm.cmd ci --prefix frontend' }
if (@(Get-NetTCPConnection -State Listen -LocalPort 15174 -ErrorAction SilentlyContinue).Count) { throw 'Port 15174 is already in use.' }
Write-Host 'P0 frontend: http://127.0.0.1:15174 -> backend http://127.0.0.1:18081'
Write-Host 'Use a separate browser profile; ports do not isolate cookies.'
if (!$Start) { Write-Host 'CHECK ONLY: add -Start to launch.'; return }
$oldPort = $env:VITE_DEV_PORT
$oldTarget = $env:VITE_BACKEND_TARGET
try {
    $env:VITE_DEV_PORT = '15174'
    $env:VITE_BACKEND_TARGET = 'http://127.0.0.1:18081'
    Push-Location $repo
    try {
        & $npmExe run dev --prefix frontend -- --host 127.0.0.1 --port 15174 --strictPort
        if ($LASTEXITCODE -ne 0) { throw "Frontend exited with code $LASTEXITCODE" }
    } finally { Pop-Location }
} finally { $env:VITE_DEV_PORT = $oldPort; $env:VITE_BACKEND_TARGET = $oldTarget }
