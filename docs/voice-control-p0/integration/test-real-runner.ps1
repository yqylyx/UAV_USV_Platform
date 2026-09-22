[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Runner,
    [string]$Python = 'python.exe',
    [string]$Maven = 'mvn.cmd',
    [string]$JavaHome = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$runnerPath = (Resolve-Path -LiteralPath $Runner).Path
$pythonExe = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
$mavenExe = (Get-Command $Maven -CommandType Application -ErrorAction Stop).Source
if (!(Test-Path -LiteralPath $runnerPath -PathType Leaf)) { throw 'Runner must be a file.' }
$names = @('P0_REAL_RUNNER','PYTHON_COMMAND','JAVA_HOME')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:P0_REAL_RUNNER = $runnerPath
    $env:PYTHON_COMMAND = $pythonExe
    if ($JavaHome) { $env:JAVA_HOME = $JavaHome }
    Write-Host 'Real Java manager -> Python adapter. Fresh in-memory H2; no running backend or MySQL required.'
    Write-Host "Runner: $runnerPath"
    Write-Host "Runner SHA256: $((Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256).Hash)"
    $report = Join-Path $repo 'backend/target/p0-real-runner-report.json'
    # Prevent an old PASS report from being mistaken for a new run after compile failure.
    if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report }
    & $mavenExe '-f' (Join-Path $repo 'backend/pom.xml') '-Dtest=VoiceRealRunnerTests#realRunnerReadyHeartbeatAndFourActions' 'test'
    $result = $LASTEXITCODE
    if (Test-Path -LiteralPath $report) { Write-Host "Evidence: $report" }
    if ($result -ne 0) { throw "Real Runner verification FAILED (Maven exit $result). Inspect evidence and Surefire reports." }
    Write-Host 'PASS: selected Runner passed Ready, heartbeat, device membership, four actions and STOP exit. A fixture is not real-algorithm acceptance.'
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}

