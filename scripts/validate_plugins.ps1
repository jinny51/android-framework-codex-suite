$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$Validator = Join-Path $CodexHome "skills/.system/plugin-creator/scripts/validate_plugin.py"

if (-not (Test-Path -LiteralPath $Validator)) {
    throw "Plugin validator not found: $Validator"
}

function Convert-ToWslPath([string]$Path) {
    $resolvedInfo = Resolve-Path -LiteralPath $Path
    $resolved = if ($resolvedInfo.ProviderPath) {
        $resolvedInfo.ProviderPath
    } else {
        $resolvedInfo.Path -replace '^Microsoft\.PowerShell\.Core\\FileSystem::', ''
    }
    if ($resolved -match '^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.*)$') {
        $tail = $Matches[1] -replace '\\', '/'
        return "/$tail"
    }
    if ($resolved -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $tail = $Matches[2] -replace '\\', '/'
        return "/mnt/$drive/$tail"
    }
    throw "Unsupported path for WSL conversion: $Path"
}

function Invoke-PythonScript([string]$ScriptPath, [string[]]$Arguments) {
    $Python = Get-Command python3 -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source $ScriptPath @Arguments
        return
    }

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source $ScriptPath @Arguments
        return
    }

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & $PyLauncher.Source -3 $ScriptPath @Arguments
        return
    }

    $Wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($Wsl) {
        $wslScript = Convert-ToWslPath $ScriptPath
        $wslArgs = @()
        foreach ($arg in $Arguments) {
            if (Test-Path -LiteralPath $arg) {
                $wslArgs += Convert-ToWslPath $arg
            } else {
                $wslArgs += $arg
            }
        }
        & $Wsl.Source python3 $wslScript @wslArgs
        return
    }

    throw "Python was not found. Install python3, python, py launcher, or WSL with python3."
}

foreach ($plugin in @("android-framework-ops", "jinny-android-practices", "android-wsl-ops", "android-macos-ops", "codex-workspace-care")) {
    Invoke-PythonScript -ScriptPath $Validator -Arguments @((Join-Path $RepoRoot "plugins/$plugin"))
}

$androidCount = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/android-framework-ops/skills") -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") }).Count
$windowsCount = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/android-wsl-ops/skills") -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") }).Count
$macosCount = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/android-macos-ops/skills") -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") }).Count
$workspaceCount = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/codex-workspace-care/skills") -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") }).Count

if ($androidCount -ne 10) {
    throw "android-framework-ops should contain 10 skills, found $androidCount"
}
if ($windowsCount -ne 3) {
    throw "android-wsl-ops should contain 3 skills, found $windowsCount"
}
if ($macosCount -ne 2) {
    throw "android-macos-ops should contain 2 skills, found $macosCount"
}
if ($workspaceCount -ne 2) {
    throw "codex-workspace-care should contain 2 skills, found $workspaceCount"
}

$CoreWindowsSkill = Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/android-framework-ops/skills") -Directory |
    Where-Object { $_.Name -like "android-windows-*" } |
    Select-Object -First 1
if ($CoreWindowsSkill) {
    throw "Windows-side skills must not be inside android-framework-ops"
}

$CoreMacosSkill = Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/android-framework-ops/skills") -Directory |
    Where-Object { $_.Name -like "android-macos-*" } |
    Select-Object -First 1
if ($CoreMacosSkill) {
    throw "macOS-native skills must not be inside android-framework-ops"
}

$SkillFiles = Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins") -Recurse -Filter "SKILL.md" -File
foreach ($SkillFile in $SkillFiles) {
    $SkillDir = Split-Path -Parent $SkillFile.FullName
    $SkillName = Split-Path -Leaf $SkillDir
    $AgentFile = Join-Path $SkillDir "agents/openai.yaml"

    if (-not (Test-Path -LiteralPath $AgentFile)) {
        throw "$SkillName is missing agents/openai.yaml"
    }

    $AgentContent = Get-Content -LiteralPath $AgentFile -Raw
    if ($AgentContent -notlike "*`$$SkillName*") {
        throw "$AgentFile default_prompt should reference `$$SkillName"
    }
}

Write-Host "Plugin validation passed"
