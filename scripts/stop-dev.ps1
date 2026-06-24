$ports = @(8081, 5174)
$processIds = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $ports } |
        Select-Object -ExpandProperty OwningProcess -Unique
)

foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

Write-Host "Stopped development services on ports 8081 and 5174."
