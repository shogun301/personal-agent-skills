#!/usr/bin/env python3
"""
m365_mail_mcp.py — a minimal local stdio MCP server that acts as an email
client to Microsoft 365 via the Microsoft Graph API.

It exposes a set of mail tools to an MCP client (e.g. the Claude
desktop app):
  Read-only:
    - whoami          : show the signed-in user (verifies auth)
    - list_messages   : list recent messages from a folder
    - search_messages : full-text search across the mailbox
    - read_message    : fetch the full body of one message by id
    - list_folders    : enumerate mail folders
  Write (require Mail.ReadWrite / Mail.Send scopes + admin consent):
    - create_draft        : create a new draft (you review & send in Outlook)
    - create_reply_draft  : create a reply draft to an existing message
    - send_message        : compose AND send an email immediately
    - send_draft          : send an existing draft by id
    - mark_read           : mark a message read/unread
    - move_message        : move a message to another folder
    - delete_message      : move a message to Deleted Items (recoverable)
    - set_flag            : flag/unflag a message for follow-up
    - set_categories      : set the category labels on a message
    - set_importance      : set importance (low/normal/high)

AUTH MODEL
----------
Uses delegated permissions through the operating-system broker when available,
then an interactive system-browser sign-in. Device-code flow is an explicit
opt-in fallback. The token cache is stored outside the source tree in the
user's local application-state directory unless `M365_CACHE_PATH` overrides
it.

Requires an Azure AD (Entra ID) app registration in your tenant:
    - "Mobile and desktop applications" platform, redirect URI
      https://login.microsoftonline.com/common/oauth2/nativeclient
    - "Allow public client flows" = Yes (enables device code)
    - Delegated Microsoft Graph scopes: Mail.Read (or Mail.ReadWrite),
      User.Read, offline_access

Set these via environment variables (recommended) or edit the constants:
    M365_CLIENT_ID   - the Application (client) ID from the app registration
    M365_TENANT_ID   - your tenant ID (or "organizations")
    M365_AUTHORITY   - optional full authority URL override (Gov cloud!)
    M365_GRAPH_BASE  - optional Graph base URL override (Gov cloud!)
    M365_CACHE_PATH  - optional token-cache path outside the source tree

GOV CLOUD NOTE
--------------
Your organization may use a sovereign/government cloud. If so, the default
public-cloud endpoints below are WRONG and must be overridden:
    Authority : https://login.microsoftonline.us/<tenant>  (GCC High/DoD)
    Graph     : https://graph.microsoft.us/v1.0            (GCC High)
                https://dod-graph.microsoft.us/v1.0         (DoD)
Confirm the correct endpoints with your IT administrator before first run.

By default this server is READ-ONLY: only the read tools above are exposed
and only read scopes (User.Read, Mail.Read) are requested. This is the known-
working posture. The write tools (send/draft/delete/organize) are gated behind
env var M365_ENABLE_WRITE=1 and additionally need delegated Mail.ReadWrite and
Mail.Send scopes, which require their own admin consent on a locked tenant.
Enable writes only after that consent is granted.
"""

import os
import sys
import json
import time
import atexit
import tempfile

# ---- third-party deps: pip install mcp msal requests --------------------
try:
    import requests
    import msal
    from fastmcp import FastMCP
except Exception as exc:  # pragma: no cover
    sys.stderr.write(
        "Missing dependencies. Install with:\n"
        "    pip install fastmcp msal requests\n"
        f"Import error: {exc}\n"
    )
    raise

# ---- configuration ------------------------------------------------------
# Use an app registration owned or explicitly approved by the operator's
# organization. Do not borrow a Microsoft-owned first-party public-client ID.
CLIENT_ID = os.environ.get("M365_CLIENT_ID", "").strip()
TENANT_ID = os.environ.get("M365_TENANT_ID", "organizations").strip()

# Optional login hint (your UPN) so the broker picks the right account.
LOGIN_HINT = os.environ.get("M365_LOGIN_HINT", "").strip()

# Set M365_USE_DEVICE_CODE=1 to force the legacy device-code flow instead of
# the OS identity broker (WAM on Windows, the Microsoft identity broker on
# macOS). Device code cannot satisfy device-based Conditional Access, so the
# broker is strongly preferred on managed devices; when no broker runtime is
# available the server falls back to an interactive system-browser sign-in.
USE_DEVICE_CODE = os.environ.get("M365_USE_DEVICE_CODE", "").strip() not in ("", "0", "false", "False")

# Public cloud defaults. OVERRIDE for Gov cloud (see module docstring).
AUTHORITY = os.environ.get(
    "M365_AUTHORITY", f"https://login.microsoftonline.com/{TENANT_ID}"
).strip()
GRAPH_BASE = os.environ.get(
    "M365_GRAPH_BASE", "https://graph.microsoft.com/v1.0"
).strip()

