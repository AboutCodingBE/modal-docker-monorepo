#!/usr/bin/env bash
# Archive App Diagnostic Tool

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

# ---------------------------------------------------------------------------
# Port check — returns "PID:PROCESS" or empty string
# ---------------------------------------------------------------------------
port_info() {
    local port=$1
    local info
    info=$(lsof -iTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR==2 {print $2, $1}')
    echo "$info"
}

# ---------------------------------------------------------------------------
# Section 1 — Port status
# ---------------------------------------------------------------------------
print_ports() {
    header "Port Status"
    declare -A PORT_LABELS=( [9090]="Agent" [4200]="Frontend" [8000]="Backend" [9998]="Tika" [5432]="Postgres" )
    for port in 9090 4200 8000 9998 5432; do
        label="${PORT_LABELS[$port]}"
        info=$(port_info "$port")
        if [[ -n "$info" ]]; then
            pid=$(echo "$info" | awk '{print $1}')
            proc=$(echo "$info" | awk '{print $2}')
            warn "Port $port ($label):$(printf '%*s' $((12 - ${#label})) '') IN USE by $proc (PID $pid)"
        else
            ok "Port $port ($label):$(printf '%*s' $((12 - ${#label})) '') FREE"
        fi
    done
}

# ---------------------------------------------------------------------------
# Section 2 — Docker status
# ---------------------------------------------------------------------------
print_docker() {
    header "Docker"
    if docker info &>/dev/null; then
        ok "Docker: Running"
    else
        err "Docker: Not running"
        return
    fi

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
    if [[ -z "$ps_output" ]] || [[ "$ps_output" == NAME* && $(echo "$ps_output" | wc -l) -le 1 ]]; then
        warn "No containers found for this compose file"
    else
        echo "$ps_output" | while IFS= read -r line; do
            echo "    $line"
        done
    fi
}

# ---------------------------------------------------------------------------
# Section 3 — Action menu
# ---------------------------------------------------------------------------
confirm() {
    local msg=$1
    echo -e "\n  ${YELLOW}$msg${RESET}"
    read -r -p "  Continue? (y/n): " answer
    [[ "$answer" == "y" || "$answer" == "Y" ]]
}

kill_port() {
    local port=$1
    local label=$2
    local info
    info=$(port_info "$port")
    if [[ -z "$info" ]]; then
        warn "Nothing running on port $port ($label)"
        return
    fi
    local pid proc
    pid=$(echo "$info" | awk '{print $1}')
    proc=$(echo "$info" | awk '{print $2}')
    if confirm "This will stop: $proc (PID $pid) on port $port ($label)."; then
        kill "$pid" 2>/dev/null && ok "Stopped $proc (PID $pid)" || err "Failed to kill PID $pid"
    else
        warn "Skipped port $port"
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
    for port in 4200 8000 9998 5432; do
        declare -A LABELS=( [4200]="Frontend" [8000]="Backend" [9998]="Tika" [5432]="Postgres" )
        kill_port "$port" "${LABELS[$port]}"
    done
    docker_down
    kill_port 9090 "Agent"
}

show_menu() {
    header "Actions"
    echo "  a) Stop everything (all ports + docker compose down)"
    echo "  b) Stop Docker services only (docker compose down)"
    echo "  c) Stop agent only (port 9090)"
    echo "  d) Exit without changes"
    echo ""
    read -r -p "  Choose [a/b/c/d]: " choice
    case "$choice" in
        a|A) stop_everything ;;
        b|B) docker_down ;;
        c|C) kill_port 9090 "Agent" ;;
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
show_menu

echo ""
