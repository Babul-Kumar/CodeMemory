"""CodeMemory server package — FastAPI REST API and MCP server."""
from __future__ import annotations

from codememory.server.app import create_app, get_mcp_server

__all__ = ["create_app", "get_mcp_server"]
