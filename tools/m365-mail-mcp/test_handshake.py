#!/usr/bin/env python3
"""Import the server and verify FastMCP registered the tools."""
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["M365_CLIENT_ID"] = "test-client-id"
_test_state = tempfile.TemporaryDirectory(prefix="m365-mail-mcp-test-")
os.environ["M365_CACHE_PATH"] = str(Path(_test_state.name) / "token_cache.json")

from fastmcp import Client
import m365_mail_mcp

source_directory = Path(m365_mail_mcp.__file__).resolve().parent
cache_path = Path(m365_mail_mcp.CACHE_PATH).resolve()
assert cache_path.parent != source_directory, "token cache must stay outside the source tree"
assert cache_path == Path(os.environ["M365_CACHE_PATH"]).resolve()


class _SilentAuthStub:
    def __init__(self, accounts):
        self.accounts = accounts
        self.username = None

    def get_accounts(self, username=None):
        self.username = username
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        return {"access_token": "test-token"}


def test_silent_account_selection():
    original_hint = m365_mail_mcp.LOGIN_HINT
    try:
        m365_mail_mcp.LOGIN_HINT = "alex@example.com"
        hinted = _SilentAuthStub([{"username": "alex@example.com"}])
        assert m365_mail_mcp._silent(hinted) == "test-token"
        assert hinted.username == "alex@example.com"

        m365_mail_mcp.LOGIN_HINT = ""
        ambiguous = _SilentAuthStub([{"id": "one"}, {"id": "two"}])
        try:
            m365_mail_mcp._silent(ambiguous)
        except RuntimeError as exc:
            assert "Multiple Microsoft 365 accounts" in str(exc)
        else:
            raise AssertionError("ambiguous cached accounts must fail closed")
    finally:
        m365_mail_mcp.LOGIN_HINT = original_hint


async def main():
    test_silent_account_selection()
    async with Client(m365_mail_mcp.mcp) as client:
        tools = await client.list_tools()
        names = [tool.name for tool in tools]
        assert names == [
            "whoami",
            "list_folders",
            "list_messages",
            "search_messages",
            "read_message",
        ]
        print("TOOLS:", names)


if __name__ == "__main__":
    asyncio.run(main())
