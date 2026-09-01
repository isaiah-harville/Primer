"""The bridge to Haystack's MCP integration.

Kept in its own module so the rest of Chat can be imported, tested, and run
without the MCP dependency present. A deployment with tools switched off
never touches this file.
"""

from __future__ import annotations

import logging
from typing import Any

from haystack_integrations.tools.mcp import MCPToolset, SSEServerInfo

from primer_chat.tool_config import ToolConfiguration

logger = logging.getLogger(__name__)


class HaystackToolInvoker:
    """Invokes MCP tools through Haystack.

    Primer runs no subprocesses of its own. Every tool executes inside the
    MCP server the operator configured, which is where the sandbox
    guarantees they declared actually live.
    """

    def __init__(self, configuration: ToolConfiguration) -> None:
        self._configuration = configuration
        self._toolsets = {
            server.name: MCPToolset(
                server_info=SSEServerInfo(url=server.url),
                # The allowlist is passed to the toolset as well as checked
                # by the policy. Two places, deliberately: this one stops a
                # tool being connected at all, the other stops it being run.
                tool_names=list(server.allowed_tools),
            )
            for server in configuration.servers
        }

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> str:
        server = self._configuration.server_for(tool_name)
        if server is None:
            # Unreachable through the policy, which refuses unknown tools
            # first. Raised rather than defaulted so a future caller that
            # skipped the policy fails loudly instead of executing.
            raise LookupError(f"no configured server exposes {tool_name}")

        toolset = self._toolsets[server.name]
        tool = next((candidate for candidate in toolset.tools if candidate.name == tool_name), None)
        if tool is None:
            raise LookupError(f"{server.name} does not expose {tool_name}")
        return str(tool.invoke(**arguments))
