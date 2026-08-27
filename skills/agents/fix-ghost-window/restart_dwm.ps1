[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('dwm', 'explorer')]
    [string] $Target,

    [switch] $ConfirmAction
)

$ErrorActionPreference = 'Stop'

if (-not $ConfirmAction) {
    throw 'Explicit -ConfirmAction is required after the user approves the desktop restart.'
}

function Restart-Explorer {
    $explorerPath = Join-Path $env:SystemRoot 'explorer.exe'
    Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    Start-Process -FilePath $explorerPath
    Write-Output 'EXPLORER-RESTARTED'
}

function Restart-Dwm {
    $taskkillPath = Join-Path $env:SystemRoot 'System32\taskkill.exe'
    if (-not (Test-Path -LiteralPath $taskkillPath -PathType Leaf)) {
        throw "System taskkill executable not found: $taskkillPath"
    }
    $process = Start-Process -FilePath $taskkillPath -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList @(
        '/IM',
        'dwm.exe',
        '/F'
    )
    if ($process.ExitCode -ne 0) {
        throw "taskkill failed with exit code $($process.ExitCode)."
    }
    Write-Output 'DWM-RESTARTED'
}

switch ($Target) {
    'explorer' { Restart-Explorer }
    'dwm' { Restart-Dwm }
}
