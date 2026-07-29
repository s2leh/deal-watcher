$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ProjectRoot "run-worker.cmd"
$TaskName = "DealWatcherWorker"

if (-not (Test-Path $Runner)) {
    throw "run-worker.cmd is missing."
}

$taskCommand = "`"$Runner`""
$args = @(
    "/Create",
    "/TN", $TaskName,
    "/SC", "ONLOGON",
    "/TR", $taskCommand,
    "/RL", "LIMITED",
    "/F"
)

$process = Start-Process -FilePath "schtasks.exe" `
    -ArgumentList $args `
    -NoNewWindow `
    -Wait `
    -PassThru

if ($process.ExitCode -ne 0) {
    throw "Scheduled Task creation failed. Exit code: $($process.ExitCode)"
}

Write-Host "Scheduled Task created: $TaskName" -ForegroundColor Green
Write-Host "The worker will start at Windows logon."
Write-Host "Run it now with:"
Write-Host "  schtasks /Run /TN `"$TaskName`""
