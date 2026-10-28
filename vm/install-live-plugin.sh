#!/usr/bin/env bash
# Copy the live-bridge plug-in into the VM account's abaqus_plugins folder (idempotent).
# usage: vm/install-live-plugin.sh [--dry-run]
# Reads ssh_host from config.local.toml (override: $ABAQUS_MCP_CONFIG). Restart CAE afterwards.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${ABAQUS_MCP_CONFIG:-$HERE/../config.local.toml}"
[[ -f "$CONFIG" ]] || { echo "missing $CONFIG" >&2; exit 1; }
HOST="$(python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb")).get("ssh_host","abaqus-vm"))' "$CONFIG")"
FILES=(mcp_live_plugin.py mcp_live_core.py mcp_live_kernel.py)
if [[ "${1:-}" == "--dry-run" ]]; then echo "would install ${FILES[*]} on $HOST"; exit 0; fi
DEST='$env:USERPROFILE\abaqus_plugins\mcp_live'
ssh -o BatchMode=yes "$HOST" "New-Item -ItemType Directory -Force -Path \"$DEST\" | Out-Null; foreach (\$d in 'inbox','outbox','log') { New-Item -ItemType Directory -Force -Path \"C:\\abaqus-work\\live\\\$d\" | Out-Null }"
for f in "${FILES[@]}"; do scp -q -o BatchMode=yes "$HERE/plugin/$f" "$HOST:abaqus_plugins/mcp_live/$f"; done
echo "installed ${FILES[*]} on $HOST; restart CAE to load it"
