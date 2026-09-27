param(
    [string]$CommitHash = "unknown"
)

$ErrorActionPreference = "Stop"
$repoRoot = "C:\Users\malha\supplywatch"
$innerRoot = "$repoRoot\supplywatch"

function Write-SkippedReport {
    param([string]$Reason)
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $sessionDir = "$repoRoot\reviews\SESSION-$timestamp"
    New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null
    $report = @"
# Synthetic User Review -- $(Get-Date -Format "o")

## Status
SKIPPED: $Reason

## What was attempted
Automated post-commit worker (run-synthetic-review.ps1) for commit $CommitHash.

## Target reviewed
http://localhost:8501

## Diff context (commit only)
- Commit: $CommitHash
"@
    Set-Content -Path "$sessionDir\report.md" -Value $report -Encoding utf8
    Add-Content -Path "$repoRoot\reviews\latest.log" -Value "$(Get-Date -Format 'o')  SKIPPED  $sessionDir\report.md"
}

function Test-Dashboard {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8501" -UseBasicParsing -TimeoutSec 3
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

# 1. Ensure the dashboard is reachable, starting it the same way the
# existing `supplywatch` profile function does if it isn't.
if (-not (Test-Dashboard)) {
    try { docker start supplywatch-pg | Out-Null } catch {}

    $venvPython = "$innerRoot\.venv\Scripts\python.exe"
    Start-Process powershell -ArgumentList "-NoProfile", "-Command", "Set-Location '$innerRoot'; & '$venvPython' -m uvicorn main:app --port 8000" -WindowStyle Hidden
    Start-Process powershell -ArgumentList "-NoProfile", "-Command", "Set-Location '$innerRoot'; & '$venvPython' -m streamlit run dashboard\app.py" -WindowStyle Hidden

    $waited = 0
    while (-not (Test-Dashboard) -and $waited -lt 60) {
        Start-Sleep -Seconds 3
        $waited += 3
    }
    if (-not (Test-Dashboard)) {
        Write-SkippedReport "dashboard did not respond at http://localhost:8501 within 60s of startup attempt"
        exit 0
    }
}

# 2. Invoke Claude headlessly to run the synthetic-user-review skill.
# Each run gets its own log; the skill itself is responsible for writing
# reviews/SESSION-<timestamp>/report.md per its own instructions.
$logTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$claudeLog = "$repoRoot\reviews\claude-invocation-$logTimestamp.log"
$prompt = "Run the synthetic-user-review skill against the local dashboard for commit $CommitHash."

Set-Location $repoRoot
$before = Get-Date
& claude -p $prompt --allowedTools "Bash,Read,Glob,Grep,Write,ToolSearch,mcp__playwright__*" --permission-mode acceptEdits --permission-prompts none --output-format text *> $claudeLog

# 3. Verify the skill actually produced a report; if `claude` itself failed
# to run at all (crash, hang, not on PATH in this context), fall back to
# writing the skipped report directly so a missing report is never silent.
$reportExists = Get-ChildItem -Path "$repoRoot\reviews" -Filter "report.md" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt $before }

if (-not $reportExists) {
    Write-SkippedReport "claude -p invocation did not produce a report.md (see $claudeLog)"
}
