param(
    [Parameter(Mandatory = $true)]
    [string]$SshHost,

    [Parameter(Mandatory = $true)]
    [string]$RemoteRoot,

    [Parameter(Mandatory = $true)]
    [ValidateSet("check", "install-tmux", "ensure", "run", "status", "tail", "stop")]
    [string]$Action,

    [string]$Command,

    [ValidateSet("none", "exclusive")]
    [string]$Lock = "none",

    [switch]$NoWait,

    [string]$CommandId,

    [int]$Lines = 120,

    [string]$SudoPasswordEnv = "CODEX_REMOTE_SUDO_PASSWORD"
)

$ErrorActionPreference = "Stop"
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $script:Utf8NoBom

function ConvertTo-ShellSingleQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + ($Value -replace "'", "'\''") + "'"
}

function ConvertTo-WindowsProcessArgument {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return '""' }
    if ($Value.Length -eq 0) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($char in $Value.ToCharArray()) {
        if ($char -eq '\') {
            $backslashes++
        } elseif ($char -eq '"') {
            [void]$builder.Append('\' * (($backslashes * 2) + 1))
            [void]$builder.Append('"')
            $backslashes = 0
        } else {
            if ($backslashes -gt 0) {
                [void]$builder.Append('\' * $backslashes)
                $backslashes = 0
            }
            [void]$builder.Append($char)
        }
    }
    if ($backslashes -gt 0) {
        [void]$builder.Append('\' * ($backslashes * 2))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Join-WindowsProcessArguments {
    param([string[]]$Values)
    return (@($Values | ForEach-Object { ConvertTo-WindowsProcessArgument $_ }) -join " ")
}

function New-SshProcessStartInfo {
    param([Parameter(Mandatory = $true)][string]$RemoteCommand)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "ssh.exe"
    $psi.Arguments = Join-WindowsProcessArguments @("-o", "BatchMode=no", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", $SshHost, $RemoteCommand)
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = $script:Utf8NoBom
    $psi.StandardErrorEncoding = $script:Utf8NoBom
    return $psi
}

function Get-SessionHash {
    param([Parameter(Mandatory = $true)][string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $hashBytes = $sha.ComputeHash($bytes)
        $hex = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
        return $hex.Substring(0, 12)
    } finally {
        $sha.Dispose()
    }
}

function Invoke-Ssh {
    param([Parameter(Mandatory = $true)][string]$RemoteCommand)
    & ssh.exe -o BatchMode=no -o ConnectTimeout=8 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 $SshHost $RemoteCommand
    $script:LastSshExitCode = $LASTEXITCODE
}

function Invoke-SshWithStdin {
    param(
        [Parameter(Mandatory = $true)][string]$RemoteCommand,
        [Parameter(Mandatory = $true)][string]$InputText
    )
    $psi = New-SshProcessStartInfo $RemoteCommand

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    $inputBytes = $script:Utf8NoBom.GetBytes($InputText)
    $process.StandardInput.BaseStream.Write($inputBytes, 0, $inputBytes.Length)
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($stdout) { Write-Output $stdout.TrimEnd() }
    if ($stderr) { Write-Error $stderr.TrimEnd() }
    $script:LastSshExitCode = $process.ExitCode
}

function Invoke-SshCapture {
    param(
        [Parameter(Mandatory = $true)][string]$RemoteCommand,
        [string]$InputText
    )
    $psi = New-SshProcessStartInfo $RemoteCommand

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    if ($null -ne $InputText) {
        $inputBytes = $script:Utf8NoBom.GetBytes($InputText)
        $process.StandardInput.BaseStream.Write($inputBytes, 0, $inputBytes.Length)
    }
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $stdoutText = if ($null -ne $stdout) { $stdout.TrimEnd() } else { "" }
    $stderrText = if ($null -ne $stderr) { $stderr.TrimEnd() } else { "" }
    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Stdout = $stdoutText
        Stderr = $stderrText
    }
}

function Write-CapturedSshOutput {
    param([Parameter(Mandatory = $true)]$Result)
    if ($Result.Stdout) { Write-Output $Result.Stdout }
    if ($Result.Stderr) { [Console]::Error.WriteLine($Result.Stderr) }
}

if (-not $RemoteRoot.StartsWith("/")) {
    throw "RemoteRoot must be an absolute Linux path."
}
if ($Lines -lt 1) {
    throw "Lines must be positive."
}

$sessionHash = Get-SessionHash "$SshHost|$RemoteRoot"
$sessionName = "codex-android-$sessionHash"
$stateDirRel = ".codex/android-remote-sessions/$sessionHash"
$stateDirDisplay = "`$HOME/$stateDirRel"

function Get-RemoteTmuxInstallBody {
@'
set -e
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y tmux
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y tmux
elif command -v yum >/dev/null 2>&1; then
  yum install -y tmux
elif command -v zypper >/dev/null 2>&1; then
  zypper --non-interactive install tmux
else
  echo 'PACKAGE_MANAGER_UNSUPPORTED install tmux manually' >&2
  exit 11
fi
'@
}

function Get-RemoteTmuxInstallCommand {
    param([switch]$WithPassword)
    $installBodyQ = ConvertTo-ShellSingleQuoted (Get-RemoteTmuxInstallBody)
    if ($WithPassword) {
@"
set -e
if command -v tmux >/dev/null 2>&1; then
  printf 'TMUX_OK path=%s\n' "`$(command -v tmux)"
  tmux -V
  exit 0
fi
command -v sudo >/dev/null 2>&1 || { echo 'SUDO_MISSING install tmux manually' >&2; exit 13; }
if ! sudo -S -p '' -v >/dev/null 2>&1; then
  echo 'REMOTE_SUDO_AUTH_FAILED' >&2
  exit 12
fi
sudo -n sh -c $installBodyQ
printf 'TMUX_INSTALLED version=%s path=%s\n' "`$(tmux -V)" "`$(command -v tmux)"
"@
    } else {
@"
set -e
if command -v tmux >/dev/null 2>&1; then
  printf 'TMUX_OK path=%s\n' "`$(command -v tmux)"
  tmux -V
  exit 0
fi
command -v sudo >/dev/null 2>&1 || { echo 'SUDO_MISSING install tmux manually' >&2; exit 13; }
if ! sudo -n true >/dev/null 2>&1; then
  echo 'REMOTE_SUDO_PASSWORD_REQUIRED env=$SudoPasswordEnv action=install_tmux' >&2
  exit 10
fi
sudo -n sh -c $installBodyQ
printf 'TMUX_INSTALLED version=%s path=%s\n' "`$(tmux -V)" "`$(command -v tmux)"
"@
    }
}

function Normalize-RemoteRootValue {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "" }
    return $Value.Trim().TrimEnd("/")
}

function Find-WindowsSourceAccessManager {
    $candidates = @(
        (Join-Path $PSScriptRoot "..\..\android-windows-source-access\scripts\Manage-AndroidSmbWindowsInfo.ps1"),
        (Join-Path $env:USERPROFILE ".codex\skills\android-windows-source-access\scripts\Manage-AndroidSmbWindowsInfo.ps1")
    )
    foreach ($candidate in $candidates) {
        $full = [System.IO.Path]::GetFullPath($candidate)
        if (Test-Path -LiteralPath $full) { return $full }
    }
    return $null
}

function Read-CredentialPassword {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match "^password=(.*)$") {
            return $matches[1].TrimEnd("`r")
        }
    }
    return $null
}

function Get-WindowsSourceAccessPasswordCandidates {
    $manager = Find-WindowsSourceAccessManager
    if (-not $manager) { return @() }

    $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager list
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return @() }

    $data = $raw | ConvertFrom-Json
    $projects = @($data.projects)
    $remoteRootNorm = Normalize-RemoteRootValue $RemoteRoot
    $matches = @($projects | Where-Object {
        (Normalize-RemoteRootValue $_.remoteRoot) -eq $remoteRootNorm -and
        ([string]::IsNullOrWhiteSpace($_.sshHost) -or $_.sshHost -eq $SshHost -or ($_.sshHost -replace "^.*@", "") -eq ($SshHost -replace "^.*@", ""))
    })

    $candidates = @()
    foreach ($project in $matches) {
        $password = Read-CredentialPassword $project.credentialsFile
        if (-not [string]::IsNullOrEmpty($password)) {
            $candidates += [pscustomobject]@{
                Source = "source-access:SAMBA_CREDENTIALS_FILE"
                Password = $password
            }
        }
    }
    return $candidates
}

