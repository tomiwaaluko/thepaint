param(
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$stateDir = Join-Path $repoRoot ".codex-tmp"
$pidPath = Join-Path $stateDir "handoff-watcher.pid"
$logPath = Join-Path $stateDir "handoff-watcher.log"
$updater = Join-Path $repoRoot "scripts\update_handoff.ps1"

if (-not (Test-Path -LiteralPath $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

Set-Content -LiteralPath $pidPath -Value $PID -Encoding ascii

try {
    while ($true) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $updater *> $null
            Add-Content -LiteralPath $logPath -Value "[$timestamp] Updated handoff snapshot."
        }
        catch {
            Add-Content -LiteralPath $logPath -Value "[$timestamp] Update failed: $($_.Exception.Message)"
        }

        Start-Sleep -Seconds $IntervalSeconds
    }
}
finally {
    if (Test-Path -LiteralPath $pidPath) {
        Remove-Item -LiteralPath $pidPath -Force
    }
}
