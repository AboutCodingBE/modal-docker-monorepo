#!/usr/bin/env bash
# freeze-check.sh
#
# Read-only diagnostics for an analysis that looks frozen.
# Run it WHILE it is frozen, before you restart anything:
#
#     chmod +x freeze-check.sh && ./freeze-check.sh
#
# It writes a report folder (freeze-report-<time>/) and a .tgz of it next to where you run it.
# The only thing it sends anywhere is one tiny request to Ollama. It does not stop, restart or
# change anything.
#
# Logs can contain file names or text from your documents. Look at them before sharing.
#
# Optional settings (environment variables), shown with their defaults:
#   OLLAMA_URL=http://localhost:11434
#   OLLAMA_MODEL=gemma3:1b
#   OLLAMA_URL_FROM_CONTAINER=http://host.docker.internal:11434
#   AGENT_URL=http://localhost:9090
#   TIKA_URL=http://localhost:9998
#   BACKEND_CONTAINER=   (auto: first container with "backend" in its name or image)
#   DB_CONTAINER=        (auto: first container with "postgres" in its name or image)
#   LOG_SINCE=60m        (how far back to collect container logs)
#   SAMPLE_SECONDS=30    (how long to watch whether the result counters move; 0 = skip)

OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3:1b}"
OLLAMA_URL_FROM_CONTAINER="${OLLAMA_URL_FROM_CONTAINER:-http://host.docker.internal:11434}"
AGENT_URL="${AGENT_URL:-http://localhost:9090}"
TIKA_URL="${TIKA_URL:-http://localhost:9998}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-}"
DB_CONTAINER="${DB_CONTAINER:-}"
LOG_SINCE="${LOG_SINCE:-60m}"
SAMPLE_SECONDS="${SAMPLE_SECONDS:-30}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="freeze-report-$STAMP"
mkdir -p "$OUT/logs"
REPORT="$OUT/report.txt"

