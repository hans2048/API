#!/bin/bash
set -euo pipefail

# 원격(웹) 환경에서만 실행
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

pip install -r "$CLAUDE_PROJECT_DIR/requirements.txt" --quiet
