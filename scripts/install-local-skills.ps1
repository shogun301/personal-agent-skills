[CmdletBinding(SupportsShouldProcess)]
param(
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$userRoot = [Environment]::GetFolderPath('UserProfile')

$sets = @(
    @{ Source = Join-Path $repoRoot 'skills\codex'; Destination = Join-Path $userRoot '.codex\skills' },
    @{ Source = Join-Path $repoRoot 'skills\agents'; Destination = Join-Path $userRoot '.agents\skills' }
)

foreach ($set in $sets) {
    foreach ($skill in Get-ChildItem -LiteralPath $set.Source -Directory) {
        if (-not (Test-Path -LiteralPath (Join-Path $skill.FullName 'SKILL.md'))) {
            continue
        }
        $destination = Join-Path $set.Destination $skill.Name
        if ((Test-Path -LiteralPath $destination) -and -not $Force) {
            Write-Warning "Skipping existing skill $destination. Use -Force to replace files."
            continue
        }

        if ($PSCmdlet.ShouldProcess($destination, "Install $($skill.Name)")) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
            Copy-Item -Path (Join-Path $skill.FullName '*') -Destination $destination -Recurse -Force
        }
    }
}

$agentSets = @(
    @{ Source = Join-Path $repoRoot 'agents\codex'; Destination = Join-Path $userRoot '.codex\agents' },
    @{ Source = Join-Path $repoRoot 'agents\claude'; Destination = Join-Path $userRoot '.claude\agents' }
)

foreach ($set in $agentSets) {
    if (-not (Test-Path -LiteralPath $set.Source)) { continue }
    foreach ($agent in Get-ChildItem -LiteralPath $set.Source -File) {
        $destination = Join-Path $set.Destination $agent.Name
        if ((Test-Path -LiteralPath $destination) -and -not $Force) {
            Write-Warning "Skipping existing agent $destination. Use -Force to replace it."
            continue
        }

        if ($PSCmdlet.ShouldProcess($destination, "Install $($agent.Name)")) {
            New-Item -ItemType Directory -Path $set.Destination -Force | Out-Null
            Copy-Item -LiteralPath $agent.FullName -Destination $destination -Force
        }
    }
}
