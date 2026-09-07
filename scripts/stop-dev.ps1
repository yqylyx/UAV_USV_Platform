$ports = @(8081, 5174)
$projectRoot = Split-Path -Parent $PSScriptRoot
$algorithmRunner = [System.IO.Path]::GetFullPath(
    (Join-Path $projectRoot 'algorithm-service\runner.py')
).ToLowerInvariant()
$processIds = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $ports } |
        Select-Object -ExpandProperty OwningProcess -Unique
)

foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

$algorithmProcessIds = @(
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $commandLine = if ($null -eq $_.CommandLine) { '' } else { $_.CommandLine.ToLowerInvariant() }
            $commandLine.Contains($algorithmRunner)
        } |
        Select-Object -ExpandProperty ProcessId -Unique
)

foreach ($processId in $algorithmProcessIds) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

Write-Host (
    "Stopped development services on ports 8081 and 5174; " +
    "removed $($algorithmProcessIds.Count) project algorithm runner process(es)."
)
