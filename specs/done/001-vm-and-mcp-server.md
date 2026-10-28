# Abaqus MCP

Status: done (pushed as 87d46ca, 2026-10-28). Facts about Enej's machine and network are kept locally.

Goal: from Claude Code on Omarchy, build, run and post-process Abaqus models in a Windows
VM, with the university license reached over OpenVPN, without rebooting into Windows.

## Criteria
C1. Windows VM. `setup.sh` (idempotent stages) downloads
    the Windows 11 Enterprise evaluation ISO and virtio-win, installs unattended
    (autounattend.xml with LabConfig TPM/Secure Boot bypass, virtio drivers, OpenSSH server,
    key login with ~/.ssh/abaqus_vm, sleep and Windows Update off) as libvirt domain
    `abaqus-win` on qemu:///system, 8 GB RAM, 6 vCPU, 80 GB disk. No sudo in any stage.
    check: `ssh abaqus-vm cmd /c ver` prints a Windows version; a second `./setup.sh`
    exits 0 and changes nothing.
C2. VPN without sudo. `bin/abaqus-vpn up|down|status` wraps `nmcli connection up|down
    fs-abaqus`; `up` is idempotent. The VM reaches the license server through the host
    tunnel (libvirt NAT).
    check: VPN up: `Test-NetConnection <license host> -Port <port>` in the VM succeeds;
    VPN down: it fails.
C3. MCP server on the host: Python, uv project, stdio, official `mcp` SDK. Tools:
    license_check, run_script (abaqus cae noGUI), submit_job, job_status (.sta/.msg),
    odb_query (JSON), model_info, viewport_png. Transport to the VM over ssh, files by
    scp. License host, port and ssh alias come from git-ignored `config.local.toml`;
    `config.example.toml` is committed with placeholders.
    check: `uv run pytest` passes against a stub ssh/abaqus; `claude mcp add` registers it
    and tools/list shows all seven.
C4. License guard. run_script and submit_job call license_check first. license_check
    runs `abaqus-vpn up` once when the port is closed; if it is still closed, the call
    returns "license server unreachable" within 30 s.
    check: VPN down: license_check reconnects and passes; config pointing at a closed port:
    the error arrives within 30 s.
C5. Abaqus install stage `./setup.sh abaqus <media-dir>`: copies the media into the VM,
    installs silently, configures DSLS license server <license host>:<port>.
    Tonight: written, reviewed against the installer's documented silent mode. Morning:
    run on Enej's media.
    check (morning): `ssh abaqus-vm abaqus information=release` prints 2026.
C6. End to end through the MCP: steel cantilever, L = 1 m, 20 x 20 mm square section,
    E = 210 GPa, nu = 0.3, rho = 7850 kg/m^3, 20 B33 elements, linear (NLGEOM off).
    Tip load P = 100 N: tip deflection within 1 % of PL^3/(3EI) = 11.905 mm.
    Frequency step: f1 within 2 % of (1.8751^2 / 2pi) sqrt(EI / (rho A L^4)) = 16.71 Hz.
    A script with a deliberate error returns its traceback; a job without boundary
    conditions makes job_status report the .msg error.
    check (morning): run via the MCP tools; compare with the hand calc in the test.
C7. README covers install and use, facts only.
C8. GitHub: private repo podlen/abaqus-mcp, remote `origin`. After the final critic
    pass, push main. The repo stays publishable.
    check: `git grep -nE "$(cat .team/publish-patterns)"`
    on main returns nothing; `git ls-files` lists no .ovpn, .pem or config.local.toml.

## Ruled out
- Copying the Windows Abaqus install into a VM: it depends on registry, services and
  license-client config.
- Abaqus under Wine.
- Booting the physical Windows partition in a VM: driver and activation churn, possible
  BitLocker recovery, NTFS corruption risk.
- Downloading Abaqus from Dassault or the faculty: needs Enej.
- Live GUI session control: v2, out of scope.
