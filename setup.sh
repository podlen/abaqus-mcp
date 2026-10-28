#!/usr/bin/env bash
# Build the Windows VM in a user-session libvirt domain (qemu:///session, passt networking, no sudo).
# Everything lives in state_dir (config.local.toml, default ~/.local/share/abaqus-mcp) and in
# libvirt's own per-user folders. Settings come from `python -m abaqus_mcp.config --print`.
#
#   ./setup.sh              run every stage in order
#   ./setup.sh <stage>...   run only these stages
#   ./setup.sh abaqus <media-dir> [--dry-run]   install Abaqus in the VM (vm/install-abaqus.sh);
#                           listed by --list, not part of the default run (the media is an argument)
#   ./setup.sh gui          enable RDP in the running VM over SSH (for bin/abaqus-gui); listed by --list,
#                           not part of the default run
#   ./setup.sh live         install the live-bridge CAE plug-in in the running VM; listed by --list,
#                           not part of the default run
#   ./setup.sh uninstall    remove the domain and state_dir after a yes/no prompt; listed by --list,
#                           not part of the default run
#   ./setup.sh --list       show the stages
#   SETUP_DRY=1 ./setup.sh vm   print the virt-install command line and stop
#
# Every stage is idempotent. Needs: libvirt (user session, passt backend), passt, virt-install,
# xorriso, edk2-ovmf, curl, uv. Downloads ~6 GB; the unattended install takes ~20-40 min.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

command -v uv >/dev/null || { echo "missing: uv (https://docs.astral.sh/uv/)" >&2; exit 1; }
eval "$(uv run --directory "$HERE" python -m abaqus_mcp.config --print)"