function Try-TmuxPasswordCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [string]$Password
    )
    if ([string]::IsNullOrEmpty($Password)) { return $false }
    $result = Invoke-SshCapture (Get-RemoteTmuxInstallCommand -WithPassword) ($Password + "`n")
    if ($result.ExitCode -eq 0) {
        Write-CapturedSshOutput $result
        Write-Output "TMUX_INSTALL_AUTH source=$Source"
        return $true
    }
    if ($result.ExitCode -eq 12) {
        return $false
    }
    Write-CapturedSshOutput $result
    exit $result.ExitCode
}

function Install-Tmux {
    if ([string]::IsNullOrWhiteSpace($SudoPasswordEnv)) {
        throw "SudoPasswordEnv must not be empty."
    }

    $result = Invoke-SshCapture (Get-RemoteTmuxInstallCommand)
    if ($result.ExitCode -eq 0) {
        Write-CapturedSshOutput $result
        Write-Output "TMUX_INSTALL_AUTH source=passwordless-or-existing"
        return
    }
    if ($result.ExitCode -ne 10) {
        Write-CapturedSshOutput $result
        exit $result.ExitCode
    }

    $envPassword = [Environment]::GetEnvironmentVariable($SudoPasswordEnv)
    if (Try-TmuxPasswordCandidate "env:$SudoPasswordEnv" $envPassword) { return }

    foreach ($candidate in Get-WindowsSourceAccessPasswordCandidates) {
        if (Try-TmuxPasswordCandidate $candidate.Source $candidate.Password) { return }
    }

    [Console]::Error.WriteLine("REMOTE_SUDO_PASSWORD_REQUIRED env=$SudoPasswordEnv action=install_tmux")
    exit 10
}

