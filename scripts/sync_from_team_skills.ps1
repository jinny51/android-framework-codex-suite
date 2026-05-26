param(
    [string]$SourceRoot
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $SourceRoot) {
    $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
    $SourceRoot = Join-Path $CodexHome "team-skills"
}

function Should-Exclude([System.IO.FileSystemInfo]$Item) {
    return $Item.Name -eq "config.toml" -or
        $Item.Name -eq "__pycache__" -or
        $Item.Name -eq ".pytest_cache" -or
        $Item.Name -eq ".DS_Store" -or
        $Item.Name -like "*.log" -or
        $Item.Name -like "*.pem" -or
        $Item.Name -like "*.key" -or
        $Item.Name -like "*password*" -or
        $Item.Name -like "*credential*" -or
        $Item.Extension -eq ".pyc" -or
        $Item.Extension -eq ".pyo"
}

function Copy-Tree([string]$From, [string]$To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    Get-ChildItem -LiteralPath $From -Force | ForEach-Object {
        if (-not (Should-Exclude $_)) {
            $dest = Join-Path $To $_.Name
            if ($_.PSIsContainer) {
                Copy-Tree -From $_.FullName -To $dest
            } else {
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
            }
        }
    }
}

function Sync-Skill([string]$Name, [string]$Plugin) {
    $source = Join-Path $SourceRoot $Name
    $target = Join-Path $RepoRoot "plugins/$Plugin/skills/$Name"

    if (-not (Test-Path -LiteralPath (Join-Path $source "SKILL.md"))) {
        throw "Missing source skill: $source"
    }

    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Get-ChildItem -LiteralPath $target -Force | Remove-Item -Recurse -Force
    Copy-Tree -From $source -To $target
}

$AndroidSkills = @(
    "android-framework-change-workflow",
    "android-framework-patch-capture",
    "android-knowledge-search",
    "android-knowledge-intake",
    "android-remote-channel",
    "android-wsl-source-access",
    "android-wsl-remote-build-deploy",
    "android-windows-source-access",
    "android-windows-remote-build-deploy"
)

$WorkspaceCareSkills = @(
    "codex-chat-history-cleaner",
    "codex-chat-history-context-extractor"
)

foreach ($name in $AndroidSkills) {
    Sync-Skill -Name $name -Plugin "android-framework-ops"
}

foreach ($name in $WorkspaceCareSkills) {
    Sync-Skill -Name $name -Plugin "codex-workspace-care"
}

function Convert-ToWslPath([string]$Path) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $tail = $Matches[2] -replace '\\', '/'
        return "/mnt/$drive/$tail"
    }
    throw "Unsupported path for WSL conversion: $Path"
}

function Invoke-PythonScript([string]$ScriptPath) {
    $Python = Get-Command python3 -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source $ScriptPath
        return
    }

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source $ScriptPath
        return
    }

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & $PyLauncher.Source -3 $ScriptPath
        return
    }

    $Wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($Wsl) {
        & $Wsl.Source python3 (Convert-ToWslPath $ScriptPath)
        return
    }

    throw "Python was not found. Install python3, python, py launcher, or WSL with python3."
}

Invoke-PythonScript -ScriptPath (Join-Path $RepoRoot "scripts/apply_plugin_overrides.py")

Write-Host "Synced team skills from $SourceRoot"