# WRITE TOOLS ARE OFF BY DEFAULT (safe, known-working read-only posture).
# The write tools (send/draft/delete/organize) need Mail.ReadWrite + Mail.Send,
# which require their own admin consent on a locked tenant. Until that consent
# is granted, keep writes disabled so token acquisition only asks for the
# already-consented read scopes. To enable writes once consent lands, set
# env var  M365_ENABLE_WRITE=1  in the MCP server config.
ENABLE_WRITE = os.environ.get("M365_ENABLE_WRITE", "").strip() not in ("", "0", "false", "False")
READ_ONLY = not ENABLE_WRITE

# ---- optional M365 domains (each OFF by default) ------------------------
# Calendar / OneDrive-SharePoint / Teams each add delegated Graph scopes.
# MSAL requests ALL scopes in a single token call, so turning a domain on
# BEFORE its admin consent is granted would break token acquisition for the
# whole server (the consent wall applies to the combined request, taking
# working mail down with it). Therefore each domain stays OFF until an Entra
# admin consents to its scopes; then set the matching env var to 1.
ENABLE_CALENDAR = os.environ.get("M365_ENABLE_CALENDAR", "").strip() not in ("", "0", "false", "False")
ENABLE_FILES = os.environ.get("M365_ENABLE_FILES", "").strip() not in ("", "0", "false", "False")
ENABLE_TEAMS = os.environ.get("M365_ENABLE_TEAMS", "").strip() not in ("", "0", "false", "False")

# Delegated scopes. Mail.ReadWrite covers read + draft/move/delete/flag;
# Mail.Send is required to actually send. Read-only mode drops both writes.
if READ_ONLY:
    SCOPES = ["User.Read", "Mail.Read"]
else:
    SCOPES = ["User.Read", "Mail.ReadWrite", "Mail.Send"]

# Additive read scopes for the optional domains (see the enable flags above).
# These are appended only when the domain is enabled, so the token request
# never asks for a scope you have not yet turned on / had consented.
if ENABLE_CALENDAR:
    SCOPES.append("Calendars.Read" if READ_ONLY else "Calendars.ReadWrite")
if ENABLE_FILES:
    SCOPES += ["Files.Read.All", "Sites.Read.All"]
if ENABLE_TEAMS:
    SCOPES += ["Chat.Read", "Team.ReadBasic.All",
               "Channel.ReadBasic.All", "ChannelMessage.Read.All"]

def _default_cache_path() -> str:
    override = os.environ.get("M365_CACHE_PATH", "").strip()
    if override:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(override)))
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
    else:
        base = os.environ.get("XDG_STATE_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "state"
        )
    return os.path.join(base, "m365-mail-mcp", "token_cache.json")


CACHE_PATH = _default_cache_path()

mcp = FastMCP("m365-mail")

