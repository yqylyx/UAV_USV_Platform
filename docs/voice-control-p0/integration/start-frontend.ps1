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
$oldToken = $env:VITE_PLATFORM_INTEGRATION_TOKEN
$oldOverview = $env:VITE_OVERVIEW_WEBGL_URL
$tokenFile = Join-Path $repo '.local-tools/p0-integration/browser-integration-token.txt'
if (!(Test-Path -LiteralPath $tokenFile)) { throw 'Start isolated backend first to generate its local integration token.' }
$oldPort = $env:VITE_DEV_PORT
$oldTarget = $env:VITE_BACKEND_TARGET
try {
    $env:VITE_PLATFORM_INTEGRATION_TOKEN = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
    $env:VITE_OVERVIEW_WEBGL_URL = '/unity-overview/index.html?embedded=1'
    $env:VITE_DEV_PORT = '15174'
    $env:VITE_BACKEND_TARGET = 'http://127.0.0.1:18081'
    Push-Location $repo
    try {
        & $npmExe run dev --prefix frontend -- --host 127.0.0.1 --port 15174 --strictPort
        if ($LASTEXITCODE -ne 0) { throw "Frontend exited with code $LASTEXITCODE" }
    } finally { Pop-Location }
} finally { $env:VITE_PLATFORM_INTEGRATION_TOKEN = $oldToken; $env:VITE_OVERVIEW_WEBGL_URL = $oldOverview; $env:VITE_DEV_PORT = $oldPort; $env:VITE_BACKEND_TARGET = $oldTarget }
