$ErrorActionPreference = "Stop"
schtasks.exe /Delete /TN "DealWatcherWorker" /F
Write-Host "Scheduled Task removed."
