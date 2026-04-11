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

# Expected Docker image substrings per port
$DockerImagePatterns = @{
    4200 = "archive-app-frontend"
    8000 = "archive-app-backend"
    9998 = "apache/tika"
    5432 = "postgres"
}

$PortLabels = @{
    9090 = "Agent"
    4200 = "Frontend"
    8000 = "Backend"
    9998 = "Tika"
    5432 = "Postgres"
}

# State populated by check functions, consumed by menu actions
# Values: "free" | "app" | "foreign"
$PortStatus    = @{}
$PortPid       = @{}
$PortProc      = @{}
$PortContainer = @{}
$PortImage     = @{}

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
# Get PID + process name listening on a port via netstat
# ---------------------------------------------------------------------------
function Get-LsofPort($port) {
    $lines = netstat -ano 2>$null | Select-String "TCP\s+\S+:$port\s+\S+\s+LISTENING"
    if (-not $lines) { return $null }
    $pid = ($lines[0].ToString() -split '\s+')[-1]
    if (-not $pid -or $pid -eq '0') { return $null }
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    return [PSCustomObject]@{
        Pid  = $pid
        Name = if ($proc) { $proc.Name } else { "unknown" }
    }
}

# ---------------------------------------------------------------------------
# Port checks
# ---------------------------------------------------------------------------

# Port 9090 — native process; verify it's archive-agent or python (dev mode)
function Check-AgentPort {
    $pad = "       "
    $info = Get-LsofPort 9090

    if (-not $info) {
        $PortStatus[9090] = "free"
        Write-Ok "Port 9090 (Agent):$pad FREE"
        return
    }

    $PortPid[9090]  = $info.Pid
    $PortProc[9090] = $info.Name

    if ($info.Name -match "archive-agent|python") {
        $PortStatus[9090] = "app"
        Write-Ok "Port 9090 (Agent):$pad IN USE by $($info.Name) (PID $($info.Pid)) [App process]"
    } else {
        $PortStatus[9090] = "foreign"
        Write-Warn "Port 9090 (Agent):$pad IN USE by $($info.Name) (PID $($info.Pid)) [NOT an App process]"
    }
}

# Ports 4200/8000/9998/5432 — Docker-managed; verify via docker ps image match
function Check-DockerPort($port) {
    $label   = $PortLabels[$port]
    $pattern = $DockerImagePatterns[$port]
    $pad     = " " * (12 - $label.Length)

    # Look for a running container whose image matches the expected pattern
    $containerLine = docker ps --format "{{.Image}}`t{{.Names}}" 2>$null |
                     Where-Object { $_ -match [regex]::Escape($pattern) } |
                     Select-Object -First 1

    if ($containerLine) {
        $parts = $containerLine -split "`t"
        $img   = $parts[0]
        $name  = $parts[1]
        $PortStatus[$port]    = "app"
        $PortContainer[$port] = $name
        $PortImage[$port]     = $img
        Write-Ok "Port $port ($label):$pad IN USE by $name [$img] [App process]"
        return
    }

    # No matching container — fall back to netstat for foreign occupants
    $info = Get-LsofPort $port
    if ($info) {
        $PortStatus[$port] = "foreign"
        $PortPid[$port]    = $info.Pid
        $PortProc[$port]   = $info.Name
        Write-Warn "Port $port ($label):$pad IN USE by $($info.Name) (PID $($info.Pid)) [NOT an App process]"
    } else {
        $PortStatus[$port] = "free"
        Write-Ok "Port $port ($label):$pad FREE"
    }
}

function Show-Ports {
    Write-Header "Port Status"
    Check-AgentPort
    foreach ($port in 4200, 8000, 9998, 5432) {
        Check-DockerPort $port
    }
}

# ---------------------------------------------------------------------------
# Docker status
# ---------------------------------------------------------------------------
function Show-Docker {
    Write-Header "Docker"

    docker info 2>&1 | Out-Null
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
    $dataLines = $ps | Where-Object { $_ -notmatch "^NAME" -and $_.Trim() -ne "" }
    if (-not $dataLines) {
        Write-Warn "No containers found for this compose file"
    } else {
        $ps | ForEach-Object { Write-Host "    $_" }
    }
}

# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------
function Confirm-Action($msg) {
    Write-Host ""
    Write-Host "  $msg" -ForegroundColor Yellow
    $answer = Read-Host "  Continue? (y/n)"
    return ($answer -eq 'y' -or $answer -eq 'Y')
}

function Stop-Agent {
    $status = $PortStatus[9090]

    if ($status -eq "free" -or -not $status) {
        Write-Warn "Nothing running on port 9090 (Agent)"
        return
    }

    $pid  = $PortPid[9090]
    $proc = $PortProc[9090]

    if ($status -eq "foreign") {
        $msg = "Port 9090 is used by $proc (PID $pid), which is NOT part of Archive App. Are you sure you want to stop it?"
    } else {
        $msg = "This will stop: $proc (PID $pid) on port 9090 (Agent)."
    }

    if (Confirm-Action $msg) {
        taskkill /PID $pid /F | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Stopped $proc (PID $pid)"
        } else {
            Write-Err "Failed to stop PID $pid"
        }
    } else {
        Write-Warn "Skipped port 9090"
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
    Stop-DockerServices
    Stop-Agent
}

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
function Show-Menu {
    Write-Header "Actions"
    Write-Host "  a) Stop everything (docker compose down + stop agent)"
    Write-Host "  b) Stop Docker services only (docker compose down)"
    Write-Host "  c) Stop agent only (port 9090)"
    Write-Host "  d) Exit without changes"
    Write-Host ""
    $choice = Read-Host "  Choose [a/b/c/d]"
    switch ($choice.ToLower()) {
        'a' { Stop-Everything }
        'b' { Stop-DockerServices }
        'c' { Stop-Agent }
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
