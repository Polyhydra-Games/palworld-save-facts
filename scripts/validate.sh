#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_command="${PYTHON:-python}"
if [[ -z "${PYTHON:-}" && -x "$repo_root/.venv/bin/python" ]]; then
  python_command="$repo_root/.venv/bin/python"
fi

"$python_command" -m compileall -q src scripts
"$python_command" -m pytest -q
