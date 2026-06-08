#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  DRIFT Full Test Suite — Intensive Validation Runner                         ║
# ║  Logs everything to logs/test_suite_YYYYMMDD_HHMMSS/ for post-study         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
set -euo pipefail

cd "$(dirname "$0")"
export INFJ_DATA_DIR="${INFJ_DATA_DIR:-$(pwd)/data}"
source venv/bin/activate

RUN_ID=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/test_suite_${RUN_ID}"
mkdir -p "${LOG_DIR}"

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "  DRIFT FULL TEST SUITE — Run ID: ${RUN_ID}"
echo "  Log directory: ${LOG_DIR}"
echo "  Started: $(date -Iseconds)"
echo "═══════════════════════════════════════════════════════════════════════════════"

# ── Helper: run a step with logging ──
run_step() {
    local name="$1"
    local cmd="$2"
    local logfile="${LOG_DIR}/$(echo "$name" | tr ' ' '_').log"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  STEP: ${name}"
    echo "  Command: ${cmd}"
    echo "  Log: ${logfile}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if eval "${cmd}" > "${logfile}" 2>&1; then
        echo "  ✅ PASS"
        echo "${name}|PASS|0" >> "${LOG_DIR}/summary.tsv"
    else
        echo "  ❌ FAIL (exit code $?)"
        echo "${name}|FAIL|$?" >> "${LOG_DIR}/summary.tsv"
    fi
    echo "  Finished: $(date -Iseconds)"
}

# ── Step 1: Syntax check all modified/new Python files ──
run_step "syntax_check" "
  find . -path ./venv -prune -o -name '*.py' -print | \
  while read f; do python3 -m py_compile \"\$f\" 2>&1 || echo \"SYNTAX_ERROR: \$f\"; done
"

# ── Step 2: Unit tests (fast, no API calls) ──
run_step "unit_tests" "python3 -m pytest tests/ -q --tb=short"

# ── Step 3: Consistency eval ──
run_step "consistency_eval" "python3 -m evals.consistency_eval"

# ── Step 4: Mode discrimination eval ──
run_step "mode_discrimination" "python3 -m evals.mode_discrimination"

# ── Step 5: Self-modify audit ──
run_step "self_modify_audit" "python3 -m evals.self_modify_audit"

# ── Step 6: Health check (offline + live if keys present) ──
if [[ -n "${GEMINI_API_KEY:-}" || -n "${API_KEY:-}" ]]; then
    run_step "health_check_live" "LIVE_API_CHECK=1 bash scripts/health_check.sh"
else
    run_step "health_check_offline" "bash scripts/health_check.sh"
fi

# ── Step 7: DMU audit (verifyArchitecture.py) ──
run_step "dmu_pedi_audit" "python3 verify_architecture.py"

# ── Step 8: Start API, run conversational validation, stop API ──
run_step "api_conversational_validation" "
  export \$(grep -v '^#' .env | xargs -d '\\n') && \
  python3 -m uvicorn interfaces.api:app --host 127.0.0.1 --port 8765 --no-access-log &
  API_PID=\$! && sleep 6 && \
  curl -sf http://127.0.0.1:8765/api/health > /dev/null && \
  python3 validate.py --cycles 10 --mode conversational --delay 2 && \
  kill \$API_PID 2>/dev/null || true
"

# ── Step 9: Start API, run mini stress validation, stop API ──
run_step "api_stress_validation" "
  export \$(grep -v '^#' .env | xargs -d '\\n') && \
  python3 -m uvicorn interfaces.api:app --host 127.0.0.1 --port 8765 --no-access-log &
  API_PID=\$! && sleep 6 && \
  curl -sf http://127.0.0.1:8765/api/health > /dev/null && \
  python3 validate.py --cycles 5 --mode stress && \
  kill \$API_PID 2>/dev/null || true
"

# ── Summary ──
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "  TEST SUITE COMPLETE"
echo "  Finished: $(date -Iseconds)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Results:"
cat "${LOG_DIR}/summary.tsv" | column -t -s'|'
echo ""
echo "All logs saved to: ${LOG_DIR}"
