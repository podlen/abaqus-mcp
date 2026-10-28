# First-logon provisioning, run from the ANSWER CD. __SSH_PUBKEY__ is filled in by setup.sh.
Start-Transcript C:\fl-setup.log -Force
$ErrorActionPreference = 'Continue'

# virtio network driver (WinPE-loaded drivers do not all persist)
foreach ($v in (Get-Volume | Where-Object { $_.FileSystemLabel -like 'virtio-win*' })) {
    pnputil /add-driver "$($v.DriveLetter):\NetKVM\w11\amd64\*.inf" /install
}
for ($i = 0; $i -lt 60; $i++) {
    if (Test-Connection 192.168.122.1 -Count 1 -Quiet) { break }
    Start-Sleep 3
}

# no sleep, no Windows Update
powercfg /h off
powercfg /change standby-timeout-ac 0; powercfg /change monitor-timeout-ac 0; powercfg /change disk-timeout-ac 0
New-Item 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -Force | Out-Null
Set-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' NoAutoUpdate 1 -Type DWord
foreach ($s in 'wuauserv', 'UsoSvc', 'WaaSMedicSvc') {
    Stop-Service $s -Force -ErrorAction SilentlyContinue
    Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\$s" Start 4 -ErrorAction SilentlyContinue
}

# OpenSSH server: Windows capability, else the GitHub release zip
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    try { Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction Stop | Out-Null } catch { Write-Host $_ }
}
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    [Net.ServicePointManager]::SecurityProtocol = 'Tls12'
    Invoke-WebRequest 'https://github.com/PowerShell/Win32-OpenSSH/releases/download/v9.8.1.0p1-Preview/OpenSSH-Win64.zip' -OutFile C:\ossh.zip
    Expand-Archive C:\ossh.zip 'C:\Program Files' -Force
    Rename-Item 'C:\Program Files\OpenSSH-Win64' 'C:\Program Files\OpenSSH' -ErrorAction SilentlyContinue
    & 'C:\Program Files\OpenSSH\install-sshd.ps1'
}
Set-Service sshd -StartupType Automatic
Set-Service ssh-agent -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service sshd
New-ItemProperty 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force | Out-Null
if (-not (Get-NetFirewallRule -Name sshd-in -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name sshd-in -DisplayName 'OpenSSH 22' -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow -Profile Any | Out-Null
}
$f = 'C:\ProgramData\ssh\administrators_authorized_keys'
Set-Content -Path $f -Value '__SSH_PUBKEY__' -Encoding ascii
icacls $f /inheritance:r /grant 'SYSTEM:(F)' /grant 'BUILTIN\Administrators:(F)'
Restart-Service sshd
# The eval's grace period is already over on the ISO's build date; rearm gives 90 days.
cscript //nologo C:\Windows\System32\slmgr.vbs /rearm
Stop-Transcript
shutdown /r /t 15
