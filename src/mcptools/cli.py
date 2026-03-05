"""CLI entry point for mcptools."""

import click

from . import __version__


@click.group()
@click.version_option(__version__, prog_name="mcptools")
def main():
    """mcptools — Developer toolkit for MCP servers.

    Inspect, test, benchmark, validate, and document any MCP server.

    \b
    Examples:
      mcptools inspect python -m my_server
      mcptools test python -m my_server
      mcptools bench python -m my_server
      mcptools doctor python -m my_server
      mcptools docs python -m my_server
      mcptools init my-new-server
    """


# Import and register commands
from .commands import inspect, test, bench, doctor, docs, init  # noqa: E402

main.add_command(inspect)
main.add_command(test)
main.add_command(bench)
main.add_command(doctor)
main.add_command(docs)
main.add_command(init)
