<#
SKYE live-view relay (Prompt 132). Run it in its own terminal and leave that
terminal open:

    tools\go2rtc\start.ps1

It runs go2rtc (tools\go2rtc\bin\go2rtc.exe, gitignored, never committed)
with the config the SKYE backend generates from the camera registry
(GO2RTC_CONFIG_PATH in backend\.env; default tools\go2rtc\go2rtc.yaml).
go2rtc in turn runs ffmpeg (tools\go2rtc\bin\ffmpeg.exe, also gitignored)
once per viewer to read the camera; stopping go2rtc stops those too. It:

  - reads VIGI_CAMERA_PASSWORD from backend\.env and hands it to go2rtc
    through go2rtc's own environment only. It is never printed, written to
    disk or put on a command line, and go2rtc masks it as *** in its log.
  - relaunches go2rtc when the config file changes (a camera was added,
    edited or deleted; go2rtc's own restart API does nothing on Windows) and
    when the password in backend\.env changes, re-reading it every time.
  - relaunches go2rtc if it stops by itself.

go2rtc's API listens on 127.0.0.1:1984 only. Its WebRTC media port (8555)
listens on this laptop's LAN address, because Windows won't let a browser's
WebRTC traffic reach 127.0.0.1. If Windows asks whether go2rtc may use the
network, refuse: the Block rules that creates keep other devices out, and
viewing on this laptop still works. go2rtc's own log goes to go2rtc.log next
to the config file. Ctrl+C stops go2rtc and this script.

The backend never starts, stops or supervises go2rtc; this script does.
#>
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$exe = Join-Path $PSScriptRoot "bin\go2rtc.exe"
$envFile = Join-Path $repo "backend\.env"
$apiUrl = "http://127.0.0.1:1984/api"

function Read-EnvValue([string]$name) {
    # The value of NAME=value in backend\.env, or $null. Handles quotes,
    # "export NAME=" and a trailing " # comment" on an unquoted value.
    if (-not (Test-Path -LiteralPath $envFile)) { return $null }
    $value = $null
    foreach ($line in [IO.File]::ReadAllLines($envFile)) {
        if ($line -match ('^\s*(?:export\s+)?' + [regex]::Escape($name) + '\s*=\s*(.*)$')) {
            $v = $Matches[1].Trim()
            if ($v.Length -ge 2 -and (($v[0] -eq '"' -and $v[-1] -eq '"') -or ($v[0] -eq "'" -and $v[-1] -eq "'"))) {
                $v = $v.Substring(1, $v.Length - 2)
            } else {
                $v = ($v -replace '\s+#.*$', '').Trim()
            }
            $value = $v
        }
    }
    return $value
}

function Resolve-Go2rtcPath([string]$name, [string]$default) {
    # As the backend does: the setting from backend\.env, else tools\go2rtc\<default>;
    # a relative setting is taken from backend\.
    $setting = Read-EnvValue $name
    if (-not $setting) { return (Join-Path $PSScriptRoot $default) }
    if ([IO.Path]::IsPathRooted($setting)) { return $setting }
    return [IO.Path]::GetFullPath((Join-Path (Join-Path $repo "backend") $setting))
}

function Get-ConfigPath { return (Resolve-Go2rtcPath "GO2RTC_CONFIG_PATH" "go2rtc.yaml") }

function Get-Stamp([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return "" }
    $item = Get-Item -LiteralPath $path
    return "$($item.LastWriteTimeUtc.Ticks):$($item.Length)"
}

function Get-Fingerprint([string]$text) {
    # Compares passwords across reads without keeping a second plain copy around.
    if (-not $text) { return "" }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))) }
    finally { $sha.Dispose() }
}

function Test-ApiUp {
    try { Invoke-WebRequest -UseBasicParsing -Uri $apiUrl -TimeoutSec 1 | Out-Null; return $true }
    catch { return $false }
}

