param(
    [string]$LocalRepo,
    [string]$RemoteRoot,
    [string]$SdkName,
    [string]$ProjectsDir = "$env:USERPROFILE\.codex\android-windows-source-access-info\projects"
)

$ErrorActionPreference = "Stop"

function Normalize-PathValue([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    return $Value.Trim().TrimEnd("\", "/")
}

function Unquote-EnvValue([string]$Value) {
    if ($null -eq $Value) { return $null }
    $trimmed = $Value.Trim()
    if ($trimmed.Length -ge 2 -and $trimmed.StartsWith("'") -and $trimmed.EndsWith("'")) {
        return $trimmed.Substring(1, $trimmed.Length - 2).Replace("'\''", "'")
    }
    return $trimmed
}

function Parse-ArrayAssignment([string]$Line) {
    $body = ($Line -replace "^[^=]+=\(", "") -replace "\)\s*$", ""
    $items = @()
    foreach ($match in [regex]::Matches($body, "'([^']*)'|(\S+)")) {
        if ($match.Groups[1].Success) {
            $items += $match.Groups[1].Value.Replace("'\''", "'")
        } elseif ($match.Groups[2].Success) {
            $items += $match.Groups[2].Value
        }
    }
    return $items
}

function ConvertTo-WindowsSmbPath([string]$SmbUrl) {
    $value = Normalize-PathValue $SmbUrl
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    if ($value.StartsWith("//")) {
        return "\\" + $value.Substring(2).Replace("/", "\")
    }
    return $value
}

function Read-AccountEnv([string]$Path) {
    $state = [ordered]@{
        SAMBA_SERVER = $null
        SAMBA_USER = $null
        SAMBA_CREDENTIALS_FILE = $null
        PROJECT_PATHS = @()
        SAMBA_PROJECT_SHARES = @()
        WINDOWS_SMB_PATHS = @()
        REMOTE_SSH_HOSTS = @()
        REMOTE_ROOTS = @()
        PLATFORMS = @()
        SDK_NAMES = @()
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match "^(SAMBA_SERVER|SAMBA_USER|SAMBA_CREDENTIALS_FILE)=(.*)$") {
            $state[$matches[1]] = Unquote-EnvValue $matches[2]
        } elseif ($line -match "^(PROJECT_PATHS|SAMBA_PROJECT_SHARES|WINDOWS_SMB_PATHS|REMOTE_SSH_HOSTS|REMOTE_ROOTS|PLATFORMS|SDK_NAMES)=\(") {
            $state[$matches[1]] = @(Parse-ArrayAssignment $line)
        }
    }
    return $state
}

if (-not (Test-Path -LiteralPath $ProjectsDir)) {
    throw "Windows Android SMB mapping registry not found: $ProjectsDir"
}

$all = @()
foreach ($file in Get-ChildItem -LiteralPath $ProjectsDir -Filter "*.env" -File) {
    $state = Read-AccountEnv $file.FullName
    $count = @($state.PROJECT_PATHS).Count
    for ($i = 0; $i -lt $count; $i++) {
        $smbUrl = @($state.SAMBA_PROJECT_SHARES)[$i]
        $windowsSmb = @($state.WINDOWS_SMB_PATHS)[$i]
        if ([string]::IsNullOrWhiteSpace($windowsSmb)) {
            $windowsSmb = ConvertTo-WindowsSmbPath $smbUrl
        }
        $all += [pscustomobject]@{
            LOCAL_REPO = @($state.PROJECT_PATHS)[$i]
            SMB_ROOT = $windowsSmb
            SMB_URL = $smbUrl
            SSH_HOST = @($state.REMOTE_SSH_HOSTS)[$i]
            REMOTE_ROOT = @($state.REMOTE_ROOTS)[$i]
            PLATFORM = @($state.PLATFORMS)[$i]
            SDK_NAME = @($state.SDK_NAMES)[$i]
            SAMBA_SERVER = $state.SAMBA_SERVER
            SAMBA_USER = $state.SAMBA_USER
            SAMBA_CREDENTIALS_FILE = $state.SAMBA_CREDENTIALS_FILE
            MAPPING_REGISTRY = $file.FullName
        }
    }
}

$local = Normalize-PathValue $LocalRepo
$remote = Normalize-PathValue $RemoteRoot
$sdk = if ($SdkName) { $SdkName.Trim() } else { $null }

$matches = @($all | Where-Object {
    (($local -and (Normalize-PathValue $_.LOCAL_REPO) -ieq $local) -or
     ($remote -and (Normalize-PathValue $_.REMOTE_ROOT) -eq $remote) -or
     ($sdk -and $_.SDK_NAME -ieq $sdk))
})

if ($matches.Count -eq 0) {
    throw "No Windows Android SMB mapping matched the provided input."
}
if ($matches.Count -gt 1) {
    throw "Multiple mappings matched; specify -LocalRepo or -RemoteRoot."
}

$matches[0] | ConvertTo-Json -Depth 6
