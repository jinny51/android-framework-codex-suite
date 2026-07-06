param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,

    [string]$Destination,
    [string]$Adb = "adb.exe",
    [string]$DeviceSerial,
    [switch]$Reboot,
    [switch]$WaitBoot
)

$ErrorActionPreference = "Stop"

function Invoke-Adb {
    param([string[]]$Args)
    $cmd = @()
    if ($DeviceSerial) {
        $cmd += @("-s", $DeviceSerial)
    }
    $cmd += $Args
    & $Adb @cmd
    if ($LASTEXITCODE -ne 0) {
        throw "adb failed: $Adb $($cmd -join ' ')"
    }
}

function Infer-Destination([string]$Path) {
    $name = [System.IO.Path]::GetFileName($Path)
    switch ($name) {
        "services.jar" { return "/system/framework/services.jar" }
        "framework.jar" { return "/system/framework/framework.jar" }
        "framework-res.apk" { return "/system/framework/framework-res.apk" }
        "SystemUI.apk" { return "/system/priv-app/SystemUI/SystemUI.apk" }
        "Launcher3.apk" { return "/system/priv-app/Launcher3/Launcher3.apk" }
        default { throw "Destination not provided and cannot infer destination for artifact: $name" }
    }
}

if (-not (Test-Path -LiteralPath $Artifact)) {
    throw "Artifact not found: $Artifact"
}

if (-not $Destination) {
    $Destination = Infer-Destination $Artifact
}

Invoke-Adb @("wait-for-device")
try { Invoke-Adb @("root") } catch {}
Invoke-Adb @("remount")
Invoke-Adb @("push", $Artifact, $Destination)
try { Invoke-Adb @("shell", "sync") } catch {}

if ($Reboot) {
    Invoke-Adb @("reboot")
    if ($WaitBoot) {
        Invoke-Adb @("wait-for-device")
    }
}

[pscustomobject]@{
    artifact = $Artifact
    destination = $Destination
    adb = $Adb
    deviceSerial = $DeviceSerial
    reboot = [bool]$Reboot
    result = "pushed"
} | ConvertTo-Json
