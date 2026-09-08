param(
    [switch]$SkipDockerReset,
    [switch]$SkipPythonSetup,
    [switch]$SkipFrontendInstall,
    [switch]$SkipModelPull,
    [switch]$SkipAlembic
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = $PSScriptRoot
$agentDir = Join-Path $repoRoot 'agent'
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'

function Ensure-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$Hint = ''
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        $message = "Required command '$Name' is not available on PATH."
        if ($Hint) { $message += " $Hint" }
        throw $message
    }
}

function Invoke-Progress {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host ""
    Write-Host '==================================================' -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host '==================================================' -ForegroundColor Cyan
}

function Get-AvailablePort {
    param(
        [int]$StartPort = 4210,
        [int]$MaxAttempts = 20
    )

    for ($port = $StartPort; $port -lt ($StartPort + $MaxAttempts); $port++) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
        try {
            $listener.Start()
            return $port
        }
        catch {
            continue
        }
        finally {
            $listener.Stop()
        }
    }

    throw "No free port found starting from $StartPort."
}

function Start-DevWindow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$CommandText
    )

    $scriptBlock = @"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
Set-Location '$WorkingDirectory'
$CommandText
"@

    Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $scriptBlock) -WorkingDirectory $WorkingDirectory | Out-Null
    Write-Host "Started $Title in a separate terminal window."
}

Ensure-Command -Name 'docker' -Hint 'Docker Desktop or Docker Engine must be installed.'
Ensure-Command -Name 'py' -Hint 'Python launcher required for venv creation.'
Ensure-Command -Name 'node' -Hint 'Node.js must be installed for the frontend.'
Ensure-Command -Name 'npm' -Hint 'npm is required for Angular frontend dependencies.'

if (-not (Test-Path -Path $agentDir -PathType Container)) { throw "Missing directory: $agentDir" }
if (-not (Test-Path -Path $backendDir -PathType Container)) { throw "Missing directory: $backendDir" }
if (-not (Test-Path -Path $frontendDir -PathType Container)) { throw "Missing directory: $frontendDir" }

if (-not $SkipDockerReset) {
    Invoke-Progress 'Resetting Docker services and database volume'
    & docker compose down -v
    if ($LASTEXITCODE -ne 0) { throw 'docker compose down -v failed.' }
}

Invoke-Progress 'Starting Docker services'
& docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose up -d failed.' }

if (-not $SkipModelPull) {
    Invoke-Progress 'Pulling Ollama model gemma3:1b'
    & docker compose exec -T ollama ollama pull gemma3:1b
    if ($LASTEXITCODE -ne 0) { throw 'Failed to pull gemma3:1b via Ollama.' }
}

if (-not $SkipPythonSetup) {
    Invoke-Progress 'Starting agent in a separate terminal'
    $agentCommand = @"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python agent.py --dev
"@
    Start-DevWindow -Title 'Agent' -WorkingDirectory $agentDir -CommandText $agentCommand

    Invoke-Progress 'Starting backend in a separate terminal'
    $backendCommand = @"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download nl_core_news_lg
`$env:DATABASE_URL='postgresql+asyncpg://archiveuser:archivepass@127.0.0.1:5442/modaldb'
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8010
"@
    Start-DevWindow -Title 'Backend' -WorkingDirectory $backendDir -CommandText $backendCommand
}
else {
    Write-Host 'Python setup skipped.'
}

if (-not $SkipFrontendInstall) {
    Invoke-Progress 'Starting frontend in a separate terminal'
    $frontendPort = Get-AvailablePort -StartPort 4210
    Write-Host "Using frontend port $frontendPort (4210 already occupied or unavailable)."

    $frontendCommand = @"
cd '$frontendDir'
npm install
npx ng serve --port $frontendPort --host 0.0.0.0
"@
    Start-DevWindow -Title 'Frontend' -WorkingDirectory $repoRoot -CommandText $frontendCommand
}
else {
    Write-Host 'Frontend install skipped.'
}

if (-not $SkipAlembic) {
    Write-Host ""
    Write-Host 'Alembic command to run once the database is up:' -ForegroundColor Yellow
    Write-Host "cd '$backendDir'" -ForegroundColor Yellow
    Write-Host '.\.venv\Scripts\Activate.ps1' -ForegroundColor Yellow
    Write-Host '$env:DATABASE_URL="postgresql+asyncpg://archiveuser:archivepass@127.0.0.1:5442/modaldb"' -ForegroundColor Yellow
    Write-Host 'python -m alembic upgrade head' -ForegroundColor Yellow
}

Write-Host ""
$frontendUrl = if ($SkipFrontendInstall) { 'skipped' } else { "http://localhost:$frontendPort" }

Write-Host 'Development stack is starting.' -ForegroundColor Green
Write-Host '- Agent terminal window' -ForegroundColor Green
Write-Host '- Backend: http://localhost:8010' -ForegroundColor Green
Write-Host "- Frontend: $frontendUrl" -ForegroundColor Green
Write-Host '- Ollama API: http://localhost:11434' -ForegroundColor Green
Write-Host '- PostgreSQL: localhost:5442' -ForegroundColor Green
Write-Host ""
Write-Host 'Tip: if the agent/backend fails on first start, rerun the script with -SkipDockerReset to avoid resetting the database.' -ForegroundColor Yellow
