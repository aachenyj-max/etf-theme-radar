param(
    [switch]$NoBrowser,
    [switch]$ExitAfterReady
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend"
$logRoot = Join-Path $projectRoot "data\logs"
$runtimeRoot = Join-Path $projectRoot "data\runtime"
$pythonCommand = if (Test-Path (Join-Path $projectRoot ".venv\Scripts\python.exe")) { Join-Path $projectRoot ".venv\Scripts\python.exe" } else { "python" }
$apiPort = 8001
$webPort = 3000
$serviceId = "etf-theme-radar"
$contractVersion = "2026-08-14.v11"
$apiBaseUri = "http://127.0.0.1:$apiPort"
$webUri = "http://127.0.0.1:$webPort"

# Windows PowerShell 5.1 cannot copy an environment containing both Path and PATH.
$pathKeys = @([Environment]::GetEnvironmentVariables("Process").Keys | Where-Object { $_ -ieq "Path" })
if ($pathKeys.Count -gt 1) { Remove-Item Env:PATH }

function Get-ListeningProcessId([int]$Port) {
    $match = netstat.exe -ano -p tcp | Select-String -Pattern "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$" | Select-Object -First 1
    if ($match -and $match.Matches.Count -gt 0) { return [int]$match.Matches[0].Groups[1].Value }
    return $null
}

function Get-RadarCapabilities([string]$BaseUri) {
    try {
        $response = Invoke-WebRequest -Uri "$BaseUri/api/capabilities" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ne 200) { return $null }
        return $response.Content | ConvertFrom-Json
    } catch { return $null }
}

function Test-RadarContract([string]$BaseUri, [switch]$RequireWorker) {
    $payload = Get-RadarCapabilities $BaseUri
    if ($null -eq $payload) { return $false }
    $contractMatches = $payload.service.id -eq $serviceId -and $payload.service.contract_version -eq $contractVersion
    if (-not $contractMatches) { return $false }
    if ($RequireWorker) {
        return $payload.worker.alive -eq $true -and $payload.worker.status -eq "healthy" -and -not [string]::IsNullOrWhiteSpace($payload.worker.heartbeat_at)
    }
    return $true
}

function Wait-ExistingCanonicalServices([int]$Attempts = 180) {
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        if ((Test-RadarContract $apiBaseUri -RequireWorker) -and (Test-RadarContract $webUri)) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

if (-not (Get-Command $pythonCommand -ErrorAction SilentlyContinue)) { throw "Python was not found. Install Python 3.11 or newer." }
if (-not (Get-Command "npm.cmd" -ErrorAction SilentlyContinue)) { throw "npm was not found. Install Node.js 20.9 or newer." }
if (-not (Test-Path (Join-Path $frontendRoot "node_modules\next\package.json"))) {
    Push-Location $frontendRoot
    try { & npm.cmd install; if ($LASTEXITCODE -ne 0) { throw "npm install failed" } }
    finally { Pop-Location }
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$lockPath = Join-Path $runtimeRoot "launcher.lock"
$lockStream = $null
try {
    try {
        $lockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch {
        if (Wait-ExistingCanonicalServices) {
            Write-Host "ETF Theme Radar is already running at $webUri with the expected service contract."
            if (-not $NoBrowser) { Start-Process $webUri }
            return
        }
        throw "Another launcher owns the runtime lock, but the canonical services did not become healthy."
    }

    $apiOwner = Get-ListeningProcessId $apiPort
    $apiReused = Test-RadarContract $apiBaseUri -RequireWorker
    if ($apiOwner -and -not $apiReused) { throw "Fixed API port $apiPort is occupied by PID $apiOwner, but it is not the required ETF Theme Radar contract." }

    $webOwner = Get-ListeningProcessId $webPort
    $webReused = Test-RadarContract $webUri
    if ($webOwner -and -not $webReused) { throw "Fixed frontend port $webPort is occupied by PID $webOwner, but it is not the required ETF Theme Radar frontend." }

    $apiOut = Join-Path $logRoot "api.log"
    $apiErr = Join-Path $logRoot "api-error.log"
    $webOut = Join-Path $logRoot "frontend.log"
    $webErr = Join-Path $logRoot "frontend-error.log"
    $api = $null
    $web = $null

    try {
        if (-not $apiReused) {
            $api = Start-Process -WindowStyle Hidden -PassThru -WorkingDirectory $projectRoot -FilePath $pythonCommand -ArgumentList "-m","uvicorn","etf_theme_radar.api:app","--host","127.0.0.1","--port",$apiPort -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr
        }
        if (-not $webReused) {
            $previousBackendUrl = [Environment]::GetEnvironmentVariable("RADAR_BACKEND_URL", "Process")
            $previousNextDistDir = [Environment]::GetEnvironmentVariable("RADAR_NEXT_DIST_DIR", "Process")
            try {
                $env:RADAR_BACKEND_URL = $apiBaseUri
                $env:RADAR_NEXT_DIST_DIR = ".next"
                $web = Start-Process -WindowStyle Hidden -PassThru -WorkingDirectory $frontendRoot -FilePath "npm.cmd" -ArgumentList "run","dev","--","-H","127.0.0.1","-p",$webPort -RedirectStandardOutput $webOut -RedirectStandardError $webErr
            } finally {
                if ($null -eq $previousBackendUrl) { Remove-Item Env:RADAR_BACKEND_URL -ErrorAction SilentlyContinue } else { $env:RADAR_BACKEND_URL = $previousBackendUrl }
                if ($null -eq $previousNextDistDir) { Remove-Item Env:RADAR_NEXT_DIST_DIR -ErrorAction SilentlyContinue } else { $env:RADAR_NEXT_DIST_DIR = $previousNextDistDir }
            }
        }

        for ($attempt = 0; $attempt -lt 180; $attempt++) {
            if ($api -and $api.HasExited) { throw "API exited during startup. Check data\logs\api-error.log." }
            if ($web -and $web.HasExited) { throw "Frontend exited during startup. Check data\logs\frontend-error.log." }
            if ((Test-RadarContract $apiBaseUri -RequireWorker) -and (Test-RadarContract $webUri)) { break }
            Start-Sleep -Seconds 1
        }
        if (-not ((Test-RadarContract $apiBaseUri -RequireWorker) -and (Test-RadarContract $webUri))) { throw "Canonical services did not pass the contract check within 180 seconds." }

        Write-Host "ETF Theme Radar is running at $webUri"
        Write-Host "API documentation: $apiBaseUri/docs"
        if (-not $NoBrowser) { Start-Process $webUri }
        if ($ExitAfterReady) { Write-Host "Startup contract check passed."; return }
        if ($apiReused -and $webReused) { Write-Host "Both canonical services were reused."; return }
        Write-Host "Keep this window open. Press Ctrl+C to stop the services started by this launcher."
        while ($true) {
            if ($api -and $api.HasExited) { throw "API stopped unexpectedly." }
            if ($web -and $web.HasExited) { throw "Frontend stopped unexpectedly." }
            Start-Sleep -Seconds 2
        }
    } finally {
        if ($web) {
            $webListener = Get-ListeningProcessId $webPort
            if ($webListener) { Stop-Process -Id $webListener -Force -ErrorAction SilentlyContinue }
            if (-not $web.HasExited) { Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue }
        }
        if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
    }
} finally {
    if ($lockStream) { $lockStream.Dispose() }
}