hr()   { printf '\n==== %s ====\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# run_t SECONDS command...  : run a command, kill it if it takes longer than SECONDS
run_t() {
  secs="$1"; shift
  "$@" &
  pid=$!
  ( sleep "$secs"; kill -9 "$pid" 2>/dev/null ) >/dev/null 2>&1 &
  watcher=$!
  wait "$pid" 2>/dev/null
  rc=$?
  kill "$watcher" 2>/dev/null
  wait "$watcher" 2>/dev/null
  if [ "$rc" -eq 137 ]; then echo "(timed out after ${secs}s)"; fi
  return "$rc"
}

# detect PATTERN : first running container whose name or image matches
detect() {
  docker ps --format '{{.Names}}|{{.Image}}' 2>/dev/null | grep -i "$1" | head -1 | cut -d'|' -f1
}

main() {
  echo "MODAL freeze check, started $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "report folder: $OUT"

  hr "1. Machine"
  uname -a
  uptime
  df -h . | tail -2
  if have vm_stat; then vm_stat | head -6; elif have free; then free -m; fi

  hr "2. Sleep / wake history and power"
  if have pmset; then
    echo "-- last sleep/wake events (newest last)"
    pmset -g log 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]+ [+-][0-9]{4} (Sleep|Wake|DarkWake) ' | tail -12
    echo "-- battery / power source"
    pmset -g batt
    echo "-- what currently prevents sleep"
    pmset -g assertions | head -25
  elif have journalctl; then
    echo "-- suspend/resume entries this boot"
    journalctl -b --no-pager 2>/dev/null | grep -iE 'suspend|resume|sleep' | tail -12
  else
    echo "(no sleep/wake source found on this OS)"
  fi

  hr "3. Docker"
  BACKEND="$BACKEND_CONTAINER"
  DB="$DB_CONTAINER"
  DOCKER_OK=0
  if have docker && run_t 10 docker ps -q >/dev/null 2>&1; then
    DOCKER_OK=1
  else
    echo "Docker did not answer within 10 s (not installed, daemon down, or hung). That is a finding."
  fi

  if [ "$DOCKER_OK" -eq 1 ]; then
    [ -z "$BACKEND" ] && BACKEND="$(detect backend)"
    [ -z "$DB" ] && DB="$(detect postgres)"
    echo "backend container: ${BACKEND:-not found}"
    echo "database container: ${DB:-not found}"
    echo
    echo "-- containers"
    docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
    echo
    echo "-- state per container (look for recent start times, restarts, oomkilled=true)"
    for c in $(docker ps -a --format '{{.Names}}'); do
      docker inspect -f '{{.Name}}  status={{.State.Status}}  started={{.State.StartedAt}}  restarts={{.RestartCount}}  oomkilled={{.State.OOMKilled}}  exitcode={{.State.ExitCode}}' "$c" 2>&1
    done
    echo
    echo "-- cpu / memory right now (a stuck run usually shows ~0% cpu in the backend)"
    run_t 25 docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
  fi

  hr "4. Container logs (last $LOG_SINCE, saved in $OUT/logs/)"
  if [ "$DOCKER_OK" -eq 1 ]; then
    for c in $(docker ps -a --format '{{.Names}}'); do
      run_t 30 docker logs --since "$LOG_SINCE" --tail 500 "$c" > "$OUT/logs/$c.log" 2>&1
      lines=$(wc -l < "$OUT/logs/$c.log" | tr -d ' ')
      echo
      echo "-- $c: $lines lines. Last 3:"
      tail -3 "$OUT/logs/$c.log"
      echo "   error-like lines (last 8):"
      grep -iE 'error|exception|traceback|timeout|timed out|killed|out of memory' "$OUT/logs/$c.log" | tail -8
    done
    if [ -n "$BACKEND" ]; then
      echo
      echo "-- backend ($BACKEND): last 25 lines"
      tail -25 "$OUT/logs/$BACKEND.log"
    fi
  else
    echo "(skipped, docker not available)"
  fi

  hr "5. Ollama"
  echo "-- server answers? (expect: Ollama is running)"
  curl -s --max-time 5 "$OLLAMA_URL/" || echo "no answer from $OLLAMA_URL"
  echo
  if have ollama; then
    echo "-- models loaded right now (empty after a long idle is normal)"
    run_t 10 ollama ps
    echo "-- installed models"
    run_t 10 ollama list | head -15
  else
    echo "(ollama command not found on this machine)"
  fi
  echo "-- generate test with $OLLAMA_MODEL (max 90 s; first call after idle can be slow)"
  curl -s --max-time 90 -o /dev/null -w "HTTP %{http_code}, %{time_total}s\n" "$OLLAMA_URL/api/generate" \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"prompt\":\"Zeg hallo\",\"stream\":false}"
  echo "-- ollama processes"
  ps aux | grep -i "[o]llama" | awk '{printf "cpu=%s%% mem=%s%% %s\n", $3, $4, $11}'
  if [ "$DOCKER_OK" -eq 1 ] && [ -n "$BACKEND" ]; then
    echo "-- can the backend container reach Ollama? ($OLLAMA_URL_FROM_CONTAINER)"
    run_t 20 docker exec "$BACKEND" python -c "import urllib.request,time; t=time.time(); r=urllib.request.urlopen('$OLLAMA_URL_FROM_CONTAINER/', timeout=10); print('HTTP', r.status, round(time.time()-t,2), 's')" 2>&1 | tail -3
  fi

  hr "6. Agent and Tika"
  echo "-- agent ($AGENT_URL)"
  curl -s --max-time 5 -o /dev/null -w "HTTP %{http_code}, %{time_total}s\n" "$AGENT_URL/export/default-path"
  echo "-- tika ($TIKA_URL) (may only be reachable inside Docker, then 000 is fine)"
  curl -s --max-time 5 -o /dev/null -w "HTTP %{http_code}, %{time_total}s\n" "$TIKA_URL/tika"

  hr "7. Database"
  if [ "$DOCKER_OK" -eq 1 ] && [ -n "$DB" ]; then
    DBU="$(docker exec "$DB" printenv POSTGRES_USER 2>/dev/null)"; DBU="${DBU:-postgres}"
    DBN="$(docker exec "$DB" printenv POSTGRES_DB 2>/dev/null)";   DBN="${DBN:-$DBU}"
    echo "using user=$DBU database=$DBN in $DB"

    q() { run_t 20 docker exec "$DB" psql -U "$DBU" -d "$DBN" -X -P pager=off -A -F ' | ' -c "$1" 2>&1; }

    echo
    echo "-- 10 newest analyses"
    q "SELECT * FROM archive_analysis ORDER BY analyzed_at DESC LIMIT 10;"
    echo
    echo "-- analyses still STARTED, and for how long"
    q "SELECT *, now() - analyzed_at AS age FROM archive_analysis WHERE status = 'STARTED';"
    echo
    echo "-- database connections (look for 'idle in transaction' or a long time in one state)"
    q "SELECT pid, state, wait_event_type, wait_event, now() - state_change AS in_state_for, left(query, 70) AS query FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();"
    echo
    echo "-- task / progress tables (newest 10 rows each)"
    tables=$(run_t 15 docker exec "$DB" psql -U "$DBU" -d "$DBN" -X -A -t -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND (table_name ILIKE '%task%' OR table_name ILIKE '%progress%');" 2>/dev/null)
    if [ -z "$tables" ]; then echo "(none found)"; fi
    for t in $tables; do
      echo "-- $t"
      q "SELECT * FROM \"$t\" ORDER BY ctid DESC LIMIT 10;"
    done

    count_of() {
      out=$(run_t 15 docker exec "$DB" psql -U "$DBU" -d "$DBN" -X -A -t -c "SELECT count(*) FROM \"$1\";" 2>/dev/null)
      case "$out" in ''|*[!0-9]*) echo "n/a" ;; *) echo "$out" ;; esac
    }
    snapshot() { echo "summary=$(count_of summary) ner=$(count_of ner) topic_detection=$(count_of topic_detection)"; }

    hr "8. Are results still being written?"
    s1="$(snapshot)"
    echo "now:        $s1"
    if [ "$SAMPLE_SECONDS" -gt 0 ]; then
      echo "waiting ${SAMPLE_SECONDS}s ..."
      sleep "$SAMPLE_SECONDS"
      s2="$(snapshot)"
      echo "after ${SAMPLE_SECONDS}s: $s2"
      if [ "$s1" = "$s2" ]; then
        echo "RESULT: no change. If an analysis is supposed to be running, it is stuck."
      else
        echo "RESULT: counters moved, results are still being written."
      fi
      echo "(n/a means that table name was not found; the table names are a guess)"
    else
      echo "(sampling skipped, SAMPLE_SECONDS=0)"
    fi
  else
    echo "(skipped, database container not found; set DB_CONTAINER=<name>)"
  fi

  hr "Reading guide"
  cat <<'GUIDE'
- A container with a recent start time or restarts>0:  that container restarted. Check its log.
- oomkilled=true:                                       a container ran out of memory.
- Ollama generate test slow or failing:                 Ollama is the problem.
- Host reaches Ollama, backend container does not:      Docker networking after sleep.
- Counters not moving + backend cpu ~0% + status STARTED:  the task is waiting on a dead connection,
                                                        or it died without recording a failure.
- A database connection 'idle in transaction' for long:  something holds a transaction open.
- Sleep/wake events right before the freeze:             sleep is a suspect; compare the times.
GUIDE
}

main 2>&1 | tee "$REPORT"

tar czf "$OUT.tgz" "$OUT" 2>/dev/null
echo
echo "Saved: $OUT/report.txt and $OUT.tgz"