ADMIN_USER=abaqus
STATE="$STATE_DIR"
MARKER="$STATE/.abaqus-mcp-setup"
KEY="$STATE/ssh_key"
SSH_CONFIG="$STATE/ssh_config"
PWFILE="$STATE/admin-password"
DISK="$STATE/win.qcow2"
WIN_ISO="$STATE/win11-eval.iso"
VIRTIO_ISO="$STATE/virtio-win.iso"
ANSWER_ISO="$STATE/answer.iso"
. "$HERE/vm/sources.env"  # WIN_URL, VIRTIO_URL, LOOPBACK
VIRSH=(virsh -c qemu:///session)

STAGES=(deps keys images answer sshconfig vm wait)  # default run
LISTED=("${STAGES[@]}" gui live abaqus uninstall)

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ssh_vm() { ssh -F "$SSH_CONFIG" -o BatchMode=yes -o ConnectTimeout=5 "$SSH_HOST" "$@"; }
dom_exists() { "${VIRSH[@]}" dominfo "$VM_NAME" &>/dev/null; }
init_state() { install -d -m 0700 "$STATE"; [ -f "$MARKER" ] || date -Is > "$MARKER"; }

stage_deps() {
    say "Host tools"
    local c missing=()
    for c in virsh virt-install xorriso curl ssh-keygen openssl; do
        command -v "$c" >/dev/null || missing+=("$c")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "    missing: ${missing[*]}"
        echo "    Arch: sudo pacman -S libvirt qemu-base virt-install libisoburn edk2-ovmf curl openssh openssl"
        return 1
    fi
    command -v passt >/dev/null || {
        echo "    missing: passt (libvirt's user networking backend)"
        echo "    Arch: sudo pacman -S passt   Debian/Ubuntu: sudo apt install passt   Fedora: sudo dnf install passt"
        return 1; }
    "${VIRSH[@]}" list --all >/dev/null || {
        echo "    cannot reach qemu:///session: install libvirt and qemu, then start the daemon (virtqemud) as your user"
        echo "    Arch: sudo pacman -S libvirt qemu-base   (user session needs no libvirt group)"
        return 1; }
    echo "    ok"
}

stage_keys() {
    say "State directory $STATE, SSH key and admin password"
    init_state
    if [ ! -f "$KEY" ]; then
        ssh-keygen -t ed25519 -N '' -C abaqus-vm -f "$KEY"
    elif [ ! -f "$KEY.pub" ]; then
        ssh-keygen -y -f "$KEY" > "$KEY.pub"
    fi
    if [ ! -s "$PWFILE" ]; then
        (umask 077; openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 20 > "$PWFILE"; echo >> "$PWFILE")
        echo "    generated $PWFILE"
    fi
    chmod 600 "$PWFILE"
}

fetch() {  # fetch <url> <dest>: link a reused ISO from iso_dir, else resumable download with atomic rename
    if [ -e "$2" ]; then echo "    $2 present ($(du -hL "$2" | cut -f1))"; return; fi
    if [ -n "$ISO_DIR" ] && [ -f "$ISO_DIR/$(basename "$2")" ]; then
        ln -s "$ISO_DIR/$(basename "$2")" "$2"; echo "    linked $ISO_DIR/$(basename "$2")"; return
    fi
    curl -fL --retry 5 --retry-delay 10 -C - --progress-bar -o "$2.part" "$1"
    mv "$2.part" "$2"
}

stage_images() {
    say "Windows 11 Enterprise evaluation ISO and virtio-win ISO"
    init_state
    fetch "$WIN_URL" "$WIN_ISO"
    fetch "$VIRTIO_URL" "$VIRTIO_ISO"
}

stage_answer() {
    say "Answer-file ISO (autounattend.xml + first-logon script)"
    if [ -f "$ANSWER_ISO" ] && [ "$ANSWER_ISO" -nt vm/autounattend.xml ] && [ "$ANSWER_ISO" -nt vm/fl-setup.ps1 ]; then
        echo "    present"; return
    fi
    [ -s "$PWFILE" ] && [ -f "$KEY.pub" ] || { echo "    run the keys stage first"; return 1; }
    local d="$STATE/build" pw paths=""
    rm -rf "$d"; mkdir -p "$d"
    pw=$(head -n1 "$PWFILE")
    local n=0 l sub
    for l in C D E F G H; do
        for sub in viostor NetKVM; do
            n=$((n+1))
            paths+="        <PathAndCredentials wcm:action=\"add\" wcm:keyValue=\"$n\"><Path>$l:\\$sub\\w11\\amd64</Path></PathAndCredentials>"$'\n'
        done
    done
    PATHS="$paths" U="$ADMIN_USER" P="$pw" awk '
        /__DRIVER_PATHS__/ { printf "%s", ENVIRON["PATHS"]; next }
        { gsub(/__ADMIN_USER__/, ENVIRON["U"]); gsub(/__ADMIN_PASSWORD__/, ENVIRON["P"]); print }' \
        vm/autounattend.xml > "$d/autounattend.xml"
    K="$(cat "$KEY.pub")" awk '{ gsub(/__SSH_PUBKEY__/, ENVIRON["K"]); print }' vm/fl-setup.ps1 > "$d/fl-setup.ps1"
    chmod 600 "$d/autounattend.xml"
    xorriso -as mkisofs -quiet -V ANSWER -J -r -o "$ANSWER_ISO" "$d"
    rm -rf "$d"
    echo "    wrote $ANSWER_ISO"
}

# Hold Enter on the "Press any key to boot from CD" prompt, then leave it.
press_keys() {
    local i
    for i in $(seq 1 20); do "${VIRSH[@]}" send-key "$VM_NAME" KEY_ENTER >/dev/null 2>&1 || true; sleep 1; done
}

stage_vm() {
    say "Creating the domain $VM_NAME in qemu:///session"
    # passt user networking: the host reaches the guest only through these forwards on 127.0.0.1
    local cmd=(virt-install --connect qemu:///session
        --name "$VM_NAME" --memory "$RAM_MB" --vcpus "$VCPUS" --cpu host-passthrough
        --os-variant win11
        --boot uefi,cdrom,hd
        --disk "path=$DISK,size=$DISK_GB,format=qcow2,bus=virtio"
        --disk "path=$WIN_ISO,device=cdrom,bus=sata"
        --disk "path=$VIRTIO_ISO,device=cdrom,bus=sata"
        --disk "path=$ANSWER_ISO,device=cdrom,bus=sata"
        --network "passt,model=virtio,portForward0=$LOOPBACK:$SSH_PORT:22,portForward1=$LOOPBACK:$RDP_PORT:3389"
        --graphics "vnc,listen=$LOOPBACK" --video qxl --tpm none
        --noautoconsole --wait 0 --noreboot)
    if [ -n "${SETUP_DRY:-}" ]; then printf '%q ' "${cmd[@]}"; echo; return; fi
    if dom_exists; then echo "    '$VM_NAME' exists"; return; fi
    [ -f "$ANSWER_ISO" ] && [ -f "$WIN_ISO" ] && [ -f "$VIRTIO_ISO" ] || { echo "    run images and answer first"; return 1; }
    "${cmd[@]}" 2>&1 | tail -5 || true
    dom_exists || { echo "    virt-install failed"; return 1; }
    "${VIRSH[@]}" domstate "$VM_NAME" | grep -q running || "${VIRSH[@]}" start "$VM_NAME"
    echo "    pressing Enter through the CD boot prompt"
    press_keys
}

stage_sshconfig() {
    say "$SSH_CONFIG (the only SSH configuration used; ~/.ssh/ stays untouched)"
    init_state
    cat > "$SSH_CONFIG" <<EOT
Host $SSH_HOST
    HostName $LOOPBACK
    Port $SSH_PORT
    User $ADMIN_USER
    IdentityFile $KEY
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
EOT
}

stage_wait() {
    say "Waiting for the install to finish and SSH on $LOOPBACK:$SSH_PORT (up to 90 min)"
    local i
    for i in $(seq 1 540); do
        if ssh_vm cmd /c ver 2>/dev/null; then break; fi
        # The first boot after the CD phase can sit at the CD prompt again.
        if [ $((i % 6)) = 0 ] && "${VIRSH[@]}" domstate "$VM_NAME" | grep -q running; then
            "${VIRSH[@]}" send-key "$VM_NAME" KEY_ENTER >/dev/null 2>&1 || true
        fi
        # Setup ends its first phase with a poweroff when --noreboot is used.
        "${VIRSH[@]}" domstate "$VM_NAME" | grep -q 'shut off' && "${VIRSH[@]}" start "$VM_NAME" >/dev/null && press_keys
        printf '.'; sleep 10
    done
    ssh_vm cmd /c ver 2>/dev/null || { echo; echo "    SSH never came up"; return 1; }
    # Eject the install media once, so later boots never see the CD prompt.
    local t
    for t in sda sdb sdc; do
        if "${VIRSH[@]}" domblklist "$VM_NAME" --details | awk -v t="$t" '$3==t && $4!="-"' | grep -q .; then
            "${VIRSH[@]}" change-media "$VM_NAME" "$t" --eject --config --live >/dev/null || true
        fi
    done
}

# RDP for bin/abaqus-gui. NLA stays on (xfreerdp3 does CredSSP with /from-stdin). Prints
# "changed" only when a setting had to be written, so a second run reports "unchanged".
stage_gui() {
    say "RDP in the VM (fDenyTSConnections=0, Remote Desktop firewall group, NLA on, CAE -mesa shortcut)"
    local ps enc out
    read -r -d '' ps <<'EOPS' || true
$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'
$changed = @()
$ts = 'HKLM:\System\CurrentControlSet\Control\Terminal Server'
$wsp = "$ts\WinStations\RDP-Tcp"
if ((Get-ItemProperty $ts).fDenyTSConnections -ne 0) {
    Set-ItemProperty $ts -Name fDenyTSConnections -Value 0 -Type DWord; $changed += 'fDenyTSConnections' }
if ((Get-ItemProperty $wsp).UserAuthentication -ne 1) {
    Set-ItemProperty $wsp -Name UserAuthentication -Value 1 -Type DWord; $changed += 'NLA' }
$fw = Get-NetFirewallRule -DisplayGroup 'Remote Desktop'
if (@($fw | Where-Object { $_.Enabled -ne 'True' }).Count -gt 0) {
    Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'; $changed += 'firewall' }
if ((Get-Service TermService).StartType -ne 'Manual' -and (Get-Service TermService).StartType -ne 'Automatic') {
    Set-Service TermService -StartupType Manual; $changed += 'service-start' }
if ((Get-Service TermService).Status -ne 'Running') { Start-Service TermService; $changed += 'service-run' }
$lnk = 'C:\Users\abaqus\Desktop\Abaqus CAE (mesa).lnk'
$tgt = 'C:\Program Files\SIMULIA\Commands\abaqus.bat'
$sh = New-Object -ComObject WScript.Shell
$cur = if (Test-Path -LiteralPath $lnk) { $sh.CreateShortcut($lnk) } else { $null }
if (-not $cur -or $cur.TargetPath -ne $tgt -or $cur.Arguments -ne 'cae -mesa') {
    New-Item -ItemType Directory -Force (Split-Path $lnk) | Out-Null
    $l = $sh.CreateShortcut($lnk); $l.TargetPath = $tgt; $l.Arguments = 'cae -mesa'
    $l.WorkingDirectory = 'C:\Users\abaqus'; $l.Save(); $changed += 'shortcut' }
if ($changed.Count) { 'changed: ' + ($changed -join ', ') } else { 'unchanged' }
EOPS
    enc=$(printf '%s' "$ps" | iconv -t UTF-16LE | base64 -w0)
    out=$(ssh_vm powershell -NoProfile -NonInteractive -EncodedCommand "$enc") || { echo "    SSH failed"; return 1; }
    echo "    $out"
}

stage_live() {
    say "live-bridge plug-in into the VM account (restart CAE to load it)"
    "$HERE/vm/install-live-plugin.sh"
}

# Refuses unless state_dir holds the setup marker and is not $HOME, /, the repo or a parent of it.
stage_uninstall() {
    say "Uninstall: domain $VM_NAME and $STATE"
    local s; s="$(realpath -m -- "$STATE")"
    if [ "$s" = "$(realpath -m -- "$HOME")" ] || [ "$s" = / ] || [ "$s" = "$HERE" ] || [[ "$HERE/" == "$s/"* ]]; then
        echo "    refusing: $s is \$HOME, /, or the repo or a parent of it" >&2; return 1
    fi
    [ -f "$s/.abaqus-mcp-setup" ] || { echo "    refusing: no setup marker in $s" >&2; return 1; }
    local size ans; size="$(du -sh -- "$s" | cut -f1)"
    read -r -p "    Delete domain $VM_NAME and $s ($size)? [y/N] " ans || ans=n
    [[ "$ans" =~ ^[Yy]([Ee][Ss])?$ ]] || { echo "    aborted"; return 1; }
    if dom_exists; then
        "${VIRSH[@]}" domstate "$VM_NAME" | grep -q running && "${VIRSH[@]}" destroy "$VM_NAME"
        "${VIRSH[@]}" undefine --nvram "$VM_NAME"
    fi
    rm -rf -- "$s"
    echo "    removed; the repo, config.local.toml and reused ISOs in iso_dir stay"
}

if [ "${1:-}" = "--list" ]; then printf '%s\n' "${LISTED[@]}"; exit 0; fi

if [ "${1:-}" = "abaqus" ]; then
    shift
    dry=(); media=""
    for a in "$@"; do if [ "$a" = "--dry-run" ]; then dry=(--dry-run); else media="$a"; fi; done
    [ -n "$media" ] || { echo "usage: ./setup.sh abaqus <media-dir> [--dry-run]"; exit 1; }
    say "Abaqus install from $media"
    exec "$HERE/vm/install-abaqus.sh" "${dry[@]}" "$media"
fi

RUN=("$@"); [ ${#RUN[@]} -eq 0 ] && RUN=("${STAGES[@]}")
for s in "${RUN[@]}"; do
    declare -F "stage_$s" >/dev/null || { echo "unknown stage: $s (see --list)"; exit 1; }
    "stage_$s"
done
say "Done."
