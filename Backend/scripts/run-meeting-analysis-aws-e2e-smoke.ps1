$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env"

if (-not (Test-Path $envFile)) {
    throw ".env not found: $envFile"
}

# Export .env entries into this process so AWS DefaultCredentialsProvider can read them.
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -ne "" -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$required = @(
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "MEETING_ANALYSIS_COMMAND_QUEUE_URL",
    "AWS_ANALYSIS_RESULT_QUEUE_URL",
    "AWS_ANALYSIS_RESULT_BUCKET"
)

foreach ($name in $required) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required .env value is missing: $name"
    }
    if ($value.Contains("{") -or $value.Contains("}")) {
        throw "Malformed or placeholder value: $name"
    }
}

if ([string]::IsNullOrWhiteSpace($env:MEETING_ANALYSIS_GRAPH_SNAPSHOT_S3_PREFIX)) {
    $env:MEETING_ANALYSIS_GRAPH_SNAPSHOT_S3_PREFIX = "graph-snapshots/"
}

Write-Host "Running real AWS meeting-analysis E2E smoke test..."
Write-Host "Stop the real Python worker and Java consumers first. The Command and Result queues must be empty."

Push-Location $projectRoot
try {
    & .\gradlew.bat smokeTest --tests "*MeetingAnalysisAwsE2ESmokeTest" --no-daemon
    if ($LASTEXITCODE -ne 0) {
        throw "AWS E2E smoke test failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
