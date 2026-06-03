param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$pidPath = Join-Path $repoRoot ".codex-tmp\handoff-watcher.pid"

if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Host "Handoff watcher is not running."
    exit 0
}

$watcherPid = (Get-Content -LiteralPath $pidPath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($watcherPid)) {
    Remove-Item -LiteralPath $pidPath -Force
    Write-Host "Removed empty watcher pid file."
    exit 0
}

$process = Get-Process -Id ([int]$watcherPid) -ErrorAction SilentlyContinue
if ($null -eq $process) {
    Remove-Item -LiteralPath $pidPath -Force
    Write-Host "Watcher process was not found; removed stale pid file."
    exit 0
}

Stop-Process -Id ([int]$watcherPid)
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
Write-Host "Stopped handoff watcher process $watcherPid."
