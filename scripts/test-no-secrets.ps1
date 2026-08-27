[CmdletBinding()]
param(
    [switch] $History
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$rg = Get-Command rg -ErrorAction Stop

$patterns = @(
    '-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----',
    'AKIA[0-9A-Z]{16}',
    'gh[pousr]_[A-Za-z0-9_]{20,}',
    'sk-[A-Za-z0-9_-]{20,}',
    '(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*["''][A-Za-z0-9_./+=-]{16,}["'']',
    '(?i)C:\\Users\\[A-Za-z0-9._-]+\\',
    '(?i)(10\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}|192\.168\.(?:[0-9]{1,3}\.)[0-9]{1,3}|172\.(?:1[6-9]|2[0-9]|3[01])\.(?:[0-9]{1,3}\.)[0-9]{1,3})',
    '(?i)[A-Z0-9._%+-]+@(?!example\.com\b)[A-Z0-9.-]+\.[A-Z]{2,}'
)

if ($env:PUBLIC_RELEASE_DENY_REGEX) {
    $patterns += $env:PUBLIC_RELEASE_DENY_REGEX
}

$arguments = @(
    '--line-number',
    '--pcre2',
    '--hidden',
    '--no-ignore',
    '--glob', '!.git/**',
    '--glob', '!scripts/test-no-secrets.ps1'
)
foreach ($pattern in $patterns) {
    $arguments += @('--regexp', $pattern)
}
$arguments += '.'

Push-Location $repoRoot
try {
    $output = & $rg.Source @arguments
    if ($LASTEXITCODE -eq 0) {
        $output | Write-Error
        throw 'Potential secret or private-release material found.'
    }
    if ($LASTEXITCODE -gt 1) {
        throw "rg failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

if ($History) {
    $identities = & git -C $repoRoot log --all --format='%ae%n%ce'
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not inspect Git commit identities.'
    }
    $nonPublicIdentities = $identities |
        Where-Object { $_ -and $_ -notmatch '@users\.noreply\.github\.com$' } |
        Sort-Object -Unique
    if ($nonPublicIdentities) {
        throw 'Git history contains non-noreply author or committer email metadata.'
    }

    $revisions = & git -C $repoRoot rev-list --all
    foreach ($revision in $revisions) {
        $gitArguments = @('grep', '-n', '-I', '--perl-regexp')
        foreach ($pattern in $patterns) {
            $gitArguments += @('-e', $pattern)
        }
        $gitArguments += @($revision, '--', '.', ':(exclude)scripts/test-no-secrets.ps1')
        $historyOutput = & git -C $repoRoot @gitArguments
        if ($LASTEXITCODE -eq 0) {
            $historyOutput | Write-Error
            throw "Potential historical secret or private-release material found in $revision."
        }
        if ($LASTEXITCODE -gt 1) {
            throw "git grep failed for $revision with exit code $LASTEXITCODE"
        }
    }
}

Write-Host 'No configured secret or private-release patterns found.'