function Stop-Go2rtc($proc) {
    # The whole tree: go2rtc starts an ffmpeg per viewer, and a killed go2rtc
    # must not leave one behind holding a camera connection.
    if ($proc -and -not $proc.HasExited) {
        & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null
        $proc.WaitForExit(5000) | Out-Null
    }
}

if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host "go2rtc isn't installed: $exe is missing."
    exit 1
}
if (Test-ApiUp) {
    Write-Host "Something already answers on 127.0.0.1:1984 (another go2rtc?). Close it, then run this again."
    exit 1
}

$proc = $null
$said = ""
try {
    while ($true) {
        $config = Get-ConfigPath
        if (-not (Test-Path -LiteralPath $config)) {
            if ($said -ne "noconfig") { Write-Host "Waiting for the backend to write $config (start the backend)."; $said = "noconfig" }
            Start-Sleep -Seconds 2
            continue
        }
        $password = Read-EnvValue "VIGI_CAMERA_PASSWORD"
        if (-not $password -or $password -notmatch '^[A-Za-z0-9._~-]+$') {
            if ($said -ne "nopassword") {
                Write-Host "VIGI_CAMERA_PASSWORD in backend\.env is missing or has characters other than letters, digits and - _ . ~ - fix it and save the file."
                $said = "nopassword"
            }
            $password = $null
            Start-Sleep -Seconds 2
            continue
        }
        $said = ""
        $ffmpeg = Resolve-Go2rtcPath "GO2RTC_FFMPEG_PATH" "bin\ffmpeg.exe"
        if (-not (Test-Path -LiteralPath $ffmpeg)) {
            Write-Host "ffmpeg isn't installed: $ffmpeg is missing. go2rtc will run, but live view won't play until it's there."
        }
        $passwordPrint = Get-Fingerprint $password
        $configStamp = Get-Stamp $config
        $envStamp = Get-Stamp $envFile

        # Keep go2rtc's own log from growing without end.
        $log = Join-Path (Split-Path -Parent $config) "go2rtc.log"
        if ((Test-Path -LiteralPath $log) -and (Get-Item -LiteralPath $log).Length -gt 10MB) {
            Move-Item -LiteralPath $log -Destination ($log + ".old") -Force
        }

        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $exe
        $psi.Arguments = "-c `"$config`""
        $psi.WorkingDirectory = Split-Path -Parent $config
        $psi.UseShellExecute = $false
        $psi.EnvironmentVariables["VIGI_CAMERA_PASSWORD"] = $password
        $password = $null
        $proc = [System.Diagnostics.Process]::Start($psi)

        $up = $false
        for ($i = 0; $i -lt 40 -and -not $proc.HasExited; $i++) {
            if (Test-ApiUp) { $up = $true; break }
            Start-Sleep -Milliseconds 250
        }
        if ($up) {
            Write-Host "go2rtc running on 127.0.0.1:1984"
        } elseif (-not $proc.HasExited) {
            Write-Host "go2rtc started, but its API isn't answering on 127.0.0.1:1984. See $log"
        }

        while ($true) {
            if ($proc.HasExited) {
                Write-Host "go2rtc stopped (exit code $($proc.ExitCode)). Starting it again in 5 s; see $log"
                Start-Sleep -Seconds 5
                break
            }
            Start-Sleep -Seconds 1
            if ((Get-ConfigPath) -ne $config -or (Get-Stamp $config) -ne $configStamp) {
                Write-Host "Config changed (cameras or this laptop's address): restarting go2rtc."
                Stop-Go2rtc $proc
                break
            }
            $nowEnv = Get-Stamp $envFile
            if ($nowEnv -ne $envStamp) {
                $envStamp = $nowEnv
                if ((Get-Fingerprint (Read-EnvValue "VIGI_CAMERA_PASSWORD")) -ne $passwordPrint) {
                    Write-Host "VIGI_CAMERA_PASSWORD changed in backend\.env: restarting go2rtc."
                    Stop-Go2rtc $proc
                    break
                }
            }
        }
    }
} finally {
    Stop-Go2rtc $proc
}
