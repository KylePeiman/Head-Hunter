#Requires -Version 5.1
# stop.ps1 — Stop the HeadHunter pipeline

$pidFile = Join-Path $PSScriptRoot ".pids.json"

if (-not (Test-Path $pidFile)) {
    Write-Host "No running instance found (.pids.json missing)."
    exit 0
}

$pidMap = Get-Content $pidFile | ConvertFrom-Json

foreach ($name in @("headhunter", "llama")) {
    $id = $pidMap.$name
    if ($id) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped $name (PID $id)"
    }
}

Remove-Item $pidFile
Write-Host "HeadHunter stopped."
