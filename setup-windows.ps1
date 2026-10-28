# abaqus-mcp setup for native Windows, for the current user; no admin rights needed.
# Start it through setup-windows.cmd (double-click, or type setup-windows in a terminal in this
# folder). Every step can run again: a step that is already done prints "already".
#   1. uv (runs the Python server): found, or installed per user after a question
#   2. config.local.toml with commented examples (if missing); uv sync: Python packages into .venv
#   3. live plug-in: %USERPROFILE%\abaqus_plugins\mcp_live, live folders under the work folder
#   4. skill: %USERPROFILE%\.claude\skills\abaqus-modelling
#   5. Claude Code: registers the MCP server "abaqus" at user scope, when claude is installed
#   6. doctor: uv run abaqus-mcp --check
$Repo = $PSScriptRoot

function Say($state, $text) { Write-Host ("{0,-8} {1}" -f $state, $text) }

function Sync-File($src, $dst) {
    # copy when missing or different; $true when copied
    if ((Test-Path -LiteralPath $dst) -and
        ((Get-FileHash -LiteralPath $src).Hash -eq (Get-FileHash -LiteralPath $dst).Hash)) { return $false }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
    return $true
}

function Find-Exe($name) {
    # on PATH, else the per-user folder where the uv and Claude Code installers put it
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Join-Path $env:USERPROFILE ".local\bin\$name.exe"
    if (Test-Path -LiteralPath $p) { return $p }
    return $null
}

Write-Host "abaqus-mcp setup in $Repo"
Write-Host ''

# 1. uv
$uv = Find-Exe 'uv'
if ($uv) {
    Say 'already' "uv: $uv"
} else {
    $a = Read-Host 'uv (the tool that runs the Python server) is not installed. Install it for your user now? [Y/n]'
    if ($a -and $a -notmatch '^[Yy]') {
        Say 'STOP' 'install uv from https://docs.astral.sh/uv/getting-started/installation/ and run this setup again'
        exit 1
    }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
    $uv = Find-Exe 'uv'
    if (-not $uv) {
        Say 'STOP' 'uv did not install (no internet, or a blocked download). Install it by hand from https://docs.astral.sh/uv/getting-started/installation/ and run this setup again'
        exit 1
    }
    Say 'done' "uv: $uv"
}

# 2. Python packages, and a config file to edit later (all values are optional on Windows)
$conf = Join-Path $Repo 'config.local.toml'
if (-not (Test-Path -LiteralPath $conf)) {
    Set-Content -LiteralPath $conf -Encoding ASCII -Value @(
        '# abaqus-mcp settings for this PC. Every line is optional: remove the # to use one, save,',
        '# and run setup-windows.cmd again. Open it with: notepad config.local.toml',
        '# abaqus_cmd = ''C:\SIMULIA\Commands\abaqus.bat''   # path from `where.exe abaqus`',
        '# license_host = "licence.server.example"          # when the licence line of the check says so',
        '# license_port = 4085',
        '# work_vm = ''D:\abaqus-work''                      # Abaqus work folder: no spaces or accents')
    Say 'done' "config: $conf (all lines commented out)"
} else {
    Say 'already' "config: $conf"
}
& $uv sync --check --quiet --directory $Repo 2>$null
if ($LASTEXITCODE -eq 0) {
    Say 'already' 'uv sync: Python packages in .venv'
} else {
    & $uv sync --quiet --directory $Repo
    if ($LASTEXITCODE -ne 0) { Say 'STOP' "uv sync failed (exit $LASTEXITCODE); see the lines above"; exit 1 }
    Say 'done' 'uv sync: Python packages in .venv'
}
$cfg = (& $uv run --quiet --directory $Repo python -m abaqus_mcp.config --json) | ConvertFrom-Json
if (-not $cfg) { Say 'STOP' 'cannot read the configuration (config.local.toml?)'; exit 1 }
if ($cfg.transport -ne 'local') { Say 'NOTE' "transport is '$($cfg.transport)' in config.local.toml; native Windows needs 'local'" }

# 3. live plug-in (cae_live: Claude edits the model in an open CAE window)
$plug = Join-Path $env:USERPROFILE 'abaqus_plugins\mcp_live'
$live = Join-Path $cfg.work_vm 'live'
try {
    $n = 0
    foreach ($f in 'mcp_live_plugin.py', 'mcp_live_core.py', 'mcp_live_kernel.py') {
        if (Sync-File (Join-Path $Repo "vm\plugin\$f") (Join-Path $plug $f)) { $n++ }
    }
    $txt = Join-Path $plug 'live_dir.txt'
    if (-not (Test-Path -LiteralPath $txt) -or (Get-Content -LiteralPath $txt -TotalCount 1) -ne $live) {
        Set-Content -LiteralPath $txt -Value $live -Encoding ASCII -ErrorAction Stop; $n++
    }
    foreach ($d in 'inbox', 'outbox', 'log') {
        $p = Join-Path $live $d
        if (-not (Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Force -Path $p -ErrorAction Stop | Out-Null; $n++ }
    }
    if ($n) { Say 'done' "live plug-in: $plug (live folder $live); restart Abaqus/CAE if it is open" }
    else { Say 'already' "live plug-in: $plug (live folder $live)" }
} catch {
    Say 'FAIL' "live plug-in: $($_.Exception.Message)"
    Say '' "if the work folder $($cfg.work_vm) cannot be created, set work_vm in config.local.toml (see README)"
}

# 4. skill
$skill = Join-Path $env:USERPROFILE '.claude\skills\abaqus-modelling'
$src = Join-Path $Repo 'skills\abaqus-modelling'
$n = 0
Get-ChildItem -LiteralPath $src -Recurse -File | ForEach-Object {
    if (Sync-File $_.FullName (Join-Path $skill $_.FullName.Substring($src.Length + 1))) { $n++ }
}
if ($n) { Say 'done' "skill: $skill ($n files copied)" } else { Say 'already' "skill: $skill" }

# 5. Claude Code registration (user scope: every folder sees the server)
$claude = Find-Exe 'claude'
if (-not $claude) {
    Say 'LATER' 'Claude Code not found (claude). Install it (README, step 1), open a new terminal and run this setup again.'
} else {
    $reg = $null
    try {
        $j = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $env:USERPROFILE '.claude.json') -ErrorAction Stop | ConvertFrom-Json
        $reg = $j.mcpServers.abaqus
    } catch { }
    if ($reg -and $reg.command -eq $uv -and ($reg.args -contains $Repo)) {
        Say 'already' 'Claude Code: MCP server "abaqus" registered (user scope)'
    } else {
        if ($reg -or -not $j) { & $claude mcp remove -s user abaqus 2>$null | Out-Null }
        & $claude mcp add -s user abaqus -- $uv run --directory $Repo abaqus-mcp
        if ($LASTEXITCODE -eq 0) { Say 'done' 'Claude Code: MCP server "abaqus" registered (user scope)' }
        else { Say 'FAIL' "Claude Code: claude mcp add failed (exit $LASTEXITCODE)" }
    }
}

# 6. doctor
Write-Host ''
Write-Host 'Checking the setup (uv run abaqus-mcp --check):'
& $uv run --quiet --directory $Repo abaqus-mcp --check
$rc = $LASTEXITCODE
Write-Host ''
if ($rc -eq 0) {
    Write-Host 'Setup finished. Next: open a NEW terminal, go to a folder for your analysis and type: claude'
} else {
    Write-Host 'Setup finished with problems: fix the FAIL lines above (README, Troubleshooting), then run this setup again.'
}
exit $rc
