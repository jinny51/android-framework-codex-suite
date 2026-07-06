param(
    [Parameter(Position = 0)]
    [ValidateSet("init", "list", "add", "resolve")]
    [string]$Command = "list",

    [string]$LocalRepo,
    [string]$SmbRoot,
    [string]$SshHost,
    [string]$RemoteRoot,
    [string]$Platform,
    [string]$SdkName,
    [string]$SambaUser,
    [string]$CredentialTarget,
    [string]$SambaPassword
)

$ErrorActionPreference = "Stop"

$InfoDir = Join-Path $env:USERPROFILE ".codex\android-windows-source-access-info"
$CredentialsDir = Join-Path $InfoDir "credentials"
$ProjectsDir = Join-Path $InfoDir "projects"

function Ensure-Store {
    New-Item -ItemType Directory -Force -Path $InfoDir | Out-Null
    New-Item -ItemType Directory -Force -Path $CredentialsDir | Out-Null
    New-Item -ItemType Directory -Force -Path $ProjectsDir | Out-Null
}

function Normalize-PathValue([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    return $Value.Trim().TrimEnd("\", "/")
}

function Require-Value([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Missing required parameter: -$Name"
    }
}

function Get-SmbServer([string]$SmbPath) {
    $value = Normalize-PathValue $SmbPath
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    if ($value.StartsWith("\\")) {
        return (($value.Substring(2)) -split "\\")[0]
    }
    if ($value.StartsWith("//")) {
        return (($value.Substring(2)) -split "/")[0]
    }
    return $null
}

function ConvertTo-SmbUrl([string]$SmbPath) {
    $value = Normalize-PathValue $SmbPath
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    if ($value.StartsWith("\\")) {
        return "//" + $value.Substring(2).Replace("\", "/")
    }
    return $value
}

function ConvertTo-WindowsSmbPath([string]$SmbUrl) {
    $value = Normalize-PathValue $SmbUrl
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    if ($value.StartsWith("//")) {
        return "\\" + $value.Substring(2).Replace("/", "\")
    }
    return $value
}

function Get-AccountKey([string]$User, [string]$Server) {
    Require-Value "SambaUser" $User
    Require-Value "CredentialTarget" $Server
    $text = "$User@$Server"
    $sha = [System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($text))
    return -join ($sha | ForEach-Object { $_.ToString("x2") })
}

function Quote-EnvValue([string]$Value) {
    if ($null -eq $Value) { return "''" }
    return "'" + $Value.Replace("'", "'\''") + "'"
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
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($match in [regex]::Matches($body, "'([^']*)'|(\S+)")) {
        if ($match.Groups[1].Success) {
            $items.Add($match.Groups[1].Value.Replace("'\''", "'"))
        } elseif ($match.Groups[2].Success) {
            $items.Add($match.Groups[2].Value)
        }
    }
    return @($items)
}

function Read-AccountEnv([string]$Path) {
    $state = [ordered]@{
        SAMBA_SERVER = $null
        SAMBA_USER = $null
        SAMBA_CREDENTIALS_FILE = $null
        PROJECT_PATHS = @()
        SAMBA_PROJECT_SHARES = @()
        WINDOWS_SMB_PATHS = @()
        PREFERRED_VERS_LIST = @()
        REMOTE_SSH_HOSTS = @()
        REMOTE_ROOTS = @()
        PLATFORMS = @()
        SDK_NAMES = @()
    }
    if (-not (Test-Path -LiteralPath $Path)) { return $state }

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match "^(SAMBA_SERVER|SAMBA_USER|SAMBA_CREDENTIALS_FILE)=(.*)$") {
            $state[$matches[1]] = Unquote-EnvValue $matches[2]
        } elseif ($line -match "^(PROJECT_PATHS|SAMBA_PROJECT_SHARES|WINDOWS_SMB_PATHS|PREFERRED_VERS_LIST|REMOTE_SSH_HOSTS|REMOTE_ROOTS|PLATFORMS|SDK_NAMES)=\(") {
            $name = $matches[1]
            $state[$name] = @(Parse-ArrayAssignment $line)
        }
    }
    return $state
}

function Convert-StateToProjects($State) {
    $projects = @()
    $count = @($State.PROJECT_PATHS).Count
    for ($i = 0; $i -lt $count; $i++) {
        $smbUrl = @($State.SAMBA_PROJECT_SHARES)[$i]
        $windowsSmb = @($State.WINDOWS_SMB_PATHS)[$i]
        if ([string]::IsNullOrWhiteSpace($windowsSmb)) {
            $windowsSmb = ConvertTo-WindowsSmbPath $smbUrl
        }
        $projects += [pscustomobject]@{
            localRepo = @($State.PROJECT_PATHS)[$i]
            smbRoot = $windowsSmb
            smbUrl = $smbUrl
            sshHost = @($State.REMOTE_SSH_HOSTS)[$i]
            remoteRoot = @($State.REMOTE_ROOTS)[$i]
            platform = @($State.PLATFORMS)[$i]
            sdkName = @($State.SDK_NAMES)[$i]
            sambaUser = $State.SAMBA_USER
            credentialTarget = $State.SAMBA_SERVER
            credentialsFile = $State.SAMBA_CREDENTIALS_FILE
        }
    }
    return $projects
}

function Read-AllProjects {
    Ensure-Store
    $all = @()
    foreach ($file in Get-ChildItem -LiteralPath $ProjectsDir -Filter "*.env" -File -ErrorAction SilentlyContinue) {
        $state = Read-AccountEnv $file.FullName
        foreach ($project in Convert-StateToProjects $state) {
            $project | Add-Member -NotePropertyName registry -NotePropertyValue $file.FullName -Force
            $all += $project
        }
    }
    return $all
}

function Write-CredentialFile([string]$User, [string]$Password, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Password)) { return }
    @(
        "username=$User"
        "password=$Password"
    ) | Set-Content -LiteralPath $Path -Encoding UTF8
    icacls.exe $Path /inheritance:r /grant "$($env:USERNAME):(F)" | Out-Null
}

