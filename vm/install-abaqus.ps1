# Runs inside the VM (elevated ssh session). Called by install-abaqus.sh.
param([Parameter(Mandatory)][string]$LicenseHost, [int]$LicensePort = 4085)
$ErrorActionPreference = 'Stop'
$setup = 'C:\Install\03_Abaqus2026\1\setup.exe'
$xml = 'C:\Install\UserIntentions_CODE.xml'
$root = 'C:\Program Files\SIMULIA\EstProducts\2026'

if (-not (Test-Path "$root\InstallData\Installed.cmp")) {
    $p = Start-Process -FilePath $setup -ArgumentList '--silent', "`"$xml`"" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "setup.exe exited with $($p.ExitCode)" }
    # setup.exe may hand off to a child process: wait for Installed.cmp (written after registry.json)
    for ($i = 0; $i -lt 360 -and -not (Test-Path "$root\InstallData\Installed.cmp"); $i++) { Start-Sleep 10 }
    if (-not (Test-Path "$root\InstallData\Installed.cmp")) { throw 'install did not finish in 60 min' }
}

# DSLS license server file, same format as on the host Windows install: host:port
$dir = 'C:\ProgramData\DassaultSystemes\Licenses'
New-Item $dir -ItemType Directory -Force | Out-Null
Set-Content -Path "$dir\DSLicSrv.txt" -Value "${LicenseHost}:${LicensePort}" -NoNewline -Encoding ascii

# make `abaqus` resolvable for new ssh sessions
$cmds = 'C:\Program Files\SIMULIA\Commands'
$path = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if ($path -notlike "*$cmds*") { [Environment]::SetEnvironmentVariable('Path', "$path;$cmds", 'Machine') }

& "$cmds\abaqus.bat" information=release
