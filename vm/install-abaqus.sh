#!/usr/bin/env bash
# Install Abaqus 2026 Teaching Edition in the VM, silently, and point it at the DSLS server.
# usage: vm/install-abaqus.sh [--dry-run] <media-dir>
#   <media-dir> holds 03_Abaqus2026/1/setup.exe (the faculty media).
# Reads license_host, license_port, ssh_host, state_dir from config.local.toml (override: $ABAQUS_MCP_CONFIG)
# through `python -m abaqus_mcp.config --print`.
# The VM's SSH shell is Windows PowerShell 5.1: remote commands are PowerShell.
# Silent mode: `setup.exe --silent <UserIntentions.xml>`. The XML is the one the installer wrote
# for the existing Windows install (selections: Standard, Explicit, CAE), with the license host filled in.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY=1; shift; fi
MEDIA="${1:?usage: install-abaqus.sh [--dry-run] <media-dir>}"
SETUP="$MEDIA/03_Abaqus2026/1/setup.exe"
[[ -f "$SETUP" ]] || { echo "missing $SETUP" >&2; exit 1; }
eval "$(uv run --directory "$HERE/.." python -m abaqus_mcp.config --print)"
[[ -n "$LICENSE_HOST" ]] || { echo "license_host missing in config.local.toml (copy config.example.toml)" >&2; exit 1; }
VM="$SSH_HOST"
DEST='C:/Install'

run() { echo "+ $*"; if [[ $DRY -eq 0 ]]; then "$@"; fi; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
sed "s/__LICENSE_HOST__/$LICENSE_HOST/" "$HERE/UserIntentions_CODE.xml.tmpl" > "$TMP/UserIntentions_CODE.xml"

# 1. copy media (setup.exe folder 03_Abaqus2026 only) and the helper into the VM
run ssh -F "$STATE_DIR/ssh_config" -o BatchMode=yes "$VM" 'New-Item -ItemType Directory -Force -Path C:\Install | Out-Null'
run scp -F "$STATE_DIR/ssh_config" -r "$MEDIA/03_Abaqus2026" "$VM:$DEST/"
run scp -F "$STATE_DIR/ssh_config" "$TMP/UserIntentions_CODE.xml" "$HERE/install-abaqus.ps1" "$VM:$DEST/"

# 2. silent install + DSLS license file, then check the release
run ssh -F "$STATE_DIR/ssh_config" -o BatchMode=yes -o ServerAliveInterval=30 "$VM" \
    "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Install\install-abaqus.ps1 -LicenseHost '$LICENSE_HOST' -LicensePort $LICENSE_PORT"

echo "done: check with  ssh -F $STATE_DIR/ssh_config $VM abaqus information=release   (expect 2026)"
