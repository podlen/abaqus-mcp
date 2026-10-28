# VM sandbox: one folder in, one command out

Status: closed (source: Enej, 2026-10-28). Owner: Enej.

Goal: another Linux user (a friend with an own Abaqus licence and the same university VPN) clones
the repo, builds the Abaqus VM with one command, uses the MCP, and removes everything with one
command. The build touches nothing on the host outside one state directory and libvirt's own
per-user folders, and its settings live in one config file (source: Enej, 2026-10-28).

## Criteria
C1. One state directory. Everything the build creates lives in `state_dir` (config; default
    `~/.local/share/abaqus-mcp`): disk image, Windows and virtio ISOs (or links to reused ones),
    answer ISO, ssh key, `ssh_config`, admin password, a marker file, and the MCP's own scratch
    files (`_live`). The repo's `images/` and `.admin-password` are no longer used.
    check: before and after `./setup.sh`, `find ~/.ssh ~/.config ~/.local/share ~/.cache -type f`
    (names only); the difference lies in `state_dir`, `~/.config/libvirt/`, `~/.local/share/libvirt/`,
    `~/.cache/libvirt/` and `~/.cache/virt-manager/` only.
C2. User-session libvirt. The domain (config `vm_name`, default `abaqus-mcp`) is defined in
    `qemu:///session` with passt user networking; the host reaches the guest only through port
    forwards on 127.0.0.1 (config `ssh_port`, `rdp_port`). No system libvirt network, domain or
    pool is created or changed. No 192.168.122 address remains.
    check: `virsh -c qemu:///system list --all`, `net-dumpxml default` and `pool-list --all`
    identical before and after `./setup.sh`; `ss -ltn` shows the forwards on 127.0.0.1 only;
    `grep -rn 192.168.122 setup.sh bin vm src tests` finds nothing.
