param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$hooksDir = Join-Path $repoRoot ".git\hooks"
$updater = Join-Path $repoRoot "scripts\update_handoff.ps1"

if (-not (Test-Path -LiteralPath $hooksDir)) {
    throw "Git hooks directory not found: $hooksDir"
}

$hookBody = @"
#!/bin/sh
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$updater" >/dev/null 2>&1
exit 0
"@

$hookNames = @("pre-commit", "post-commit", "post-checkout", "post-merge")
foreach ($hookName in $hookNames) {
    $hookPath = Join-Path $hooksDir $hookName
    Set-Content -LiteralPath $hookPath -Value $hookBody -Encoding ascii
}

Write-Host "Installed handoff updater hooks: $($hookNames -join ', ')"