# ---- token handling -----------------------------------------------------
def _build_cache() -> "msal.SerializableTokenCache":
    cache = msal.SerializableTokenCache()
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as handle:
                cache.deserialize(handle.read())
        except Exception as exc:
            sys.stderr.write(f"[warn] could not read token cache: {exc}\n")

    def _save():
        if cache.has_state_changed:
            cache_directory = os.path.dirname(CACHE_PATH)
            temporary_path = None
            try:
                os.makedirs(cache_directory, mode=0o700, exist_ok=True)
                if os.name == "posix":
                    os.chmod(cache_directory, 0o700)
                descriptor, temporary_path = tempfile.mkstemp(
                    prefix=f".{os.path.basename(CACHE_PATH)}.",
                    suffix=".tmp",
                    dir=cache_directory,
                    text=True,
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(cache.serialize())
                os.replace(temporary_path, CACHE_PATH)
                temporary_path = None
                try:
                    os.chmod(CACHE_PATH, 0o600)
                except OSError:
                    pass
            except Exception as exc:
                sys.stderr.write(f"[warn] could not save token cache: {exc}\n")
                try:
                    if temporary_path and os.path.exists(temporary_path):
                        os.remove(temporary_path)
                except OSError:
                    pass

    atexit.register(_save)
    return cache


_CACHE = _build_cache()
_APP_BROKER = None
_APP_PLAIN = None


def _is_mac() -> bool:
    return sys.platform == "darwin"


def _broker_available() -> bool:
    """True if the MSAL runtime broker (pymsalruntime) is importable.

    The broker ships via `pip install "msal[broker]"`. On Windows the broker is
    WAM; on macOS it is the Microsoft identity broker exposed through the
    Microsoft Enterprise SSO extension / Company Portal. Both can present the
    device's registration to satisfy device-based Conditional Access. When the
    runtime is absent we fall back to a system-browser sign-in.
    """
    try:
        import pymsalruntime  # noqa: F401
        return True
    except Exception:
        return False


def _get_app(enable_broker: bool) -> "msal.PublicClientApplication":
    """Return a cached PublicClientApplication.

    Two variants share the same token cache: one with the OS broker enabled
    (WAM on Windows, the Microsoft identity broker on macOS) and a plain one
    that drives an interactive system-browser sign-in.
    """
    global _APP_BROKER, _APP_PLAIN
    if not CLIENT_ID:
        raise RuntimeError(
            "M365_CLIENT_ID is not set and no default client is available."
        )
    if enable_broker:
        if _APP_BROKER is None:
            kwargs = dict(authority=AUTHORITY, token_cache=_CACHE)
            if _is_mac():
                kwargs["enable_broker_on_mac"] = True
            else:
                kwargs["enable_broker_on_windows"] = True
            _APP_BROKER = msal.PublicClientApplication(CLIENT_ID, **kwargs)
        return _APP_BROKER
    if _APP_PLAIN is None:
        _APP_PLAIN = msal.PublicClientApplication(
            CLIENT_ID, authority=AUTHORITY, token_cache=_CACHE
        )
    return _APP_PLAIN


def _acquire_via_broker(app: "msal.PublicClientApplication") -> dict:
    """Interactive acquisition through the OS identity broker (WAM / macOS)."""
    kwargs = dict(
        scopes=SCOPES,
        # parent_window_handle is required by MSAL when the broker is on.
        # For a console/stdio app we pass the console window handle.
        parent_window_handle=msal.PublicClientApplication.CONSOLE_WINDOW_HANDLE,
    )
    if LOGIN_HINT:
        kwargs["login_hint"] = LOGIN_HINT
    else:
        kwargs["prompt"] = "select_account"
    return app.acquire_token_interactive(**kwargs)


def _acquire_via_browser(app: "msal.PublicClientApplication") -> dict:
    """Interactive acquisition via the system default browser (no broker).

    On a device-registered Mac with the Microsoft Enterprise SSO extension the
    browser carries the device's state and can satisfy device-based Conditional
    Access; otherwise it performs a standard interactive sign-in.
    """
    kwargs = dict(scopes=SCOPES)
    if LOGIN_HINT:
        kwargs["login_hint"] = LOGIN_HINT
    else:
        kwargs["prompt"] = "select_account"
    return app.acquire_token_interactive(**kwargs)


def _acquire_via_device_code(app: "msal.PublicClientApplication") -> dict:
    """Legacy device-code flow (prints URL + code to stderr)."""
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {json.dumps(flow)}")
    sys.stderr.write("\n=== Microsoft 365 sign-in required ===\n")
    sys.stderr.write(flow["message"] + "\n")
    sys.stderr.write("======================================\n")
    sys.stderr.flush()
    return app.acquire_token_by_device_flow(flow)  # blocks until done


def _silent(app: "msal.PublicClientApplication") -> "str | None":
    """Try a silent (cached / refresh-token) acquisition; None if unavailable."""
    accounts = app.get_accounts(username=LOGIN_HINT) if LOGIN_HINT else app.get_accounts()
    if len(accounts) > 1:
        if LOGIN_HINT:
            raise RuntimeError(
                "Multiple cached Microsoft 365 accounts match M365_LOGIN_HINT. "
                "Use a separate M365_CACHE_PATH for the intended account."
            )
        raise RuntimeError(
            "Multiple Microsoft 365 accounts are cached. Set M365_LOGIN_HINT "
            "or use a separate M365_CACHE_PATH before reading mail."
        )
    if len(accounts) == 1:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
    return None


def _get_token() -> str:
    """Return a valid access token, using the cache or an interactive flow.

    Order of preference (most to least reliable on managed devices):
      1. OS broker (WAM on Windows, Microsoft identity broker on macOS) — can
         present device registration to satisfy device-based Conditional Access;
      2. system browser — carries device state when the Microsoft SSO extension
         is present;
      3. device code (only when M365_USE_DEVICE_CODE=1) — cannot satisfy
         device-based Conditional Access.
    """
    if USE_DEVICE_CODE:
        app = _get_app(enable_broker=False)
        tok = _silent(app)
        if tok:
            return tok
        result = _acquire_via_device_code(app)
    else:
        result = None
        # 1. Preferred: the OS identity broker, if its runtime is installed.
        if _broker_available():
            try:
                app = _get_app(enable_broker=True)
                tok = _silent(app)
                if tok:
                    return tok
                result = _acquire_via_broker(app)
            except Exception as exc:
                # Broker library/runtime not usable on this machine (or an
                # unsupported msal version) — fall back to the browser. A
                # genuine auth/consent refusal returns a result dict instead,
                # which we keep so the error handler can explain it.
                sys.stderr.write(
                    f"[warn] broker sign-in unavailable ({exc}); using browser...\n"
                )
                result = None
        # 2. Fallback: system browser (only when the broker was unavailable,
        #    not when it reached Entra and was refused).
        if result is None:
            app = _get_app(enable_broker=False)
            tok = _silent(app)
            if tok:
                return tok
            result = _acquire_via_browser(app)

    if not result or "access_token" not in result:
        err = (result or {}).get("error")
        desc = (result or {}).get("error_description") or ""
        # Detect the tenant admin-consent wall and explain the fix, since the
        # raw broker/AADSTS text is cryptic. AADSTS65001 = no consent on record.
        needs_consent = (
            err in ("consent_required", "interaction_required")
            or "65001" in desc
            or "not provisioned" in desc.lower()
            or "requires your admin" in desc.lower()
        )
        if needs_consent:
            raise RuntimeError(
                "Microsoft 365 auth reached the tenant AUTHORIZATION wall "
                "(device is fine; sign-in succeeded). An Entra admin must "
                "consent to this app for your account. Ask your Entra administrator to grant "
                f"admin consent for App ID {CLIENT_ID} with delegated scopes "
                f"{', '.join(SCOPES)}, offline_access. (Leave M365_ENABLE_WRITE "
                "unset or set it to 0 to request read-only scopes.) "
                f"Raw error: {err}: {desc[:300]}"
            )
        raise RuntimeError(f"Auth failed: {err}: {desc}")
    return result["access_token"]


def _graph_get(path: str, params: dict | None = None) -> dict:
    token = _get_token()
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Graph {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def _graph_write(method: str, path: str, body: dict | None = None) -> dict:
    """POST/PATCH/DELETE against Graph. Returns parsed JSON, or {} if the
    response has no body (common for 202/204 on send/delete/update)."""
    token = _get_token()
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    resp = requests.request(
        method.upper(), url, headers=headers, json=body, timeout=30
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Graph {resp.status_code}: {resp.text[:500]}")
    if resp.status_code in (202, 204) or not (resp.text or "").strip():
        return {}
    return resp.json()


def _recipients(addresses) -> list:
    """Build a Graph recipient list from a string, comma list, or list."""
    if not addresses:
        return []
    if isinstance(addresses, str):
        addresses = [a.strip() for a in addresses.split(",") if a.strip()]
    return [{"emailAddress": {"address": a}} for a in addresses]


# ---- MCP tools ----------------------------------------------------------
@mcp.tool()
def whoami() -> str:
    """Show the signed-in user's name and email (verifies authentication)."""
    me = _graph_get("/me", {"$select": "displayName,userPrincipalName,mail"})
    return json.dumps(
        {
            "displayName": me.get("displayName"),
            "userPrincipalName": me.get("userPrincipalName"),
            "mail": me.get("mail"),
        },
        indent=2,
    )


@mcp.tool()
def list_folders() -> str:
    """List the mailbox's mail folders with unread/total counts."""
    data = _graph_get(
        "/me/mailFolders",
        {"$top": "50", "$select": "displayName,unreadItemCount,totalItemCount,id"},
    )
    folders = [
        {
            "name": f.get("displayName"),
            "unread": f.get("unreadItemCount"),
            "total": f.get("totalItemCount"),
            "id": f.get("id"),
        }
        for f in data.get("value", [])
    ]
    return json.dumps(folders, indent=2)


@mcp.tool()
def list_messages(folder: str = "inbox", limit: int = 15) -> str:
    """
    List recent messages from a mail folder.

    Args:
        folder: Folder well-known name (e.g. "inbox", "sentitems",
                "drafts") or a folder id from list_folders.
        limit:  Max number of messages to return (1-50).
    """
    limit = max(1, min(int(limit), 50))
    data = _graph_get(
        f"/me/mailFolders/{folder}/messages",
        {
            "$top": str(limit),
            "$orderby": "receivedDateTime desc",
            "$select": "subject,from,receivedDateTime,isRead,bodyPreview,id",
        },
    )
    out = []
    for m in data.get("value", []):
        frm = (m.get("from") or {}).get("emailAddress", {})
        out.append(
            {
                "id": m.get("id"),
                "subject": m.get("subject"),
                "from": f"{frm.get('name','')} <{frm.get('address','')}>",
                "received": m.get("receivedDateTime"),
                "isRead": m.get("isRead"),
                "preview": (m.get("bodyPreview") or "")[:200],
            }
        )
    return json.dumps(out, indent=2)


@mcp.tool()
def search_messages(query: str, limit: int = 15) -> str:
    """
    Full-text search across the mailbox.

    Args:
        query: Search terms (matches subject, body, sender, etc.).
        limit: Max number of results to return (1-50).
    """
    limit = max(1, min(int(limit), 50))
    # Graph $search requires the ConsistencyLevel header via $search param.
    token = _get_token()
    resp = requests.get(
        f"{GRAPH_BASE}/me/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "ConsistencyLevel": "eventual",
        },
        params={
            "$search": f'"{query}"',
            "$top": str(limit),
            "$select": "subject,from,receivedDateTime,bodyPreview,id",
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Graph {resp.status_code}: {resp.text[:500]}")
    out = []
    for m in resp.json().get("value", []):
        frm = (m.get("from") or {}).get("emailAddress", {})
        out.append(
            {
                "id": m.get("id"),
                "subject": m.get("subject"),
                "from": f"{frm.get('name','')} <{frm.get('address','')}>",
                "received": m.get("receivedDateTime"),
                "preview": (m.get("bodyPreview") or "")[:200],
            }
        )
    return json.dumps(out, indent=2)


@mcp.tool()
def read_message(message_id: str) -> str:
    """
    Fetch the full plain-text body and headers of a single message.

    Args:
        message_id: The message id from list_messages / search_messages.
    """
    m = _graph_get(
        f"/me/messages/{message_id}",
        {
            "$select": "subject,from,toRecipients,ccRecipients,"
            "receivedDateTime,body,bodyPreview"
        },
    )
    frm = (m.get("from") or {}).get("emailAddress", {})
    to = [
        r.get("emailAddress", {}).get("address", "")
        for r in m.get("toRecipients", [])
    ]
    cc = [
        r.get("emailAddress", {}).get("address", "")
        for r in m.get("ccRecipients", [])
    ]
    body = m.get("body", {}) or {}
    return json.dumps(
        {
            "subject": m.get("subject"),
            "from": f"{frm.get('name','')} <{frm.get('address','')}>",
            "to": to,
            "cc": cc,
            "received": m.get("receivedDateTime"),
            "contentType": body.get("contentType"),
            "body": body.get("content"),
        },
        indent=2,
    )


# ---- calendar tools (registered only when M365_ENABLE_CALENDAR=1) -------
if ENABLE_CALENDAR:
    from datetime import datetime, timedelta, timezone

    @mcp.tool()
    def list_events(days_ahead: int = 7, limit: int = 25) -> str:
        """
        List calendar events in a window starting now (uses calendarView, so
        recurring instances are expanded).

        Args:
            days_ahead: How many days forward to include (1-60).
            limit:      Max events to return (1-50).
        """
        days_ahead = max(1, min(int(days_ahead), 60))
        limit = max(1, min(int(limit), 50))
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)
        data = _graph_get(
            "/me/calendarView",
            {
                "startDateTime": now.isoformat(),
                "endDateTime": end.isoformat(),
                "$orderby": "start/dateTime",
                "$top": str(limit),
                "$select": "subject,organizer,start,end,location,"
                "isAllDay,isCancelled,id",
            },
        )
        out = []
        for e in data.get("value", []):
            org = (e.get("organizer") or {}).get("emailAddress", {})
            out.append(
                {
                    "id": e.get("id"),
                    "subject": e.get("subject"),
                    "organizer": f"{org.get('name','')} <{org.get('address','')}>",
                    "start": (e.get("start") or {}).get("dateTime"),
                    "end": (e.get("end") or {}).get("dateTime"),
                    "location": (e.get("location") or {}).get("displayName"),
                    "isAllDay": e.get("isAllDay"),
                    "isCancelled": e.get("isCancelled"),
                }
            )
        return json.dumps(out, indent=2)

    @mcp.tool()
    def get_event(event_id: str) -> str:
        """
        Fetch full details of one calendar event by id, including attendees
        and their response status.

        Args:
            event_id: The event id from list_events.
        """
        e = _graph_get(
            f"/me/events/{event_id}",
            {
                "$select": "subject,organizer,attendees,start,end,location,"
                "body,isAllDay,isCancelled,webLink"
            },
        )
        org = (e.get("organizer") or {}).get("emailAddress", {})
        attendees = [
            {
                "name": a.get("emailAddress", {}).get("name"),
                "address": a.get("emailAddress", {}).get("address"),
                "response": (a.get("status") or {}).get("response"),
                "type": a.get("type"),
            }
            for a in e.get("attendees", [])
        ]
        body = e.get("body", {}) or {}
        return json.dumps(
            {
                "subject": e.get("subject"),
                "organizer": f"{org.get('name','')} <{org.get('address','')}>",
                "start": (e.get("start") or {}).get("dateTime"),
                "end": (e.get("end") or {}).get("dateTime"),
                "location": (e.get("location") or {}).get("displayName"),
                "attendees": attendees,
                "isAllDay": e.get("isAllDay"),
                "isCancelled": e.get("isCancelled"),
                "contentType": body.get("contentType"),
                "body": body.get("content"),
                "webLink": e.get("webLink"),
            },
            indent=2,
        )

    # -- calendar write tools (need Calendars.ReadWrite, i.e. M365_ENABLE_WRITE=1)
    if not READ_ONLY:

        @mcp.tool()
        def create_event(
            subject: str,
            start: str,
            end: str,
            attendees: str = "",
            location: str = "",
            body: str = "",
            time_zone: str = "UTC",
        ) -> str:
            """
            Create a calendar event and send invites to any attendees.

            Args:
                subject:    Event title.
                start:      Start time, ISO 8601 (e.g. "2026-09-01T14:00:00").
                end:        End time, ISO 8601.
                attendees:  Optional attendee address(es), comma-separated.
                location:   Optional location display name.
                body:       Optional description (plain text, or HTML if it
                            contains markup).
                time_zone:  IANA/Windows time zone name for start/end (default UTC).
            """
            event = {
                "subject": subject,
                "start": {"dateTime": start, "timeZone": time_zone},
                "end": {"dateTime": end, "timeZone": time_zone},
                "attendees": [
                    {"emailAddress": {"address": a}, "type": "required"}
                    for a in (
                        [x.strip() for x in attendees.split(",") if x.strip()]
                        if attendees
                        else []
                    )
                ],
            }
            if location:
                event["location"] = {"displayName": location}
            if body:
                event["body"] = _message_body(body)
            created = _graph_write("POST", "/me/events", event)
            return json.dumps(
                {
                    "status": "created",
                    "id": created.get("id"),
                    "subject": created.get("subject"),
                    "webLink": created.get("webLink"),
                },
                indent=2,
            )

        @mcp.tool()
        def update_event(
            event_id: str,
            subject: str = "",
            start: str = "",
            end: str = "",
            location: str = "",
            body: str = "",
            time_zone: str = "UTC",
        ) -> str:
            """
            Update fields on an existing event. Only non-empty args are changed.

            Args:
                event_id:  Id of the event (from list_events).
                subject:   New title, if changing.
                start:     New start time, ISO 8601, if changing.
                end:       New end time, ISO 8601, if changing.
                location:  New location display name, if changing.
                body:      New description, if changing.
                time_zone: Time zone for start/end if either is being changed.
            """
            patch = {}
            if subject:
                patch["subject"] = subject
            if start:
                patch["start"] = {"dateTime": start, "timeZone": time_zone}
            if end:
                patch["end"] = {"dateTime": end, "timeZone": time_zone}
            if location:
                patch["location"] = {"displayName": location}
            if body:
                patch["body"] = _message_body(body)
            updated = _graph_write("PATCH", f"/me/events/{event_id}", patch)
            return json.dumps(
                {"status": "updated", "id": updated.get("id", event_id)}, indent=2
            )

        @mcp.tool()
        def delete_event(event_id: str) -> str:
            """
            Cancel/delete a calendar event by id. If you organized it, this
            sends cancellation notices to attendees.

            Args:
                event_id: Id of the event (from list_events).
            """
            _graph_write("DELETE", f"/me/events/{event_id}", None)
            return json.dumps({"status": "deleted", "id": event_id}, indent=2)


# ---- OneDrive / SharePoint file tools (M365_ENABLE_FILES=1) -------------
if ENABLE_FILES:
    from urllib.parse import quote as _url_quote

    def _fmt_item(it: dict) -> dict:
        return {
            "id": it.get("id"),
            "name": it.get("name"),
            "type": "folder" if it.get("folder") else "file",
            "size": it.get("size"),
            "lastModified": it.get("lastModifiedDateTime"),
            "webUrl": it.get("webUrl"),
        }

    @mcp.tool()
    def list_drive_items(path: str = "") -> str:
        """
        List items in your OneDrive by folder path.

        Args:
            path: Folder path relative to the drive root
                  (e.g. "Documents/Reports"). Empty lists the root.
        """
        path = (path or "").strip().strip("/")
        if path:
            endpoint = f"/me/drive/root:/{path}:/children"
        else:
            endpoint = "/me/drive/root/children"
        data = _graph_get(
            endpoint,
            {
                "$top": "100",
                "$select": "id,name,folder,file,size,"
                "lastModifiedDateTime,webUrl",
            },
        )
        return json.dumps(
            [_fmt_item(i) for i in data.get("value", [])], indent=2
        )

    @mcp.tool()
    def search_files(query: str, limit: int = 25) -> str:
        """
        Search your OneDrive/SharePoint files by name and content.

        Args:
            query: Search terms.
            limit: Max results (1-50).
        """
        limit = max(1, min(int(limit), 50))
        q = _url_quote(query)
        data = _graph_get(
            f"/me/drive/root/search(q='{q}')",
            {
                "$top": str(limit),
                "$select": "id,name,folder,file,size,"
                "lastModifiedDateTime,webUrl",
            },
        )
        return json.dumps(
            [_fmt_item(i) for i in data.get("value", [])], indent=2
        )

    @mcp.tool()
    def read_file(item_id: str, max_chars: int = 20000) -> str:
        """
        Download and return the text content of a OneDrive file by id. Only
        text-decodable files return content; binary/Office files return
        metadata plus a hint (open via webUrl or ask for extraction).

        Args:
            item_id:   Drive item id from list_drive_items / search_files.
            max_chars: Truncate returned text to this many characters.
        """
        token = _get_token()
        url = f"{GRAPH_BASE}/me/drive/items/{item_id}/content"
        resp = requests.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=60
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Graph {resp.status_code}: {resp.text[:500]}")
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.content
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return json.dumps(
                {
                    "status": "binary file (not decoded as text)",
                    "bytes": len(raw),
                    "contentType": content_type,
                    "hint": "Open via the webUrl from list_drive_items, or "
                    "ask for a specific extraction.",
                },
                indent=2,
            )
        return json.dumps(
            {
                "status": "ok",
                "bytes": len(raw),
                "contentType": content_type,
                "truncated": len(text) > max_chars,
                "content": text[:max_chars],
            },
            indent=2,
        )


# ---- Teams tools (M365_ENABLE_TEAMS=1) ----------------------------------
if ENABLE_TEAMS:

    def _teams_msg(m: dict) -> dict:
        body = m.get("body") or {}
        frm = (m.get("from") or {}).get("user") or {}
        return {
            "id": m.get("id"),
            "from": frm.get("displayName"),
            "created": m.get("createdDateTime"),
            "contentType": body.get("contentType"),
            "content": (body.get("content") or "")[:1000],
        }

    @mcp.tool()
    def list_chats(limit: int = 25) -> str:
        """List your recent Teams 1:1 and group chats."""
        limit = max(1, min(int(limit), 50))
        data = _graph_get(
            "/me/chats",
            {"$top": str(limit),
             "$select": "id,topic,chatType,lastUpdatedDateTime"},
        )
        out = [
            {
                "id": c.get("id"),
                "topic": c.get("topic"),
                "type": c.get("chatType"),
                "lastUpdated": c.get("lastUpdatedDateTime"),
            }
            for c in data.get("value", [])
        ]
        return json.dumps(out, indent=2)

    @mcp.tool()
    def list_chat_messages(chat_id: str, limit: int = 20) -> str:
        """
        List recent messages in a Teams chat.

        Args:
            chat_id: Chat id from list_chats.
            limit:   Max messages (1-50).
        """
        limit = max(1, min(int(limit), 50))
        data = _graph_get(
            f"/me/chats/{chat_id}/messages", {"$top": str(limit)}
        )
        return json.dumps(
            [_teams_msg(m) for m in data.get("value", [])], indent=2
        )

    @mcp.tool()
    def list_joined_teams() -> str:
        """List the Teams you are a member of."""
        data = _graph_get(
            "/me/joinedTeams", {"$select": "id,displayName,description"}
        )
        out = [
            {
                "id": t.get("id"),
                "name": t.get("displayName"),
                "description": t.get("description"),
            }
            for t in data.get("value", [])
        ]
        return json.dumps(out, indent=2)

    @mcp.tool()
    def list_channels(team_id: str) -> str:
        """
        List channels in a team.

        Args:
            team_id: Team id from list_joined_teams.
        """
        data = _graph_get(
            f"/teams/{team_id}/channels",
            {"$select": "id,displayName,description"},
        )
        out = [
            {
                "id": c.get("id"),
                "name": c.get("displayName"),
                "description": c.get("description"),
            }
            for c in data.get("value", [])
        ]
        return json.dumps(out, indent=2)

    @mcp.tool()
    def list_channel_messages(
        team_id: str, channel_id: str, limit: int = 20
    ) -> str:
        """
        List recent messages in a team channel. NOTE: channel messages are a
        Microsoft Graph "protected API" and may require extra admin approval
        beyond the ChannelMessage.Read.All consent.

        Args:
            team_id:    Team id from list_joined_teams.
            channel_id: Channel id from list_channels.
            limit:      Max messages (1-50).
        """
        limit = max(1, min(int(limit), 50))
        data = _graph_get(
            f"/teams/{team_id}/channels/{channel_id}/messages",
            {"$top": str(limit)},
        )
        return json.dumps(
            [_teams_msg(m) for m in data.get("value", [])], indent=2
        )


# ---- write tools (registered only when M365_ENABLE_WRITE is true) -------
if not READ_ONLY:

    def _message_body(text: str) -> dict:
        """Wrap body text. Treat as HTML if it looks like markup, else text."""
        looks_html = "<" in text and ">" in text
        return {"contentType": "HTML" if looks_html else "Text", "content": text}

    @mcp.tool()
    def create_draft(
        to: str, subject: str, body: str, cc: str = ""
    ) -> str:
        """
        Create a DRAFT email in your Drafts folder. Does NOT send — you
        review and send it yourself in Outlook. Safest way to compose.

        Args:
            to:      Recipient address(es), comma-separated for multiple.
            subject: Subject line.
            body:    Message body (plain text, or HTML if it contains markup).
            cc:      Optional CC address(es), comma-separated.
        """
        msg = {
            "subject": subject,
            "body": _message_body(body),
            "toRecipients": _recipients(to),
            "ccRecipients": _recipients(cc),
        }
        created = _graph_write("POST", "/me/messages", msg)
        return json.dumps(
            {
                "status": "draft created (not sent)",
                "id": created.get("id"),
                "subject": created.get("subject"),
                "webLink": created.get("webLink"),
            },
            indent=2,
        )

    @mcp.tool()
    def create_reply_draft(message_id: str, comment: str = "") -> str:
        """
        Create a reply DRAFT to an existing message (reply to sender only).
        Does NOT send — review and send it in Outlook.

        Args:
            message_id: Id of the message to reply to.
            comment:    Optional text to prepend to the reply body.
        """
        body = {"comment": comment} if comment else None
        created = _graph_write(
            "POST", f"/me/messages/{message_id}/createReply", body
        )
        return json.dumps(
            {
                "status": "reply draft created (not sent)",
                "id": created.get("id"),
                "webLink": created.get("webLink"),
            },
            indent=2,
        )

    @mcp.tool()
    def send_message(
        to: str, subject: str, body: str, cc: str = ""
    ) -> str:
        """
        Compose AND SEND an email immediately (no review step). Use with
        care — this sends mail as you. Prefer create_draft when unsure.

        Args:
            to:      Recipient address(es), comma-separated for multiple.
            subject: Subject line.
            body:    Message body (plain text, or HTML if it contains markup).
            cc:      Optional CC address(es), comma-separated.
        """
        payload = {
            "message": {
                "subject": subject,
                "body": _message_body(body),
                "toRecipients": _recipients(to),
                "ccRecipients": _recipients(cc),
            },
            "saveToSentItems": True,
        }
        _graph_write("POST", "/me/sendMail", payload)
        return json.dumps(
            {"status": "sent", "to": to, "subject": subject}, indent=2
        )

    @mcp.tool()
    def send_draft(message_id: str) -> str:
        """
        Send an existing draft message by id (e.g. one from create_draft).

        Args:
            message_id: Id of the draft to send.
        """
        _graph_write("POST", f"/me/messages/{message_id}/send", None)
        return json.dumps({"status": "sent", "id": message_id}, indent=2)

    @mcp.tool()
    def mark_read(message_id: str, is_read: bool = True) -> str:
        """
        Mark a message as read or unread.

        Args:
            message_id: Id of the message.
            is_read:    True to mark read, False to mark unread.
        """
        _graph_write(
            "PATCH", f"/me/messages/{message_id}", {"isRead": bool(is_read)}
        )
        return json.dumps(
            {"status": "updated", "id": message_id, "isRead": bool(is_read)},
            indent=2,
        )

    @mcp.tool()
    def move_message(message_id: str, folder: str) -> str:
        """
        Move a message to another folder.

        Args:
            message_id: Id of the message.
            folder:     Destination folder well-known name (e.g. "archive",
                        "deleteditems", "inbox") or a folder id.
        """
        moved = _graph_write(
            "POST", f"/me/messages/{message_id}/move", {"destinationId": folder}
        )
        return json.dumps(
            {"status": "moved", "id": moved.get("id", message_id), "folder": folder},
            indent=2,
        )

    @mcp.tool()
    def delete_message(message_id: str) -> str:
        """
        Delete a message by moving it to Deleted Items (recoverable, NOT a
        permanent purge).

        Args:
            message_id: Id of the message to delete.
        """
        _graph_write(
            "POST", f"/me/messages/{message_id}/move",
            {"destinationId": "deleteditems"},
        )
        return json.dumps(
            {"status": "moved to Deleted Items", "id": message_id}, indent=2
        )

    @mcp.tool()
    def set_flag(message_id: str, flagged: bool = True) -> str:
        """
        Flag or unflag a message for follow-up.

        Args:
            message_id: Id of the message.
            flagged:    True to flag, False to clear the flag.
        """
        status = "flagged" if flagged else "notFlagged"
        _graph_write(
            "PATCH", f"/me/messages/{message_id}",
            {"flag": {"flagStatus": status}},
        )
        return json.dumps(
            {"status": "updated", "id": message_id, "flag": status}, indent=2
        )

    @mcp.tool()
    def set_categories(message_id: str, categories: str) -> str:
        """
        Set the category labels on a message (replaces existing categories).

        Args:
            message_id: Id of the message.
            categories: Comma-separated category names (empty string clears).
        """
        cats = [c.strip() for c in categories.split(",") if c.strip()]
        _graph_write(
            "PATCH", f"/me/messages/{message_id}", {"categories": cats}
        )
        return json.dumps(
            {"status": "updated", "id": message_id, "categories": cats}, indent=2
        )

    @mcp.tool()
    def set_importance(message_id: str, level: str = "normal") -> str:
        """
        Set a message's importance.

        Args:
            message_id: Id of the message.
            level:      One of "low", "normal", or "high".
        """
        level = level.strip().lower()
        if level not in ("low", "normal", "high"):
            raise RuntimeError("level must be one of: low, normal, high")
        _graph_write(
            "PATCH", f"/me/messages/{message_id}", {"importance": level}
        )
        return json.dumps(
            {"status": "updated", "id": message_id, "importance": level}, indent=2
        )


if __name__ == "__main__":
    # FastMCP defaults to stdio transport, which is what the desktop app
    # launches. All logging goes to stderr so stdout stays clean for MCP.
    mcp.run()
