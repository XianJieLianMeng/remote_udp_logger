param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

$pluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $pluginRoot "components\remote_udp_logger"
$resolvedProject = (Resolve-Path $ProjectRoot).Path
$componentsDir = Join-Path $resolvedProject "components"
$target = Join-Path $componentsDir "remote_udp_logger"

if (!(Test-Path $source)) {
    throw "ESP component source not found: $source"
}

if (!(Test-Path $componentsDir)) {
    New-Item -ItemType Directory -Force $componentsDir | Out-Null
}

if (Test-Path $target) {
    if (!$Force) {
        throw "Target already exists: $target. Re-run with -Force to replace it."
    }
    Remove-Item -Recurse -Force $target
}

Copy-Item -Recurse -Force $source $target
Write-Host "Installed remote_udp_logger ESP component to: $target"
