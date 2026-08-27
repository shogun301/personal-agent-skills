# Microsoft 365 MCP

Local stdio MCP server for Microsoft Graph. Mail is enabled read-only by
default. Calendar, Files, Teams, and all mail writes remain disabled unless
their explicit environment switches are set and the tenant has granted the
matching delegated scopes.

## Install

```powershell
py -3.10 -m pip install -r .\requirements.txt
```

For Windows broker/WAM support, also install `msal[broker]`.

## Codex configuration

Copy the example block from `codex-config.toml.example` into your personal
Codex `config.toml`, then replace both example paths and set
`M365_CLIENT_ID` to a public-client app registration owned or explicitly
approved by your organization. Keep tenant IDs, login hints, and endpoint
overrides in local configuration or environment variables.

The first interactive sign-in creates `token_cache.json` under
`%LOCALAPPDATA%\m365-mail-mcp` on Windows or the XDG state directory on
Unix-like systems. Override it with `M365_CACHE_PATH`. The cache contains
OAuth material; protect the host account and never place the cache in a source
checkout or synchronized folder.

## Environment switches

- `M365_CLIENT_ID` (required), `M365_TENANT_ID`, `M365_LOGIN_HINT`
- `M365_CACHE_PATH` to override the external per-user cache location
- `M365_AUTHORITY`, `M365_GRAPH_BASE` for sovereign-cloud endpoints
- `M365_USE_DEVICE_CODE=1` to select device-code authentication
- `M365_ENABLE_CALENDAR=1`, `M365_ENABLE_FILES=1`, `M365_ENABLE_TEAMS=1`
- `M365_ENABLE_WRITE=1` to expose mail write tools after consent

## Checks

```powershell
py -3.10 -m py_compile .\m365_mail_mcp.py
py -3.10 .\test_handshake.py
```

A live `whoami` check requires the local token cache and is intentionally not
part of repository tests.
