#!/usr/bin/env bash
# Build the Windows VM `abaqus-win` (no sudo anywhere).
#
#   ./setup.sh              run every stage in order
#   ./setup.sh <stage>...   run only these stages
#   ./setup.sh abaqus <media-dir> [--dry-run]   install Abaqus in the VM (vm/install-abaqus.sh);
#                           listed by --list, not part of the default run (the media is an argument)
#   ./setup.sh --list       show the stages
#
# Every stage is idempotent. Needs: libvirt group membership, virt-install,
# xorriso, edk2-ovmf, curl. Downloads ~6 GB; the unattended install takes ~20-40 min.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VM=abaqus-win
IP=192.168.122.51
MAC=52:54:00:41:42:01
RAM=8192
VCPUS=6
DISK_GB=80
ADMIN_USER=abaqus
KEY="$HOME/.ssh/abaqus_vm"
PWFILE="$HERE/.admin-password"
WIN_ISO=images/win11-eval.iso
VIRTIO_ISO=images/virtio-win.iso
ANSWER_ISO=vm/build/answer.iso
# fwlink for the Windows 11 Enterprise evaluation, en-us x64 (Microsoft's own servers)
WIN_URL='https://go.microsoft.com/fwlink/?linkid=2289031&clcid=0x409&culture=en-us&country=us'
VIRTIO_URL=https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso
VIRSH=(virsh -c qemu:///system)

STAGES=(deps keys images answer net vm sshconfig wait)  # default run
LISTED=("${STAGES[@]}" abaqus)

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ssh_vm() { ssh -i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
               -o LogLevel=ERROR -o BatchMode=yes -o ConnectTimeout=5 "$ADMIN_USER@$IP" "$@"; }
vol_exists() { "${VIRSH[@]}" vol-info --pool images "$1" &>/dev/null; }
dom_exists() { "${VIRSH[@]}" dominfo "$VM" &>/dev/null; }

stage_deps() {
    say "Host tools"
    for c in virsh virt-install xorriso curl ssh-keygen openssl; do
        command -v "$c" >/dev/null || { echo "    missing: $c"; return 1; }
    done
    "${VIRSH[@]}" net-info default >/dev/null || { echo "    cannot reach qemu:///system"; return 1; }
    echo "    ok"
}

stage_keys() {
    say "SSH key $KEY and admin password"
    if [ ! -f "$KEY" ]; then
        install -d -m 0700 "$HOME/.ssh"
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

fetch() {  # fetch <url> <dest>: resumable, atomic rename
    if [ -f "$2" ]; then echo "    $2 present ($(du -h "$2" | cut -f1))"; return; fi
    curl -fL --retry 5 --retry-delay 10 -C - --progress-bar -o "$2.part" "$1"
    mv "$2.part" "$2"
}

stage_images() {
    say "Windows 11 Enterprise evaluation ISO and virtio-win ISO"
    mkdir -p images
    fetch "$WIN_URL" "$WIN_ISO"
    fetch "$VIRTIO_URL" "$VIRTIO_ISO"
}

stage_answer() {
    say "Answer-file ISO (autounattend.xml + first-logon script)"
    if [ -f "$ANSWER_ISO" ] && [ "$ANSWER_ISO" -nt vm/autounattend.xml ] && [ "$ANSWER_ISO" -nt vm/fl-setup.ps1 ]; then
        echo "    present"; return
    fi
    [ -s "$PWFILE" ] && [ -f "$KEY.pub" ] || { echo "    run the keys stage first"; return 1; }
    local d=vm/build/src pw paths=""
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
    # the pool copy is read by the existing domain; replace its content only, never the domain
    if vol_exists abaqus-answer.iso; then
        "${VIRSH[@]}" vol-delete --pool images abaqus-answer.iso
        upload "$ANSWER_ISO" abaqus-answer.iso && echo "    replaced pool volume abaqus-answer.iso"
    fi
}

stage_net() {
    say "Pinning $IP to $MAC on the default network"
    if "${VIRSH[@]}" net-dumpxml default | grep -q "mac='$MAC'.*ip='$IP'"; then
        echo "    already pinned"
    else
        "${VIRSH[@]}" net-update default delete ip-dhcp-host "<host mac='$MAC'/>" --live --config 2>/dev/null || true
        "${VIRSH[@]}" net-update default add ip-dhcp-host "<host mac='$MAC' name='$VM' ip='$IP'/>" --live --config
    fi
}

# Upload a local file into libvirt's images pool (the qemu user cannot read
# $HOME, and this needs no sudo).
upload() {  # upload <file> <volname>
    vol_exists "$2" && return
    "${VIRSH[@]}" vol-create-as images "$2" "$(stat -c %s "$1")" --format raw
    "${VIRSH[@]}" vol-upload --pool images "$2" "$1"
}

# Hold Enter on the "Press any key to boot from CD" prompt, then leave it.
press_keys() {
    local i
    for i in $(seq 1 20); do "${VIRSH[@]}" send-key "$VM" KEY_ENTER >/dev/null 2>&1 || true; sleep 1; done
}

stage_vm() {
    say "Creating the domain $VM"
    if dom_exists; then echo "    '$VM' exists"; return; fi
    [ -f "$ANSWER_ISO" ] && [ -f "$WIN_ISO" ] && [ -f "$VIRTIO_ISO" ] || { echo "    run images and answer first"; return 1; }
    upload "$WIN_ISO" abaqus-win11.iso
    upload "$VIRTIO_ISO" abaqus-virtio-win.iso
    vol_exists abaqus-answer.iso && "${VIRSH[@]}" vol-delete --pool images abaqus-answer.iso
    upload "$ANSWER_ISO" abaqus-answer.iso
    vol_exists abaqus-win.qcow2 || "${VIRSH[@]}" vol-create-as images abaqus-win.qcow2 "${DISK_GB}G" --format qcow2
    local pool; pool=$("${VIRSH[@]}" pool-dumpxml images | sed -n 's|.*<path>\(.*\)</path>.*|\1|p' | head -1)
    virt-install --connect qemu:///system \
        --name "$VM" --memory "$RAM" --vcpus "$VCPUS" --cpu host-passthrough \
        --os-variant win11 \
        --boot uefi,cdrom,hd \
        --disk "path=$pool/abaqus-win.qcow2,format=qcow2,bus=virtio" \
        --disk "path=$pool/abaqus-win11.iso,device=cdrom,bus=sata" \
        --disk "path=$pool/abaqus-virtio-win.iso,device=cdrom,bus=sata" \
        --disk "path=$pool/abaqus-answer.iso,device=cdrom,bus=sata" \
        --network "network=default,mac=$MAC,model=virtio" \
        --graphics vnc --video qxl --tpm none \
        --noautoconsole --wait 0 --noreboot 2>&1 | tail -5 || true
    dom_exists || { echo "    virt-install failed"; return 1; }
    "${VIRSH[@]}" domstate "$VM" | grep -q running || "${VIRSH[@]}" start "$VM"
    echo "    pressing Enter through the CD boot prompt"
    press_keys
}

stage_sshconfig() {
    say "~/.ssh/config entry"
    if grep -q '^Host abaqus-vm$' "$HOME/.ssh/config" 2>/dev/null; then
        echo "    present"
    else
        cat >> "$HOME/.ssh/config" <<EOT

Host abaqus-vm
    HostName $IP
    User $ADMIN_USER
    IdentityFile $KEY
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
EOT
    fi
}

stage_wait() {
    say "Waiting for the install to finish and SSH on $IP (up to 90 min)"
    local i
    for i in $(seq 1 540); do
        if ssh_vm cmd /c ver 2>/dev/null; then break; fi
        # The first boot after the CD phase can sit at the CD prompt again.
        if [ $((i % 6)) = 0 ] && "${VIRSH[@]}" domstate "$VM" | grep -q running; then
            "${VIRSH[@]}" send-key "$VM" KEY_ENTER >/dev/null 2>&1 || true
        fi
        # Setup ends its first phase with a poweroff when --noreboot is used.
        "${VIRSH[@]}" domstate "$VM" | grep -q 'shut off' && "${VIRSH[@]}" start "$VM" >/dev/null && press_keys
        printf '.'; sleep 10
    done
    ssh_vm cmd /c ver 2>/dev/null || { echo; echo "    ssh never came up"; return 1; }
    # Eject the install media once, so later boots never see the CD prompt.
    local t
    for t in sda sdb sdc; do
        if "${VIRSH[@]}" domblklist "$VM" --details | awk -v t="$t" '$3==t && $4!="-"' | grep -q .; then
            "${VIRSH[@]}" change-media "$VM" "$t" --eject --config --live >/dev/null || true
        fi
    done
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
