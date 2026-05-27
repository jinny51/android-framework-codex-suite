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

$candidatePaths = @(
    (Join-Path $env:USERPROFILE ".codex\skills\android-windows-remote-channel\scripts\Invoke-AndroidRemoteChannel.ps1"),
    (Join-Path $PSScriptRoot "..\..\android-windows-remote-channel\scripts\Invoke-AndroidRemoteChannel.ps1")
)

$channelScript = $candidatePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $channelScript) {
    Write-Error "android-windows-remote-channel is not installed or not found. Expected one of: $($candidatePaths -join '; ')"
    exit 127
}

$arguments = @{
    SshHost = $SshHost
    RemoteRoot = $RemoteRoot
    Action = $Action
    Lock = $Lock
    Lines = $Lines
    SudoPasswordEnv = $SudoPasswordEnv
}
if ($Command) { $arguments.Command = $Command }
if ($NoWait) { $arguments.NoWait = $true }
if ($CommandId) { $arguments.CommandId = $CommandId }

& $channelScript @arguments
if ($null -ne $LASTEXITCODE) {
    exit $LASTEXITCODE
}
