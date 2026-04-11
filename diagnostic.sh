#!/usr/bin/env bash
# Archive App Diagnostic Tool
# Requires bash 4+ (macOS: install via homebrew — brew install bash)

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

header() { echo -e "\n${BOLD}${CYAN}$1${RESET}"; }
ok()     { echo -e "  ${GREEN}✔${RESET}  $1"; }
warn()   { echo -e "  ${YELLOW}!${RESET}  $1"; }
err()    { echo -e "  ${RED}✘${RESET}  $1"; }

# ---------------------------------------------------------------------------
# Port + image definitions
# ---------------------------------------------------------------------------
declare -A PORT_LABELS=(
    [9090]="Agent"
    [4200]="Frontend"
    [8000]="Backend"
    [9998]="Tika"
    [5432]="Postgres"
)

# Expected Docker image substring for each port (port 9090 is a native process)
declare -A DOCKER_IMAGE_PATTERNS=(
    [4200]="archive-app-frontend"
    [8000]="archive-app-backend"
    [9998]="apache/tika"
    [5432]="postgres"
)

# State populated by check functions, consumed by menu actions
# Values: "free" | "app" | "foreign"
declare -A PORT_STATUS
declare -A PORT_PID        # native PID (port 9090, or foreign processes)
declare -A PORT_PROC       # native process name (port 9090, or foreign)
declare -A PORT_CONTAINER  # Docker container name (app Docker ports)
declare -A PORT_IMAGE      # Docker image (app Docker ports)

# ---------------------------------------------------------------------------
# Detect compose file
# ---------------------------------------------------------------------------
detect_compose_file() {
    if [[ -f "$SCRIPT_DIR/docker-compose.prod.yml" ]]; then
        echo "$SCRIPT_DIR/docker-compose.prod.yml"
    elif [[ -f "$SCRIPT_DIR/docker-compose.yml" ]]; then
        echo "$SCRIPT_DIR/docker-compose.yml"
    else
        echo ""
    fi
}

# Returns "PID PROCNAME" for a TCP LISTEN port, or empty string
lsof_port() {
    lsof -iTCP:"$1" -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR==2 {print $2, $1}'
}

# ---------------------------------------------------------------------------
# Port checks
# ---------------------------------------------------------------------------

# Port 9090 — native process; verify it's archive-agent or python (dev mode)
check_agent_port() {
    local pad="       "
    local lsof_info pid proc
    lsof_info=$(lsof_port 9090)

    if [[ -z "$lsof_info" ]]; then
        PORT_STATUS[9090]="free"
        ok "Port 9090 (Agent):$pad FREE"
        return
    fi

    pid=$(echo "$lsof_info"  | awk '{print $1}')
    proc=$(echo "$lsof_info" | awk '{print $2}')
    PORT_PID[9090]="$pid"
    PORT_PROC[9090]="$proc"

    if echo "$proc" | grep -qiE "^archive-a|^python"; then
        PORT_STATUS[9090]="app"
        ok "Port 9090 (Agent):$pad IN USE by $proc (PID $pid) ${GREEN}✔ App process${RESET}"
    else
        PORT_STATUS[9090]="foreign"
        warn "Port 9090 (Agent):$pad IN USE by $proc (PID $pid) ${YELLOW}⚠ NOT an App process${RESET}"
    fi
}

