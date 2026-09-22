[CmdletBinding()]
param(
    [string]$Java = 'java.exe',
    [string]$Python = 'python.exe',
    [string]$Runner = '',
    [switch]$EnableVoice,
    [switch]$Start
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$config = (Resolve-Path (Join-Path $PSScriptRoot 'application-p0-integration.yml')).Path
$jar = Join-Path $repo 'backend/target/platform-backend-0.1.0-SNAPSHOT.jar'
if (!(Test-Path -LiteralPath $jar -PathType Leaf)) { throw 'Build backend first with mvn.cmd -f backend/pom.xml -DskipTests package.' }
if (!$Runner) { $Runner = Join-Path $repo 'algorithm-service/runner.py' }
$runnerFile = (Resolve-Path -LiteralPath $Runner).Path
$pythonExe = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
$javaExe = (Get-Command $Java -CommandType Application -ErrorAction Stop).Source
# Refuse inherited Spring/Java injection rather than silently using a developer datasource.
$overrides = @(Get-ChildItem Env: | Where-Object {
    $_.Name -match '^(SPRING_|APP_|SERVER_|MANAGEMENT_)|^(JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS|_JAVA_OPTIONS)$'
})
if ($overrides.Count) { throw ('Use a clean terminal; conflicting environment variable names: ' + (($overrides | ForEach-Object Name) -join ', ')) }
$busy = @(Get-NetTCPConnection -State Listen -LocalPort 18081 -ErrorAction SilentlyContinue)
if ($busy.Count) { throw 'Port 18081 is in use; stop only the identified integration process or choose a separately reviewed configuration.' }
Write-Host 'P0 backend: 127.0.0.1:18081; database=uav_usv_p0_integration; DB user=p0_integration; web user=p0_admin'
Write-Host "Runner: $runnerFile"
Write-Host "Voice enabled: $($EnableVoice.IsPresent). Gateway/ROS/visual-sensor connections disabled."
if (!$Start) { Write-Host 'CHECK ONLY: no service, process runner, database or migration started. Add -Start to launch.'; return }
function Read-SecretText([string]$label) {
    $value = Read-Host $label -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
$names = @('P0_DB_PASSWORD','P0_ADMIN_PASSWORD','P0_INTEGRATION_TOKEN','P0_PYTHON','P0_RUNNER')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:P0_DB_PASSWORD = Read-SecretText 'Dedicated p0_integration database password'
    $env:P0_ADMIN_PASSWORD = Read-SecretText 'p0_admin login password (used on first creation only)'
    if ([string]::IsNullOrWhiteSpace($env:P0_DB_PASSWORD) -or [string]::IsNullOrWhiteSpace($env:P0_ADMIN_PASSWORD)) { throw 'Passwords must not be empty.' }
    $env:P0_INTEGRATION_TOKEN = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    $tokenDir = Join-Path $repo '.local-tools/p0-integration'
    New-Item -ItemType Directory -Path $tokenDir -Force | Out-Null
    $env:P0_INTEGRATION_TOKEN | Set-Content -LiteralPath (Join-Path $tokenDir 'browser-integration-token.txt') -Encoding ASCII
    $env:P0_PYTHON = $pythonExe
    $env:P0_RUNNER = $runnerFile
    $configUri = ([Uri]$config).AbsoluteUri
    $voice = $EnableVoice.IsPresent.ToString().ToLowerInvariant()
    Push-Location $repo
    try {
        & $javaExe '-jar' $jar "--spring.config.location=$configUri" '--spring.profiles.active=p0-integration' "--app.voicecontrol.enabled=$voice"
        if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE" }
    } finally { Pop-Location }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
