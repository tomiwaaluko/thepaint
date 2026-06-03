param(
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$stateDir = Join-Path $repoRoot ".codex-tmp"
$outPath = Join-Path $stateDir "handoff-watcher.stdout.log"
$errPath = Join-Path $stateDir "handoff-watcher.stderr.log"
$watcher = Join-Path $repoRoot "scripts\start_handoff_watcher.ps1"

if (-not (Test-Path -LiteralPath $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "powershell.exe"
$psi.WorkingDirectory = $repoRoot
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$watcher`" -IntervalSeconds $IntervalSeconds"

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
[void]$process.Start()

# Drain stdout/stderr asynchronously to the log files so the buffers don't block.
$null = $process.StandardOutput.ReadToEndAsync().ContinueWith({
    param($t) [System.IO.File]::WriteAllText($outPath, $t.Result)
})
$null = $process.StandardError.ReadToEndAsync().ContinueWith({
    param($t) [System.IO.File]::WriteAllText($errPath, $t.Result)
})

Write-Host "Started handoff watcher process $($process.Id). Logs: $outPath"
