#!/usr/bin/env bash
# Copy the live-bridge plug-in into the VM account's abaqus_plugins folder (idempotent).
# usage: vm/install-live-plugin.sh [--dry-run]
# Reads ssh_host and state_dir from config.local.toml (override: $ABAQUS_MCP_CONFIG) through
# `python -m abaqus_mcp.config --print`. Restart CAE afterwards.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
eval "$(uv run --directory "$HERE/.." python -m abaqus_mcp.config --print)"
HOST="$SSH_HOST"
FILES=(mcp_live_plugin.py mcp_live_core.py mcp_live_kernel.py)
if [[ "${1:-}" == "--dry-run" ]]; then echo "would install ${FILES[*]} on $HOST"; exit 0; fi
DEST='$env:USERPROFILE\abaqus_plugins\mcp_live'
ssh -F "$STATE_DIR/ssh_config" -o BatchMode=yes "$HOST" "New-Item -ItemType Directory -Force -Path \"$DEST\" | Out-Null; foreach (\$d in 'inbox','outbox','log') { New-Item -ItemType Directory -Force -Path \"C:\\abaqus-work\\live\\\$d\" | Out-Null }"
for f in "${FILES[@]}"; do scp -q -F "$STATE_DIR/ssh_config" -o BatchMode=yes "$HERE/plugin/$f" "$HOST:abaqus_plugins/mcp_live/$f"; done
echo "installed ${FILES[*]} on $HOST; restart CAE to load it"