function Write-AccountEnv([array]$Projects, [string]$User, [string]$Server) {
    $key = Get-AccountKey $User $Server
    $credFile = Join-Path $CredentialsDir "$key.cred"
    $projectFile = Join-Path $ProjectsDir "$key.env"
    $accountProjects = @($Projects | Where-Object {
        $_.sambaUser -eq $User -and $_.credentialTarget -eq $Server
    })

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("SAMBA_SERVER=$Server")
    $lines.Add("SAMBA_USER=$User")
    if (Test-Path -LiteralPath $credFile) {
        $lines.Add("SAMBA_CREDENTIALS_FILE=$(Quote-EnvValue $credFile)")
    }
    $lines.Add("PROJECT_PATHS=( $((@($accountProjects | ForEach-Object { Quote-EnvValue $_.localRepo })) -join ' ') )")
    $lines.Add("SAMBA_PROJECT_SHARES=( $((@($accountProjects | ForEach-Object { Quote-EnvValue (ConvertTo-SmbUrl $_.smbRoot) })) -join ' ') )")
    $lines.Add("WINDOWS_SMB_PATHS=( $((@($accountProjects | ForEach-Object { Quote-EnvValue $_.smbRoot })) -join ' ') )")
    $lines.Add("PREFERRED_VERS_LIST=( $((@($accountProjects | ForEach-Object { '3.0' })) -join ' ') )")
    $lines.Add("REMOTE_SSH_HOSTS=( $((@($accountProjects | ForEach-Object { Quote-EnvValue $_.sshHost })) -join ' ') )")
    $lines.Add("REMOTE_ROOTS=( $((@($accountProjects | ForEach-Object { Quote-EnvValue $_.remoteRoot })) -join ' ') )")
    $lines.Add("PLATFORMS=( $((@($accountProjects | ForEach-Object { Quote-EnvValue $_.platform })) -join ' ') )")
    $lines.Add("SDK_NAMES=( $((@($accountProjects | ForEach-Object { Quote-EnvValue $_.sdkName })) -join ' ') )")
    $lines | Set-Content -LiteralPath $projectFile -Encoding UTF8
    return $projectFile
}

switch ($Command) {
    "init" {
        Ensure-Store
        [ordered]@{ infoDir = $InfoDir; credentialsDir = $CredentialsDir; projectsDir = $ProjectsDir; status = "ok" } | ConvertTo-Json
    }

    "list" {
        [ordered]@{ projects = @(Read-AllProjects) } | ConvertTo-Json -Depth 8
    }

    "add" {
        Require-Value "LocalRepo" $LocalRepo
        Require-Value "SmbRoot" $SmbRoot
        Require-Value "SshHost" $SshHost
        Require-Value "RemoteRoot" $RemoteRoot
        Require-Value "SambaUser" $SambaUser

        Ensure-Store
        $server = if ($CredentialTarget) { $CredentialTarget.Trim() } else { Get-SmbServer $SmbRoot }
        Require-Value "CredentialTarget" $server
        $key = Get-AccountKey $SambaUser.Trim() $server
        $credFile = Join-Path $CredentialsDir "$key.cred"
        Write-CredentialFile $SambaUser.Trim() $SambaPassword $credFile

        $projects = @()
        foreach ($project in Read-AllProjects) {
            if ((Normalize-PathValue $project.localRepo) -ine (Normalize-PathValue $LocalRepo) -and
                (Normalize-PathValue $project.remoteRoot) -ne (Normalize-PathValue $RemoteRoot)) {
                $projects += $project
            }
        }

        $entry = [pscustomobject]@{
            localRepo = Normalize-PathValue $LocalRepo
            smbRoot = Normalize-PathValue $SmbRoot
            smbUrl = ConvertTo-SmbUrl $SmbRoot
            sshHost = $SshHost.Trim()
            remoteRoot = Normalize-PathValue $RemoteRoot
            platform = if ($Platform) { $Platform.Trim() } else { "" }
            sdkName = if ($SdkName) { $SdkName.Trim() } else { "" }
            sambaUser = $SambaUser.Trim()
            credentialTarget = $server
            credentialsFile = if (Test-Path -LiteralPath $credFile) { $credFile } else { $null }
        }
        $projects += $entry
        $registry = Write-AccountEnv $projects $entry.sambaUser $entry.credentialTarget
        $entry | Add-Member -NotePropertyName registry -NotePropertyValue $registry -Force
        $entry | ConvertTo-Json -Depth 8
    }

    "resolve" {
        $local = Normalize-PathValue $LocalRepo
        $remote = Normalize-PathValue $RemoteRoot
        $sdk = if ($SdkName) { $SdkName.Trim() } else { $null }
        $matches = @(Read-AllProjects | Where-Object {
            (($local -and (Normalize-PathValue $_.localRepo) -ieq $local) -or
             ($remote -and (Normalize-PathValue $_.remoteRoot) -eq $remote) -or
             ($sdk -and $_.sdkName -ieq $sdk))
        })
        if ($matches.Count -eq 0) {
            throw "No matching Android SMB Windows mapping found."
        }
        if ($matches.Count -gt 1) {
            throw "Multiple matching mappings found; specify -LocalRepo or -RemoteRoot."
        }
        $matches[0] | ConvertTo-Json -Depth 8
    }
}
