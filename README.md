# Agent Skills and Tooling

Reusable Codex and agent skills, subagent definitions, and supporting utilities.
This repository is maintained as public source: tracked files must not depend on
one person's accounts, private infrastructure, employer systems, or credentials.

## Layout

- `skills/codex/` - Codex skills
- `skills/agents/` - portable agent skills
- `agents/codex/` - native Codex subagent definitions
- `agents/claude/` - matching Claude Code subagent definitions
- `tools/home-assistant/` - configurable Home Assistant custom-card source
- `tools/m365-mail-mcp/` - Microsoft 365 MCP source and setup templates
- `scripts/` - local installation and release-safety checks

## Included skills

Codex:

- `amazon-product-search`

Portable agent skills:

- `find-files`
- `fix-ghost-window`
- `m365-mail`
- `mars-time`

Subagents:

- `adversary` - evidence-ranked independent red-team review
- `offload-worker` - bounded routine work with explicit provenance

Private infrastructure connectors, organization-specific tooling, internal
enterprise integrations, and device-specific network automation are
intentionally not part of this public repository.

## Update and validate

From PowerShell:

```powershell
.\scripts\test-no-secrets.ps1
git status --short
```

Curate source updates explicitly and review the complete staged diff. Do not
bulk-copy a live agent environment into this repository: skill folders can
contain credentials, connector authorization, memories, sessions, OAuth state,
or private instructions alongside the reusable source.

## Install locally

Preview first:

```powershell
.\scripts\install-local-skills.ps1 -WhatIf
```

Use `-Force` to replace existing skill and agent files. The installer does not
install credentials, connector authorization, external applications, or the M365
MCP runtime. See `tools/m365-mail-mcp/README.md` for that server.

## Public-release rule

A clean current tree is not enough when old commits contained private material.
Before making a repository public, scan every reachable Git object and ensure the
published history was created only from the sanitized tree.

## License

No license is currently granted. Public visibility alone does not grant
permission to copy, modify, or redistribute the contents. Add an explicit
license only after confirming ownership of every retained component.

