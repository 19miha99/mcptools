"""MCP client connection helper."""

import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connect(command: str, args: list[str]):
    """Connect to an MCP server via stdio transport.

    Usage:
        async with connect("python", ["-m", "my_server"]) as session:
            tools = await session.list_tools()
    """
    params = StdioServerParameters(command=command, args=args)
    # Redirect server stderr to devnull (needs real file handle on Windows)
    devnull = open(os.devnull, "w")
    try:
        async with stdio_client(params, errlog=devnull) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    finally:
        devnull.close()


def parse_server_cmd(server_cmd: tuple[str, ...]) -> tuple[str, list[str]]:
    """Parse click's variadic args into command + args."""
    if not server_cmd:
        raise SystemExit("Error: server command is required")
    return server_cmd[0], list(server_cmd[1:])
