param(
    [Parameter(Mandatory = $true)]
    [string]$SshHost,

    [Parameter(Mandatory = $true)]
    [string]$RemoteRoot,

    [string]$GeneratorPath = "",

    [switch]$Force
)

$ErrorActionPreference = "Stop"
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $script:Utf8NoBom

function ConvertTo-ShellSingleQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + ($Value -replace "'", "'\''") + "'"
}

function Invoke-ProcessCapture {
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$InputText
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FileName
    foreach ($arg in $Arguments) {
        [void]$psi.ArgumentList.Add($arg)
    }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = $script:Utf8NoBom
    $psi.StandardErrorEncoding = $script:Utf8NoBom
    if ($PSBoundParameters.ContainsKey("InputText")) {
        $psi.RedirectStandardInput = $true
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    if ($PSBoundParameters.ContainsKey("InputText")) {
        $inputBytes = $script:Utf8NoBom.GetBytes($InputText)
        $process.StandardInput.BaseStream.Write($inputBytes, 0, $inputBytes.Length)
        $process.StandardInput.Close()
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Invoke-Remote {
    param([Parameter(Mandatory = $true)][string]$Command)
    Invoke-ProcessCapture -FileName "ssh.exe" -Arguments @("-o", "BatchMode=no", "-o", "ConnectTimeout=8", $SshHost, $Command)
}

function Send-RemoteFileContent {
    param(
        [Parameter(Mandatory = $true)][string]$RemotePath,
        [Parameter(Mandatory = $true)][string]$Content
    )
    Invoke-ProcessCapture -FileName "ssh.exe" -Arguments @("-o", "BatchMode=no", "-o", "ConnectTimeout=8", $SshHost, "cat > $(ConvertTo-ShellSingleQuoted $RemotePath)") -InputText $Content
}

if (-not $RemoteRoot.StartsWith("/")) {
    throw "RemoteRoot must be an absolute Linux path."
}
if (-not $GeneratorPath) {
    $GeneratorPath = Join-Path $PSScriptRoot "remote-generate-build-push.sh"
}
if (-not (Test-Path -LiteralPath $GeneratorPath -PathType Leaf)) {
    throw "GeneratorPath not found: $GeneratorPath"
}

$remoteRootQ = ConvertTo-ShellSingleQuoted $RemoteRoot
if (-not $Force) {
    $check = Invoke-Remote "test -f $remoteRootQ/.codex/build-session.sh"
    if ($check.ExitCode -eq 0) {
        Write-Output "BUILD_SESSION_OK remote=$RemoteRoot/.codex/build-session.sh existing=true"
        exit 0
    }
}

$tmp = Invoke-Remote "mktemp -d"
if ($tmp.ExitCode -ne 0) {
    if ($tmp.Stderr) { Write-Error $tmp.Stderr.TrimEnd() }
    exit $tmp.ExitCode
}
$remoteTmp = $tmp.Stdout.Trim()
if (-not $remoteTmp.StartsWith("/")) {
    throw "Unexpected remote temp dir: $remoteTmp"
}

try {
    $generatorText = [System.IO.File]::ReadAllText($GeneratorPath, [System.Text.Encoding]::UTF8)
    $remoteGenerator = "$remoteTmp/generate-build-push.sh"
    $upload = Send-RemoteFileContent -RemotePath $remoteGenerator -Content $generatorText
    if ($upload.ExitCode -ne 0) {
        if ($upload.Stderr) { Write-Error $upload.Stderr.TrimEnd() }
        exit $upload.ExitCode
    }

    $remoteScript = @"
set -euo pipefail
remote_root=$remoteRootQ
ssh_host_label=$(ConvertTo-ShellSingleQuoted $SshHost)
tmp_dir=$(ConvertTo-ShellSingleQuoted $remoteTmp)
generator="`$tmp_dir/generate-build-push.sh"
disc="`$tmp_dir/discovery.env"
chmod +x "`$generator"
test -d "`$remote_root" || { echo "REMOTE_ROOT_MISSING `$remote_root" >&2; exit 2; }

quote_value() {
  printf "'%s'" "`$(printf "%s" "`$1" | sed "s/'/'\\\\''/g")"
}

ENVSETUP_SCRIPT="build/envsetup.sh"
LUNCH_TARGET=""
PRODUCT_OUT_DIR_REL=""

if [ -r "`$remote_root/.codex/build-push.config.sh" ]; then
  # shellcheck disable=SC1090
  source "`$remote_root/.codex/build-push.config.sh" || true
fi

if [ -z "`${LUNCH_TARGET:-}" ] || [ -z "`${PRODUCT_OUT_DIR_REL:-}" ]; then
  hints="`$tmp_dir/root-build-hints.txt"
  (
    cd "`$remote_root"
    {
      find . -maxdepth 1 -type f -name 'debug.sh' 2>/dev/null
      find . -maxdepth 1 -type f -name 'debug*.sh' ! -name 'debug.sh' 2>/dev/null | sort
      find . -maxdepth 1 -type f -name '*.sh' ! -name 'debug*.sh' 2>/dev/null | sort
    } | awk '!seen[`$0]++' |
    while IFS= read -r f; do
      grep -HnE 'source[[:space:]]+.*build/envsetup|^[[:space:]]*\.[[:space:]]+.*build/envsetup|lunch[[:space:]]+|out/target/product' "`$f" 2>/dev/null || true
    done | head -n 1000
  ) >"`$hints"

  if [ -z "`${ENVSETUP_SCRIPT:-}" ] || [ "`$ENVSETUP_SCRIPT" = "build/envsetup.sh" ]; then
    env_match="`$(grep -Eo '(source|\.)[[:space:]]+[./A-Za-z0-9_-]*build/envsetup\.sh' "`$hints" | head -n 1 | awk '{print `$2}' | sed 's#^\./##' || true)"
    [ -n "`$env_match" ] && ENVSETUP_SCRIPT="`$env_match"
  fi

  if [ -z "`${LUNCH_TARGET:-}" ]; then
    LUNCH_TARGET="`$(grep -Eo 'lunch[[:space:]]+[A-Za-z0-9_.+-]+' "`$hints" | head -n 1 | awk '{print `$2}' || true)"
  fi

  if [ -z "`${PRODUCT_OUT_DIR_REL:-}" ]; then
    product="`$(grep -Eo 'out/target/product/[A-Za-z0-9_.-]+' "`$hints" | head -n 1 || true)"
    [ -n "`$product" ] && PRODUCT_OUT_DIR_REL="`$product"
  fi
fi

[ -n "`${ENVSETUP_SCRIPT:-}" ] || ENVSETUP_SCRIPT="build/envsetup.sh"
[ -n "`${LUNCH_TARGET:-}" ] || { echo "LUNCH_TARGET_REQUIRED remote=`$remote_root" >&2; exit 3; }

if [ -z "`${PRODUCT_OUT_DIR_REL:-}" ] && [ -f "`$remote_root/`$ENVSETUP_SCRIPT" ]; then
  set +u
  product_out_abs="`$(
    cd "`$remote_root" &&
    source "`$ENVSETUP_SCRIPT" >/dev/null 2>&1 &&
    lunch "`$LUNCH_TARGET" >/dev/null 2>&1 &&
    get_build_var PRODUCT_OUT 2>/dev/null | tail -n 1
  )" || true
  set -u
  case "`$product_out_abs" in
    "`$remote_root"/*) PRODUCT_OUT_DIR_REL="`${product_out_abs#"`$remote_root"/}" ;;
    out/target/product/*) PRODUCT_OUT_DIR_REL="`$product_out_abs" ;;
  esac
fi

if [ -z "`${PRODUCT_OUT_DIR_REL:-}" ]; then
  product="`$LUNCH_TARGET"
  product="`${product%%-*}"
  PRODUCT_OUT_DIR_REL="out/target/product/`$product"
fi

{
  printf 'SSH_HOST=%s\n' "`$(quote_value "`$ssh_host_label")"
  printf 'REMOTE_ROOT=%s\n' "`$(quote_value "`$remote_root")"
  printf 'ENVSETUP_SCRIPT=%s\n' "`$(quote_value "`$ENVSETUP_SCRIPT")"
  printf 'LUNCH_TARGET=%s\n' "`$(quote_value "`$LUNCH_TARGET")"
  printf 'PRODUCT_OUT_DIR_REL=%s\n' "`$(quote_value "`$PRODUCT_OUT_DIR_REL")"
} >"`$disc"

bash "`$generator" --repo "`$remote_root" --discovery-file "`$disc"
test -f "`$remote_root/.codex/build-session.sh"
echo "BUILD_SESSION_OK remote=`$remote_root/.codex/build-session.sh existing=false lunch=`$LUNCH_TARGET product_out=`$PRODUCT_OUT_DIR_REL"
"@

    $result = Invoke-Remote $remoteScript
    if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
    if ($result.ExitCode -ne 0) {
        if ($result.Stderr) { Write-Error $result.Stderr.TrimEnd() }
        exit $result.ExitCode
    }
    if ($result.Stderr) { Write-Warning $result.Stderr.TrimEnd() }
} finally {
    [void](Invoke-Remote "rm -rf $(ConvertTo-ShellSingleQuoted $remoteTmp)")
}
