# Security

This repository is designed for public source. Do not commit credential stores,
`.env` files, API keys, OAuth material, browser state, raw session logs, agent
memories, private hostnames, personal account identifiers, or private network
topology.

Before each push, run:

```powershell
.\scripts\test-no-secrets.ps1
```

The scanner is a guardrail, not proof of safety. Review changes for identifiers,
organization-only instructions, internal endpoints, and operational details that
could expose private systems even when no credential is present.

If a sensitive value is committed, removing it in a later commit is insufficient:
rewrite all affected Git history and rotate the credential if it was usable. Do
not paste suspected secrets into a public issue. Use the repository Security tab
for private reporting when available.

