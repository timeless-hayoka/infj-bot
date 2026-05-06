#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  check_secrets.sh — Manual secret scanner for INFJ Bot / DRIFT              ║
# ║  Run this before pushing if you bypassed the pre-commit hook.               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

FOUND=0

echo "🔍 Scanning repository for potential secrets..."
echo ""

PATTERNS=(
    'sk-ant-[a-zA-Z0-9]{48,}'
    'sk-proj-[a-zA-Z0-9_-]{40,}'
    'sk-live-[a-zA-Z0-9]{40,}'
    '8f13df41-d7d6-491f-aedf-785fffcaad51'
    'sk-[a-zA-Z0-9]{48,}'
    'AIza[0-9A-Za-z_-]{35,}'
    'Bearer [a-zA-Z0-9_\-]{40,}'
    'AKIA[0-9A-Z]{16}'
    'BEGIN OPENSSH PRIVATE KEY'
    'BEGIN RSA PRIVATE KEY'
)

for pattern in "${PATTERNS[@]}"; do
    MATCHES=$(grep -rnHP "$pattern" --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" --include="*.sh" --include="*.json" --include="*.txt" . 2>/dev/null | grep -v ".git/" | grep -v "venv/" | grep -v "__pycache__/" || true)
    if [ -n "$MATCHES" ]; then
        echo -e "${YELLOW}⚠️  Pattern match:${NC}"
        echo "$MATCHES" | head -n 10
        FOUND=1
    fi
done

# Check for untracked .env files
UNTRACKED_ENV=$(git ls-files --others --exclude-standard | grep -E "^\.env" || true)
if [ -n "$UNTRACKED_ENV" ]; then
    echo -e "${YELLOW}⚠️  Untracked env files found (OK if gitignored):${NC}"
    echo "$UNTRACKED_ENV"
fi

if [ "$FOUND" -eq 0 ]; then
    echo -e "${GREEN}✅ No obvious secrets found in tracked files.${NC}"
else
    echo ""
    echo -e "${RED}❌ Potential secrets detected. Review before pushing.${NC}"
    exit 1
fi