C3. No ~/.ssh edits. Every ssh and scp call (setup.sh, bin/, vm/*.sh, the transport, tests) uses
    `-F <state_dir>/ssh_config`, which holds `HostName 127.0.0.1`, the port and the key.
    check: `~/.ssh` file list and checksums unchanged by setup; every `ssh`/`scp` line found by
    `grep -rnE '\b(ssh|scp) ' setup.sh bin vm src tests` passes `-F`.
C4. Licence. The VM reaches the DSLS server through passt and the host's split-tunnel VPN. The
    NetworkManager connection name is a config value (`vpn_connection`, default `fs-abaqus`) read
    by `bin/abaqus-vpn`; each user brings an own connection and credentials.
    check: in the VM over ssh, `Test-NetConnection <license_host> -Port <license_port>` succeeds,
    and the cantilever E2E runs (licence checkout).
C5. One config file. `config.local.toml` holds: vm_name, ram_mb, vcpus, disk_gb, ssh_port,
    rdp_port, state_dir, iso_dir (optional reuse), vpn_connection, license_host, license_port.
    Defaults live once, in `src/abaqus_mcp/config.py`; setup.sh and bin/ read the resolved values
    through `python -m abaqus_mcp.config --print` (`uv run`). `work_host` is removed (C7).
    check: `grep -nE '(RAM|VCPUS|DISK_GB|VM|CON|MAC|IP)=[^$"(]|=[0-9]{3,}' setup.sh bin/*` finds
    nothing; a test config with non-default values prints exactly a fixture.
C6. Uninstall. `./setup.sh uninstall` destroys the domain if running, `undefine --nvram`s it, and
    deletes `state_dir` after a yes/no prompt that names its actual size (`du -sh`). It refuses
    unless `state_dir` holds the setup marker and is not `$HOME`, `/`, or the repo or a parent of
    it. Reused ISOs in `iso_dir` stay. The repo and `config.local.toml` stay.
    check: `virsh -c qemu:///session list --all` empty; no `<vm_name>` file under
    `~/.config/libvirt/qemu/`; the C1 file list equals the pre-install list apart from libvirt and
    virt-install logs; a unit test feeds `state_dir = "~"` and a dir without marker and gets refusals.
C7. Project directory. The user names the analysis directory per project: existing files or a new
    location (source: Enej, 2026-10-28). Tool `set_project(path)` sets it for the session; a second
    call switches projects. Jobs read and write `<path>/<job>/`; input files at `<path>/` are
    found by name. The VM mirror is `C:\abaqus-work\<slug>-<hash>\<job>`, slug from the basename
    reduced to `[A-Za-z0-9_-]`, hash the first 8 hex of sha1 of the resolved path. Before the
    first `set_project`, job tools return "no project: call set_project". `path` must resolve
    (symlinks followed) under `$HOME`. The skill's workflow starts by asking for the directory.
    check: unit tests for the slug, the hash, the `$HOME` limit and the no-project error; an E2E
    test sets a temporary directory, runs the cantilever, and finds the files fetched to the host
    (results JSON, PNG) in `<path>/<job>/` and the .odb in the VM mirror; nothing under `~/abaqus-work`; `grep -n set_project skills/abaqus-modelling/SKILL.md` finds the step.
C8. Fresh-user run. Enej's friend follows the README on his own Linux machine, from clone to the
    cantilever E2E and uninstall, mostly through Claude, and fixes what breaks in a PR against this
    spec (source: Enej, 2026-10-28). check: the friend's PR or report names each README step as passed.
C9. README reads well for a person and works as instructions Claude can follow (source: Enej,
    2026-10-28). It opens with what the project does and for whom. Its install section covers: host packages with minimum versions (libvirt with the passt
    backend, passt, virt-install, xorriso, edk2-ovmf), the new flow, uninstall, and the 90-day
    Windows evaluation (`slmgr /xpr` to read the date, rearm or rebuild). The `deps` stage checks
    `virsh -c qemu:///session` and `command -v passt` and stops with the package names, no sudo.
    check: `grep -nE 'passt|slmgr|uninstall' README.md`; `./setup.sh deps` on a PATH without passt
    stops with the message.

## Facts
- Friend: Linux host, own Abaqus Teaching licence, same university VPN (source: Enej, 2026-10-28).
- Host packages: libvirt 12.8.0, qemu-base 11.1.2, virt-install 5.1.0; passt is in Arch `extra`
  and not installed (checked 2026-10-28). Setup runs without sudo; the user installs packages.
- virt-install 5.1.0 accepts `--network passt,portForward0=127.0.0.1:2222:22` (man page, critic
  spec review 2026-10-28). The libvirt release that added passt `portForward`: [TBD, libvirt NEWS].
- Today: domain `abaqus-win` on qemu:///system, DHCP reservation in the system `default` network,
  key `~/.ssh/abaqus_vm`, a `~/.ssh/config` block, ISOs in `images/`, password in `.admin-password`;
  `bin/abaqus-gui` and `vm/fl-setup.ps1` (waits on a ping to 192.168.122.1) use the fixed network
  (setup.sh, bin/, vm/, 2026-10-28).
- `license_check` is a TCP connect from the host; it does not test the VM's route.
- The Windows 11 Enterprise evaluation runs 90 days after `slmgr /rearm`, which `vm/fl-setup.ps1`
  runs at first logon. The number of rearms allowed: [TBD].
- The transport copies files over scp (docs/decisions.md); no shared folder.

## Ruled out
- Containers wrapping the VM (source: Enej, 2026-10-28).
- Windows and macOS hosts.
- Sharing a built VM image between users (Windows and Abaqus licensing).
- A `libvirt_uri` setting pointing back at qemu:///system (contradicts C2).

## Decided
- Enej's VM: rebuild in the session domain and reinstall Abaqus with `./setup.sh abaqus <media>`.
  The system domain `abaqus-win` stays untouched until the session VM passes C4; removing it needs
  Enej's go (source: Enej, 2026-10-28).
- passt installed on Enej's host (2026-10-28).

## Log
- 2026-10-28: session VM `abaqus-mcp` built by `./setup.sh` (ISOs reused from `iso_dir`) and Abaqus
  installed by `./setup.sh abaqus`. C1/C3: no file in `~/.ssh` changed; other new files under `~` belong
  to unrelated apps. C2: system libvirt domain and network lists unchanged; forwards on
  127.0.0.1:2222 and :3390. C4: `Test-NetConnection` to the licence port from the VM: True.
  C7 and the E2E suite: `ABAQUS_E2E=1 uv run pytest` 72 passed, 5 skipped (live tests).
  C5: greps empty; unit tests 61 passed. C6: refusal unit tests pass; a real uninstall not run (it
  would delete the new VM). C8: open, for the friend. C9: README minimum libvirt version and rearm count [TBD].
- 2026-10-28: closed by Enej. Old system domain `abaqus-win`, its DHCP entry, `~/.ssh/abaqus_vm` and
  its `~/.ssh/config` block removed; ISOs moved into `state_dir`. C6 real uninstall, C8 and the C9 [TBD]s in backlog.
