param(
    [string]$Message = "checkpoint: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    [switch]$Push
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$status = git status --short
if (-not $status) {
    Write-Host 'No changes to commit.'
    exit 0
}

git add --all

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host 'No staged changes after filtering.'
    exit 0
}

git commit -m $Message

if ($Push) {
    $remote = git remote
    if (-not $remote) {
        Write-Host 'Commit created, but no git remote is configured. Skipping push.'
        exit 0
    }

    $branch = git branch --show-current
    if (-not $branch) {
        Write-Host 'Commit created, but current branch could not be detected. Skipping push.'
        exit 0
    }

    git push origin $branch
}
