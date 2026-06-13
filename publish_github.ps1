param(
    [string]$RepoName = "warehouse-agent-mvp"
)

$ErrorActionPreference = "Stop"

gh auth status | Out-Null

$secretHits = rg -n "sk-[A-Za-z0-9]|OPENAI_API_KEY=.*sk-|ydata\.space" -g "!*.png" -g "!.env" -g "!publish_github.ps1"
if ($LASTEXITCODE -eq 0) {
    Write-Error "Potential secret-like content found. Review the output above before publishing."
}

.\run_tests.ps1

$status = git status --short
if ($status) {
    git add .
    git commit -m "Prepare public GitHub release"
}

if (-not (git remote get-url origin 2>$null)) {
    gh repo create $RepoName --public --source . --remote origin --push
} else {
    git push -u origin HEAD
}