function Test-Channel {
    $remoteRootQ = ConvertTo-ShellSingleQuoted $RemoteRoot
    $cmd = @"
set -e
printf 'SSH_OK host=%s\n' '$SshHost'
command -v tmux >/dev/null 2>&1 || { echo 'TMUX_MISSING install tmux on remote host' >&2; exit 127; }
printf 'TMUX_OK path=%s\n' "`$(command -v tmux)"
test -d $remoteRootQ || { echo 'REMOTE_ROOT_MISSING $RemoteRoot' >&2; exit 2; }
printf 'REMOTE_ROOT_OK path=%s\n' '$RemoteRoot'
"@
    Invoke-Ssh $cmd
    if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }
}

function Ensure-Session {
    $sessionQ = ConvertTo-ShellSingleQuoted $sessionName
    $remoteRootQ = ConvertTo-ShellSingleQuoted $RemoteRoot
    $cmd = @"
set -e
command -v tmux >/dev/null 2>&1 || { echo 'TMUX_MISSING install tmux on remote host' >&2; exit 127; }
test -d $remoteRootQ || { echo 'REMOTE_ROOT_MISSING $RemoteRoot' >&2; exit 2; }
state_dir="`$HOME/$stateDirRel"
mkdir -p "`$state_dir/commands"
cat >"`$state_dir/session.env" <<EOF
SESSION_NAME=$sessionName
SSH_HOST=$SshHost
REMOTE_ROOT=$RemoteRoot
STATE_DIR=`$state_dir
EOF
if ! tmux has-session -t $sessionQ 2>/dev/null; then
  tmux new-session -d -s $sessionQ -c $remoteRootQ
  tmux send-keys -t $sessionQ -l "cd $remoteRootQ"
  tmux send-keys -t $sessionQ C-m
fi
echo "SESSION_OK name=$sessionName state=`$state_dir remote=$RemoteRoot"
"@
    Invoke-Ssh $cmd
    if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }
}

function Get-Status {
    $sessionQ = ConvertTo-ShellSingleQuoted $sessionName
    $cmd = @"
state_dir="`$HOME/$stateDirRel"
if tmux has-session -t $sessionQ 2>/dev/null; then
  echo "SESSION_STATUS running name=$sessionName state=`$state_dir"
else
  echo "SESSION_STATUS stopped name=$sessionName state=`$state_dir"
fi
if [ -f "`$state_dir/busy" ]; then
  printf 'BUSY '
  cat "`$state_dir/busy"
  echo
else
  echo 'BUSY none'
fi
if [ -L "`$state_dir/current.log" ] || [ -f "`$state_dir/current.log" ]; then
  echo "CURRENT_LOG=`$state_dir/current.log"
fi
"@
    Invoke-Ssh $cmd
    if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }
}

