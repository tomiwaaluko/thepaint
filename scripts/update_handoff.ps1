param(
    [string]$HandoffPath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
if ([string]::IsNullOrWhiteSpace($HandoffPath)) {
    $HandoffPath = Join-Path $repoRoot "docs\HANDOFF.md"
}

Set-Location $repoRoot

function Get-GitLines {
    param([string[]]$GitArgs)

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & git @GitArgs 2>$null
    $ErrorActionPreference = $previousErrorActionPreference

    if ($LASTEXITCODE -ne 0 -or $null -eq $output) {
        return @()
    }

    return @($output | ForEach-Object { $_.ToString().TrimEnd() })
}

function Format-CodeBlock {
    param(
        [string]$Language,
        [string[]]$Lines,
        [string]$EmptyText = "(none)"
    )

    $body = if ($Lines.Count -gt 0) { $Lines } else { @($EmptyText) }
    return @((('```') + $Language)) + $body + @('```')
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$branch = (Get-GitLines @("branch", "--show-current") | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($branch)) {
    $branch = "(detached or unavailable)"
}

$status = Get-GitLines @("status", "--short", "--branch")
$diffStat = Get-GitLines @("diff", "--stat")
$changedFiles = Get-GitLines @("diff", "--name-only")
$stagedFiles = Get-GitLines @("diff", "--cached", "--name-only")
$recentCommits = Get-GitLines @("log", "--oneline", "-5")

$generated = @(
    "<!-- HANDOFF_AUTO_START -->",
    "## Generated Snapshot",
    "",
    "- Last refreshed: $timestamp",
    "- Repository: $repoRoot",
    "- Branch: $branch",
    "",
    "### Git Status",
    "",
    (Format-CodeBlock "text" $status),
    "",
    "### Changed Files",
    "",
    (Format-CodeBlock "text" $changedFiles),
    "",
    "### Staged Files",
    "",
    (Format-CodeBlock "text" $stagedFiles),
    "",
    "### Diff Stat",
    "",
    (Format-CodeBlock "text" $diffStat),
    "",
    "### Recent Commits",
    "",
    (Format-CodeBlock "text" $recentCommits),
    "<!-- HANDOFF_AUTO_END -->"
) | ForEach-Object {
    if ($_ -is [array]) { $_ } else { $_ }
}

$startMarker = "<!-- HANDOFF_AUTO_START -->"
$endMarker = "<!-- HANDOFF_AUTO_END -->"
$handoff = Get-Content -LiteralPath $HandoffPath -Raw
$pattern = "(?s)<!-- HANDOFF_AUTO_START -->.*?<!-- HANDOFF_AUTO_END -->"
$replacement = ($generated -join [Environment]::NewLine)

if ($handoff -notmatch [regex]::Escape($startMarker) -or $handoff -notmatch [regex]::Escape($endMarker)) {
    throw "Could not find generated snapshot markers in $HandoffPath"
}

$updated = [regex]::Replace($handoff, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($match) $replacement }, 1)
Set-Content -LiteralPath $HandoffPath -Value $updated -Encoding utf8

Write-Host "Updated $HandoffPath"
