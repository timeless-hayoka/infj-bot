#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  DRIFT Continuous Mode — Production launcher                                ║
# ║  start | stop | restart | status | logs                                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# ── Config ──────────────────────────────────────────────────────────
PID_FILE="${PROJECT_ROOT}/drift.pid"
LOG_FILE="${PROJECT_ROOT}/logs/drift_continuous.log"
MAIN_SCRIPT="${PROJECT_ROOT}/main.py"
ENV_FILE="${PROJECT_ROOT}/.env"
VENV_ACTIVATE="${PROJECT_ROOT}/venv/bin/activate"

# Critical: preserve PYTHONPATH for infj_bot imports
export PYTHONPATH="/home/crexs:/home/crexs/infj_bot/core:${PYTHONPATH:-}"

# ── Helpers ─────────────────────────────────────────────────────────
ensure_dirs() {
    mkdir -p "${PROJECT_ROOT}/logs"
}

is_running() {
    local pid
    if [[ -f "$PID_FILE" ]]; then
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

cleanup_stale_pid() {
    if [[ -f "$PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [[ -n "$old_pid" ]] && ! ps -p "$old_pid" > /dev/null 2>&1; then
            echo "🧹 Cleaning stale PID file (PID $old_pid is gone)..."
            rm -f "$PID_FILE"
        fi
    fi
}

start_bot() {
    ensure_dirs
    cleanup_stale_pid

    if is_running; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null)
        echo "❌ DRIFT is already running (PID: $pid). Use: $0 restart"
        exit 1
    fi

    # Activate virtual environment if present
    if [[ -f "$VENV_ACTIVATE" ]]; then
        # shellcheck source=/dev/null
        source "$VENV_ACTIVATE"
    else
        echo "⚠️  Virtual environment not found at $VENV_ACTIVATE"
        echo "   Attempting to use system Python..."
    fi

    echo "🚀 Starting DRIFT in Continuous Mode..."
    echo "   Log: $LOG_FILE"

    # Rotate log if it's getting large (>10MB)
    if [[ -f "$LOG_FILE" ]] && [[ $(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0) -gt 10485760 ]]; then
        mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d_%H%M%S).old"
        echo "📦 Rotated old log file"
    fi

    nohup python "$MAIN_SCRIPT" >> "$LOG_FILE" 2>&1 &
    local new_pid=$!

    # Wait briefly to confirm it started
    sleep 1
    if ps -p "$new_pid" > /dev/null 2>&1; then
        echo "$new_pid" > "$PID_FILE"
        echo "✅ DRIFT started — PID: $new_pid"
        echo "📍 Watch logs:   tail -f $LOG_FILE"
        echo "🔄 Restart:      $0 restart"
        echo "⛔ Stop:         $0 stop"
        echo "📊 Status:       $0 status"
    else
        echo "❌ Failed to start DRIFT. Check logs:"
        tail -n 20 "$LOG_FILE" 2>/dev/null || true
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop_bot() {
    if ! is_running; then
        cleanup_stale_pid
        echo "🛑 DRIFT is not running."
        return 0
    fi

    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null)
    echo "🛑 Stopping DRIFT (PID: $pid)..."

    # Graceful shutdown first
    kill -TERM "$pid" 2>/dev/null
    sleep 2

    # Force kill if still alive
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "⚠️  Graceful shutdown timed out. Force killing..."
        kill -KILL "$pid" 2>/dev/null
        sleep 1
    fi

    cleanup_stale_pid
    echo "✅ DRIFT stopped."
}

restart_bot() {
    echo "🔄 Restarting DRIFT..."
    stop_bot
    sleep 2
    start_bot
}

show_status() {
    if is_running; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null)
        echo "📊 DRIFT is RUNNING (PID: $pid)"
        echo "   Log:   $LOG_FILE"
        echo "   Uptime: $(ps -o etime= -p "$pid" 2>/dev/null || echo 'unknown')"
        echo "   Memory: $(ps -o rss= -p "$pid" 2>/dev/null | awk '{print int($1/1024)"MB"}' || echo 'unknown')"
    else
        cleanup_stale_pid
        echo "📊 DRIFT is NOT running."
        echo "   Start with: $0 start"
    fi
}

show_logs() {
    if [[ -f "$LOG_FILE" ]]; then
        tail -n 50 -f "$LOG_FILE"
    else
        echo "No log file found at $LOG_FILE"
    fi
}

# ── Main dispatch ───────────────────────────────────────────────────
case "${1:-start}" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