function Stop-Session {
    $sessionQ = ConvertTo-ShellSingleQuoted $sessionName
    $cmd = @"
if tmux has-session -t $sessionQ 2>/dev/null; then
  tmux kill-session -t $sessionQ
  echo "SESSION_STOPPED name=$sessionName"
else
  echo "SESSION_ALREADY_STOPPED name=$sessionName"
fi
"@
    Invoke-Ssh $cmd
    if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }
}

function Tail-Log {
    if ($CommandId) {
        $logPath = "`$HOME/$stateDirRel/commands/$CommandId.log"
    } else {
        $logPath = "`$HOME/$stateDirRel/current.log"
    }
    $cmd = @"
log=$logPath
if [ ! -e "`$log" ]; then
  echo "LOG_MISSING `$log" >&2
  exit 2
fi
tail -n $Lines "`$log"
"@
    Invoke-Ssh $cmd
    if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }
}

function Run-Command {
    if (-not $Command) {
        throw "Action run requires -Command."
    }
    if (-not $CommandId) {
        $script:CommandId = (Get-Date -Format "yyyyMMdd-HHmmss") + "-$PID"
    }

    Ensure-Session | Out-Null

    $busyQ = ConvertTo-ShellSingleQuoted "$stateDirDisplay/busy"
    Invoke-Ssh "test -f $busyQ" | Out-Null
    if ($script:LastSshExitCode -eq 0) {
        Write-Error "SESSION_BUSY name=$sessionName state=$stateDirDisplay"
        exit 3
    }

    $lineFile = "`$HOME/$stateDirRel/commands/$CommandId.line"
    $logFile = "`$HOME/$stateDirRel/commands/$CommandId.log"
    $exitFile = "`$HOME/$stateDirRel/commands/$CommandId.exit"
    $lockFile = "`$HOME/$stateDirRel/project.lock"
    $remoteRootQ = ConvertTo-ShellSingleQuoted $RemoteRoot
    $commandIdQ = ConvertTo-ShellSingleQuoted $CommandId

    $lockPrefix = ""
    $lockSuffix = ""
    if ($Lock -eq "exclusive") {
        $lockPrefix = "exec 9>`"$lockFile`"; flock 9; "
        $lockSuffix = "; flock -u 9"
    }

    $line = "__codex_cmd_id=$commandIdQ; __codex_log=`"$logFile`"; __codex_exit=`"$exitFile`"; __codex_busy=`"`$HOME/$stateDirRel/busy`"; rm -f `"`$__codex_exit`"; mkdir -p `"`$HOME/$stateDirRel/commands`"; printf '%s remote=$RemoteRoot\n' `"`$__codex_cmd_id`" > `"`$__codex_busy`"; ln -sfn `"`$__codex_log`" `"`$HOME/$stateDirRel/current.log`"; { cd $remoteRootQ; $lockPrefix{ $Command; }; __codex_rc=`$?$lockSuffix; } > `"`$__codex_log`" 2>&1; printf '%s\n' `"`$__codex_rc`" > `"`$__codex_exit`"; rm -f `"`$__codex_busy`"; printf '__CODEX_CMD_DONE id=%s rc=%s\n' `"`$__codex_cmd_id`" `"`$__codex_rc`" >> `"`$__codex_log`""

    Invoke-SshWithStdin "cat > `"$lineFile`"" $line
    if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }

    $sessionQ = ConvertTo-ShellSingleQuoted $sessionName
    Invoke-Ssh "tmux send-keys -t $sessionQ -l `"$(cat `"$lineFile`")`" && tmux send-keys -t $sessionQ C-m"
    if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }

    Write-Output "COMMAND_STARTED id=$CommandId session=$sessionName log=$stateDirDisplay/commands/$CommandId.log"

    if (-not $NoWait) {
        $waitCmd = @"
exit_file="`$HOME/$stateDirRel/commands/$CommandId.exit"
log_file="`$HOME/$stateDirRel/commands/$CommandId.log"
while [ ! -f "`$exit_file" ]; do
  sleep 2
done
cat "`$log_file"
exit "`$(cat "`$exit_file")"
"@
        Invoke-Ssh $waitCmd
        if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }
    }
}

switch ($Action) {
    "check" { Test-Channel }
    "install-tmux" { Install-Tmux }
    "ensure" { Ensure-Session }
    "status" { Get-Status }
    "stop" { Stop-Session }
    "tail" { Tail-Log }
    "run" { Run-Command }
}
