#!/bin/bash
# ============================================================
# connect-gemini.sh — Ensure Chrome daemon is ready for multiagent
#
# Chrome生命周期由 start-chrome-debug.sh (Playwright daemon) 管理。
# 本脚本不预开tab — multiagent pipeline 通过 CDP 按需管理。
#
# P0 security fix (2026-06-29): replaced `source .env` with safe parser.
#
# Environment variables:
#   CDP_PORT       (default: 9222)
#   FORCE_FRESH    1 = 强制关闭所有旧 Gemini tab 并新建
#
# Usage:
#   bash connect-gemini.sh
#   FORCE_FRESH=1 bash connect-gemini.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- Safe .env loader (P0 fix: NO source — see start-chrome-debug.sh) ----
_safe_load_env() {
    local env_file="$1"
    if [ ! -f "$env_file" ]; then return 0; fi
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        if [[ ! "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then continue; fi
        case "$key" in
            PATH|PYTHONPATH|LD_PRELOAD|LD_LIBRARY_PATH|PYTHONSTARTUP|BASH_ENV|PROMPT_COMMAND)
                continue ;;
        esac
        value="${value#\"}"; value="${value%\"}"
        value="${value#\'}"; value="${value%\'}"
        export "$key=$value"
    done < "$env_file"
}

if [ -f "$PROJECT_DIR/.env" ]; then
    _safe_load_env "$PROJECT_DIR/.env"
fi

# ---- Config ----
CDP_PORT="${CDP_PORT:-9222}"
FORCE_FRESH="${FORCE_FRESH:-0}"
START_SCRIPT="$SCRIPT_DIR/start-chrome-debug.sh"

# ---- Ensure Chrome is running ----
echo "[1/2] Ensuring Chrome daemon is running..."
bash "$START_SCRIPT"

# ---- Chrome daemon handles tab lifecycle ----
# Multiagent pipeline opens tabs via CDP when needed.
# No pre-opened Gemini tab required.
echo "[2/2] Chrome daemon ready — tabs managed by multiagent pipeline"
echo "✅ Chrome ready (no pre-opened tabs)"
