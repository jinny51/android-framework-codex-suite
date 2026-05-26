$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$Validator = Join-Path $CodexHome "skills/.system/plugin-creator/scripts/validate_plugin.py"

if (-not (Test-Path -LiteralPath $Validator)) {
    throw "Plugin validator not found: $Validator"
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

foreach ($plugin in @("android-framework-ops", "jinny-android-practices", "codex-workspace-care")) {
    Invoke-PythonScript -ScriptPath $Validator -Arguments @((Join-Path $RepoRoot "plugins/$plugin"))
}

$androidCount = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/android-framework-ops/skills") -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") }).Count
$workspaceCount = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "plugins/codex-workspace-care/skills") -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") }).Count

if ($androidCount -ne 9) {
    throw "android-framework-ops should contain 9 skills, found $androidCount"
}
if ($workspaceCount -ne 2) {
    throw "codex-workspace-care should contain 2 skills, found $workspaceCount"
}

Write-Host "Plugin validation passed"