# Ports 4200/8000/9998/5432 — Docker-managed; verify via docker ps image match
check_docker_port() {
    local port=$1
    local label="${PORT_LABELS[$port]}"
    local image_pattern="${DOCKER_IMAGE_PATTERNS[$port]}"
    local pad
    pad=$(printf '%*s' $((12 - ${#label})) '')

    # Look for a running container whose image matches the expected pattern
    local container_line img name
    container_line=$(docker ps --format $'{{.Image}}\t{{.Names}}' 2>/dev/null \
                     | grep "$image_pattern" | head -1 || true)

    if [[ -n "$container_line" ]]; then
        img=$(echo "$container_line"  | cut -f1)
        name=$(echo "$container_line" | cut -f2)
        PORT_STATUS[$port]="app"
        PORT_CONTAINER[$port]="$name"
        PORT_IMAGE[$port]="$img"
        ok "Port $port ($label):$pad IN USE by $name [$img] ${GREEN}✔ App process${RESET}"
        return
    fi

    # No matching container — fall back to lsof to detect any foreign occupant
    local lsof_info pid proc
    lsof_info=$(lsof_port "$port")

    if [[ -n "$lsof_info" ]]; then
        pid=$(echo "$lsof_info"  | awk '{print $1}')
        proc=$(echo "$lsof_info" | awk '{print $2}')
        PORT_STATUS[$port]="foreign"
        PORT_PID[$port]="$pid"
        PORT_PROC[$port]="$proc"
        warn "Port $port ($label):$pad IN USE by $proc (PID $pid) ${YELLOW}⚠ NOT an App process${RESET}"
    else
        PORT_STATUS[$port]="free"
        ok "Port $port ($label):$pad FREE"
    fi
}

print_ports() {
    header "Port Status"
    check_agent_port
    for port in 4200 8000 9998 5432; do
        check_docker_port "$port"
    done
}

# ---------------------------------------------------------------------------
# Docker status
# ---------------------------------------------------------------------------
print_docker() {
    header "Docker"

    if ! docker info &>/dev/null; then
        err "Docker: Not running"
        return
    fi
    ok "Docker: Running"

    local compose_file
    compose_file=$(detect_compose_file)
    if [[ -z "$compose_file" ]]; then
        warn "No docker-compose file found in $SCRIPT_DIR"
        return
    fi

    echo -e "  Compose file: ${CYAN}$compose_file${RESET}"
    echo ""

    local ps_output
    ps_output=$(docker compose -f "$compose_file" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || true)
    local line_count
    line_count=$(echo "$ps_output" | wc -l)

    if [[ -z "$ps_output" ]] || [[ $line_count -le 1 ]]; then
        warn "No containers found for this compose file"
    else
        echo "$ps_output" | while IFS= read -r line; do
            echo "    $line"
        done
    fi
}

# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------
confirm() {
    echo -e "\n  ${YELLOW}$1${RESET}"
    read -r -p "  Continue? (y/n): " answer
    [[ "$answer" == "y" || "$answer" == "Y" ]]
}

kill_agent() {
    local status="${PORT_STATUS[9090]:-free}"

    if [[ "$status" == "free" ]]; then
        warn "Nothing running on port 9090 (Agent)"
        return
    fi

    local pid="${PORT_PID[9090]}"
    local proc="${PORT_PROC[9090]}"

    if [[ "$status" == "foreign" ]]; then
        if confirm "Port 9090 is used by $proc (PID $pid), which is NOT part of Archive App. Are you sure you want to stop it?"; then
            kill "$pid" 2>/dev/null && ok "Stopped $proc (PID $pid)" || err "Failed to kill PID $pid"
        else
            warn "Skipped port 9090"
        fi
    else
        if confirm "This will stop: $proc (PID $pid) on port 9090 (Agent)."; then
            kill "$pid" 2>/dev/null && ok "Stopped $proc (PID $pid)" || err "Failed to kill PID $pid"
        else
            warn "Skipped port 9090"
        fi
    fi
}

docker_down() {
    local compose_file
    compose_file=$(detect_compose_file)
    if [[ -z "$compose_file" ]]; then
        err "No docker-compose file found — cannot run docker compose down"
        return
    fi
    if confirm "This will run: docker compose down (using $compose_file)."; then
        docker compose -f "$compose_file" down && ok "Docker services stopped" || err "docker compose down failed"
    else
        warn "Skipped Docker shutdown"
    fi
}

stop_everything() {
    docker_down
    kill_agent
}

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
show_menu() {
    header "Actions"
    echo "  a) Stop everything (docker compose down + stop agent)"
    echo "  b) Stop Docker services only (docker compose down)"
    echo "  c) Stop agent only (port 9090)"
    echo "  d) Exit without changes"
    echo ""
    read -r -p "  Choose [a/b/c/d]: " choice
    case "$choice" in
        a|A) stop_everything ;;
        b|B) docker_down ;;
        c|C) kill_agent ;;
        d|D) echo -e "\n  No changes made." ;;
        *)   echo -e "\n  ${RED}Invalid choice.${RESET}" ;;
    esac
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Archive App Diagnostic Tool        ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"

print_ports
print_docker

# Summary: if everything is free, say so and skip the menu
all_free=true
for port in 9090 4200 8000 9998 5432; do
    if [[ "${PORT_STATUS[$port]:-free}" != "free" ]]; then
        all_free=false
        break
    fi
done

if $all_free; then
    echo ""
    ok "${GREEN}All ports are free. No running Archive App processes found."
    ok "The application can be started without problem.${RESET}"
    echo ""
    exit 0
fi

show_menu

echo ""
