# Archive App Diagnostic Tool (Windows)

$ErrorActionPreference = 'SilentlyContinue'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Header($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Cyan
    Write-Host ("-" * $text.Length) -ForegroundColor DarkCyan
}

function Write-Ok($text)   { Write-Host "  [OK]  $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  [!]   $text" -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host "  [X]   $text" -ForegroundColor Red }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ---------------------------------------------------------------------------
# Detect compose file
# ---------------------------------------------------------------------------
function Get-ComposeFile {
    $prod = Join-Path $ScriptDir "docker-compose.prod.yml"
    $dev  = Join-Path $ScriptDir "docker-compose.yml"
    if (Test-Path $prod) { return $prod }
    if (Test-Path $dev)  { return $dev }
    return $null
}

# ---------------------------------------------------------------------------
# Port check — returns object with Pid and ProcessName, or $null
# ---------------------------------------------------------------------------
function Get-PortInfo($port) {
    $lines = netstat -ano | Select-String "TCP\s+\S+:$port\s+\S+\s+LISTENING"
    if (-not $lines) { return $null }

    $pid = ($lines[0] -split '\s+')[-1]
    if (-not $pid -or $pid -eq '0') { return $null }

    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    return [PSCustomObject]@{ Pid = $pid; Name = if ($proc) { $proc.Name } else { "unknown" } }
}

# ---------------------------------------------------------------------------
# Section 1 — Port status
# ---------------------------------------------------------------------------
function Show-Ports {
    Write-Header "Port Status"

    $ports = @{
        9090 = "Agent"
        4200 = "Frontend"
        8000 = "Backend"
        9998 = "Tika"
        5432 = "Postgres"
    }

    foreach ($port in 9090, 4200, 8000, 9998, 5432) {
        $label = $ports[$port]
        $pad   = " " * (12 - $label.Length)
        $info  = Get-PortInfo $port
        if ($info) {
            Write-Warn "Port $port ($label):$pad IN USE by $($info.Name) (PID $($info.Pid))"
        } else {
            Write-Ok   "Port $port ($label):$pad FREE"
        }
    }
}

# ---------------------------------------------------------------------------
# Section 2 — Docker status
# ---------------------------------------------------------------------------
function Show-Docker {
    Write-Header "Docker"

    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Docker: Not running"
        return
    }
    Write-Ok "Docker: Running"

    $composeFile = Get-ComposeFile
    if (-not $composeFile) {
        Write-Warn "No docker-compose file found in $ScriptDir"
        return
    }

    Write-Host "  Compose file: $composeFile" -ForegroundColor DarkCyan
    Write-Host ""

    $ps = docker compose -f $composeFile ps --format "table {{.Name}}`t{{.Status}}" 2>&1
    if ($ps -match "no such file" -or ($ps | Where-Object { $_ -notmatch "^NAME" }) -eq $null) {
        Write-Warn "No containers found for this compose file"
    } else {
        $ps | ForEach-Object { Write-Host "    $_" }
    }
}

# ---------------------------------------------------------------------------
# Section 3 — Action menu
# ---------------------------------------------------------------------------
function Confirm-Action($msg) {
    Write-Host ""
    Write-Host "  $msg" -ForegroundColor Yellow
    $answer = Read-Host "  Continue? (y/n)"
    return ($answer -eq 'y' -or $answer -eq 'Y')
}

function Stop-Port($port, $label) {
    $info = Get-PortInfo $port
    if (-not $info) {
        Write-Warn "Nothing running on port $port ($label)"
        return
    }
    if (Confirm-Action "This will stop: $($info.Name) (PID $($info.Pid)) on port $port ($label).") {
        taskkill /PID $info.Pid /F | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Stopped $($info.Name) (PID $($info.Pid))"
        } else {
            Write-Err "Failed to stop PID $($info.Pid)"
        }
    } else {
        Write-Warn "Skipped port $port"
    }
}

function Stop-DockerServices {
    $composeFile = Get-ComposeFile
    if (-not $composeFile) {
        Write-Err "No docker-compose file found — cannot run docker compose down"
        return
    }
    if (Confirm-Action "This will run: docker compose down (using $composeFile).") {
        docker compose -f $composeFile down
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Docker services stopped"
        } else {
            Write-Err "docker compose down failed"
        }
    } else {
        Write-Warn "Skipped Docker shutdown"
    }
}

function Stop-Everything {
    $appPorts = @{ 4200 = "Frontend"; 8000 = "Backend"; 9998 = "Tika"; 5432 = "Postgres" }
    foreach ($port in 4200, 8000, 9998, 5432) {
        Stop-Port $port $appPorts[$port]
    }
    Stop-DockerServices
    Stop-Port 9090 "Agent"
}

function Show-Menu {
    Write-Header "Actions"
    Write-Host "  a) Stop everything (all ports + docker compose down)"
    Write-Host "  b) Stop Docker services only (docker compose down)"
    Write-Host "  c) Stop agent only (port 9090)"
    Write-Host "  d) Exit without changes"
    Write-Host ""
    $choice = Read-Host "  Choose [a/b/c/d]"
    switch ($choice.ToLower()) {
        'a' { Stop-Everything }
        'b' { Stop-DockerServices }
        'c' { Stop-Port 9090 "Agent" }
        'd' { Write-Host "`n  No changes made." }
        default { Write-Err "Invalid choice." }
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Archive App Diagnostic Tool          " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Show-Ports
Show-Docker
Show-Menu

Write-Host ""
