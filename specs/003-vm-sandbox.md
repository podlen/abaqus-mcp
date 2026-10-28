# VM sandbox: one folder in, one command out

Status: draft. Owner: Enej. Branch: 003-vm-sandbox.

Goal: another Linux user (a friend with an own Abaqus licence and the same university VPN) clones
the repo, builds the Abaqus VM with one command, uses the MCP, and removes everything with one
command. The build touches nothing on the host outside one state directory, and its settings
live in one config file (source: Enej, 2026-10-28).

## Criteria
C1. One state directory. Everything the build creates lives in `state_dir` (config; default
    `~/.local/share/abaqus-mcp`): disk image, Windows and virtio ISOs, answer ISO, ssh key,
    ssh config, admin password. The repo's `images/` and `.admin-password` are no longer used.
    check: touch a stamp file, run `./setup.sh`; `find ~ -newer stamp` outside `state_dir`, the
    repo and libvirt's own `~/.config/libvirt/` and `~/.cache/libvirt/` lists nothing.
C2. User-session libvirt. The domain is defined in `qemu:///session` with passt user networking
    and port forwards bound to 127.0.0.1 for ssh and RDP (ports from config). No system libvirt
    network, domain or pool is created or changed.
    check: `virsh -c qemu:///system list --all`, `net-dumpxml default` and `pool-list --all`
    identical before and after `./setup.sh`; `ss -ltn` shows the forwards on 127.0.0.1 only.
C3. No ~/.ssh edits. The MCP transport, `bin/abaqus-gui` and setup use
    `ssh -F <state_dir>/ssh_config`. check: `~/.ssh` file list and checksums unchanged by setup.
C4. Licence. The VM reaches the DSLS server through passt and the host's split-tunnel VPN. The
    NetworkManager connection name is a config value (default `fs-abaqus`); each user brings an
    own connection and credentials. check: `license_check` returns ok from the session VM.
C5. One config file. `config.local.toml` holds VM name, RAM, CPUs, disk size, forwarded ports,
    `state_dir`, VPN connection and licence host; `setup.sh` reads it and keeps no copies of
    these values. check: `./setup.sh --print-config` shows the values from a test config;
    `grep -nE 'RAM=|VCPUS=|DISK_GB=|IP=' setup.sh` finds no literal values.
C6. Uninstall. `./setup.sh uninstall` undefines the domain and deletes `state_dir` after a
    yes/no prompt that names the disk size. The repo and `config.local.toml` stay.
    check: after uninstall, the C1-C3 host snapshots equal the ones taken before install.
C7. Project directory. The user names the analysis directory per project: existing files or a
    new location. The MCP takes it per session (tool `set_project(path)`; jobs then read and
    write `<path>/<job>/`), the VM mirror is `C:\abaqus-work\<project>\<job>`, and the skill's
    workflow starts by asking for it (source: Enej, 2026-10-28). check: a test sets a temporary
    directory, runs the cantilever, and finds its .odb and summary there and nowhere else on the host.
C8. Fresh-user run. A second Linux account on Enej's machine follows the README from clone to
    `license_check`, the cantilever E2E and uninstall. check: user judges; ISOs may be reused
    from a config path to skip the 6 GB download.
C9. README install section covers the new flow, host packages (incl. passt) and the 90-day
    Windows evaluation (rebuild or rearm).

## Facts
- Friend: Linux host, own Abaqus Teaching licence, same university VPN (source: Enej, 2026-10-28).
- Host packages: libvirt 12.8.0, qemu-base 11.1.2, virt-install 5.1.0; passt is in Arch `extra`
  and not installed (checked 2026-10-28). Setup runs without sudo; the user installs packages.
- Today: domain `abaqus-win` on qemu:///system, DHCP reservation in the system `default` network,
  key `~/.ssh/abaqus_vm`, a `~/.ssh/config` block, ISOs in `images/`, password in `.admin-password`
  (setup.sh, 2026-10-28).
- The Windows 11 Enterprise evaluation runs 90 days; Enej's VM is rearmed to 2027-01-25.
- The transport copies files over scp (docs/decisions.md); no shared folder.

## Ruled out
- Containers wrapping the VM (source: Enej, 2026-10-28).
- Windows and macOS hosts.
- Sharing a built VM image between users (Windows and Abaqus licensing).

## Open
- Enej's existing system VM: migrate its disk into the session domain, rebuild, or keep it
  reachable through a `libvirt_uri` setting until the next rebuild.

## Log
