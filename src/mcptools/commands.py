"""All mcptools commands."""

import asyncio
import json
import os
import re
import statistics
import time
from pathlib import Path
from typing import Any

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from .client import connect, parse_server_cmd

console = Console()

CMD_SETTINGS = dict(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)


def _schema_props(tool) -> tuple[dict, list[str]]:
    """Extract properties and required list from a tool's input schema."""
    schema = tool.inputSchema or {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    return props, required


def _type_str(prop: dict) -> str:
    """Human-readable type from JSON schema property."""
    t = prop.get("type", "any")
    if isinstance(t, list):
        t = "/".join(t)
    enum = prop.get("enum")
    if enum:
        return f"{t} [{', '.join(str(e) for e in enum)}]"
    return t


def _format_result(content) -> str:
    """Format CallToolResult content for display."""
    parts = []
    for item in content:
        if hasattr(item, "text"):
            try:
                parsed = json.loads(item.text)
                parts.append(json.dumps(parsed, indent=2, ensure_ascii=False))
            except (json.JSONDecodeError, TypeError):
                parts.append(item.text)
        else:
            parts.append(str(item))
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  INSPECT — show server tools, resources, prompts
# ═══════════════════════════════════════════════════════════════════════════════


@click.command(**CMD_SETTINGS)
@click.argument("server_cmd", nargs=-1, type=click.UNPROCESSED, required=True)
@click.option("--detail", "-d", is_flag=True, help="Show full parameter details for each tool.")
def inspect(server_cmd, detail):
    """Connect to an MCP server and display all available tools.

    \b
    Example:
      mcptools inspect python -m my_server
      mcptools inspect -d python -m my_server
    """
    asyncio.run(_inspect(server_cmd, detail))


async def _inspect(server_cmd, detail):
    command, args = parse_server_cmd(server_cmd)
    cmd_str = f"{command} {' '.join(args)}"

    with console.status("[bold blue]Connecting to server..."):
        async with connect(command, args) as session:
            tools_result = await session.list_tools()
            try:
                resources_result = await session.list_resources()
                resources = resources_result.resources
            except Exception:
                resources = []
            try:
                prompts_result = await session.list_prompts()
                prompts = prompts_result.prompts
            except Exception:
                prompts = []

    tools = tools_result.tools

    # Server info panel
    info_lines = [
        f"[bold cyan]Tools:[/]     {len(tools)}",
        f"[bold cyan]Resources:[/] {len(resources)}",
        f"[bold cyan]Prompts:[/]   {len(prompts)}",
        f"[dim]Command:[/]   {cmd_str}",
    ]
    console.print(Panel("\n".join(info_lines), title="[bold]MCP Server", border_style="blue"))

    if not tools:
        console.print("[yellow]No tools found.[/]")
        return

    if detail:
        # Detailed view — one panel per tool
        for tool in tools:
            props, required = _schema_props(tool)
            tree = Tree(f"[bold cyan]{tool.name}[/]")
            if tool.description:
                tree.add(f"[dim]{tool.description}[/]")

            if props:
                params_branch = tree.add("[bold]Parameters")
                for pname, pschema in props.items():
                    req = "required" if pname in required else "optional"
                    default = pschema.get("default")
                    default_str = f", default={default!r}" if default is not None else ""
                    desc = pschema.get("description", "")
                    label = f"[green]{pname}[/] ({_type_str(pschema)}, {req}{default_str})"
                    p_node = params_branch.add(label)
                    if desc:
                        p_node.add(f"[dim]{desc}[/]")
            else:
                tree.add("[dim]No parameters[/]")

            console.print(tree)
            console.print()
    else:
        # Compact table view
        table = Table(title="Tools", box=box.ROUNDED, show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("Name", style="bold cyan", min_width=20)
        table.add_column("Description", ratio=3)
        table.add_column("Params", justify="center", width=12)

        for i, tool in enumerate(tools, 1):
            props, required = _schema_props(tool)
            desc = (tool.description or "[dim]No description[/]")
            # Truncate long descriptions
            if len(desc) > 80:
                desc = desc[:77] + "..."
            param_str = f"{len(required)}req/{len(props)}" if props else "-"
            table.add_row(str(i), tool.name, desc, param_str)

        console.print(table)

    # Resources
    if resources:
        console.print()
        res_table = Table(title="Resources", box=box.SIMPLE)
        res_table.add_column("URI", style="cyan")
        res_table.add_column("Name")
        res_table.add_column("MIME Type", style="dim")
        for r in resources:
            res_table.add_row(str(r.uri), r.name or "", getattr(r, "mimeType", "") or "")
        console.print(res_table)

    # Prompts
    if prompts:
        console.print()
        pr_table = Table(title="Prompts", box=box.SIMPLE)
        pr_table.add_column("Name", style="cyan")
        pr_table.add_column("Description")
        for p in prompts:
            pr_table.add_row(p.name, p.description or "")
        console.print(pr_table)


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST — interactive tool tester
# ═══════════════════════════════════════════════════════════════════════════════


@click.command(**CMD_SETTINGS)
@click.argument("server_cmd", nargs=-1, type=click.UNPROCESSED, required=True)
@click.option("--tool", "-t", "tool_name", help="Directly test a specific tool by name.")
@click.option("--json-args", "-j", help='JSON string of arguments, e.g. \'{"limit": 5}\'.')
def test(server_cmd, tool_name, json_args):
    """Interactively test tools on an MCP server.

    \b
    Example:
      mcptools test python -m my_server
      mcptools test -t list_processes -j '{"limit":5}' python -m my_server
    """
    asyncio.run(_test(server_cmd, tool_name, json_args))


async def _test(server_cmd, tool_name, json_args):
    command, args = parse_server_cmd(server_cmd)

    with console.status("[bold blue]Connecting to server..."):
        async with connect(command, args) as session:
            tools_result = await session.list_tools()
            tools = tools_result.tools

            if not tools:
                console.print("[yellow]No tools found on this server.[/]")
                return

            console.print(f"[bold green]Connected![/] {len(tools)} tools available.\n")

            while True:
                # Select tool
                if tool_name:
                    selected = next((t for t in tools if t.name == tool_name), None)
                    if not selected:
                        console.print(f"[red]Tool '{tool_name}' not found.[/]")
                        console.print("Available: " + ", ".join(t.name for t in tools))
                        return
                else:
                    for i, t in enumerate(tools, 1):
                        desc = (t.description or "")[:60]
                        console.print(f"  [cyan]{i:>3}[/] {t.name}  [dim]{desc}[/]")

                    console.print()
                    choice = Prompt.ask(
                        "Select tool (number or name, 'q' to quit)",
                        default="q",
                    )

                    if choice.lower() == "q":
                        break

                    # Parse choice
                    try:
                        idx = int(choice) - 1
                        selected = tools[idx]
                    except (ValueError, IndexError):
                        selected = next((t for t in tools if t.name == choice), None)
                        if not selected:
                            console.print(f"[red]Not found: '{choice}'[/]")
                            continue

                # Collect arguments
                if json_args:
                    try:
                        call_args = json.loads(json_args)
                    except json.JSONDecodeError as e:
                        console.print(f"[red]Invalid JSON: {e}[/]")
                        return
                else:
                    call_args = {}
                    props, required = _schema_props(selected)

                    if props:
                        console.print(f"\n[bold]{selected.name}[/] parameters:")
                        for pname, pschema in props.items():
                            req = pname in required
                            default = pschema.get("default")
                            type_s = _type_str(pschema)
                            desc = pschema.get("description", "")

                            label = f"  [green]{pname}[/] ({type_s})"
                            if req:
                                label += " [red]*required[/]"
                            if default is not None:
                                label += f" [dim]default={default!r}[/]"
                            if desc:
                                label += f"\n    [dim]{desc}[/]"
                            console.print(label)

                            prompt_default = str(default) if default is not None else ""
                            value = Prompt.ask(f"  {pname}", default=prompt_default)

                            if value == "" and not req:
                                continue

                            # Type coercion
                            ptype = pschema.get("type", "string")
                            try:
                                if ptype == "integer":
                                    call_args[pname] = int(value)
                                elif ptype == "number":
                                    call_args[pname] = float(value)
                                elif ptype == "boolean":
                                    call_args[pname] = value.lower() in ("true", "1", "yes")
                                elif ptype in ("array", "object"):
                                    call_args[pname] = json.loads(value)
                                else:
                                    call_args[pname] = value
                            except (ValueError, json.JSONDecodeError):
                                call_args[pname] = value

                # Call the tool
                console.print(f"\n[bold]Calling [cyan]{selected.name}[/]...", end="")
                start = time.perf_counter()
                try:
                    result = await session.call_tool(selected.name, arguments=call_args or None)
                    elapsed = time.perf_counter() - start
                    console.print(f" [green]OK[/] ({elapsed:.3f}s)\n")

                    formatted = _format_result(result.content)
                    if formatted.strip().startswith("{") or formatted.strip().startswith("["):
                        console.print(Syntax(formatted, "json", theme="monokai"))
                    else:
                        console.print(Panel(formatted, border_style="green"))

                except Exception as e:
                    elapsed = time.perf_counter() - start
                    console.print(f" [red]ERROR[/] ({elapsed:.3f}s)")
                    console.print(f"[red]{e}[/]")

                console.print()

                # If tool was specified via --tool, don't loop
                if tool_name:
                    break

                if not Confirm.ask("Test another tool?", default=True):
                    break
                tool_name = None  # reset for next iteration


# ═══════════════════════════════════════════════════════════════════════════════
#  BENCH — benchmark tool response times
# ═══════════════════════════════════════════════════════════════════════════════


@click.command(**CMD_SETTINGS)
@click.argument("server_cmd", nargs=-1, type=click.UNPROCESSED, required=True)
@click.option("--iterations", "-n", default=5, help="Number of iterations per tool.")
@click.option("--tool", "-t", "tool_name", help="Benchmark a specific tool only.")
def bench(server_cmd, iterations, tool_name):
    """Benchmark MCP server tool response times.

    \b
    Example:
      mcptools bench python -m my_server
      mcptools bench -n 10 -t get_system_overview python -m my_server
    """
    asyncio.run(_bench(server_cmd, iterations, tool_name))


async def _bench(server_cmd, iterations, tool_name):
    command, args = parse_server_cmd(server_cmd)

    with console.status("[bold blue]Connecting to server..."):
        async with connect(command, args) as session:
            tools_result = await session.list_tools()
            tools = tools_result.tools

            if tool_name:
                tools = [t for t in tools if t.name == tool_name]
                if not tools:
                    console.print(f"[red]Tool '{tool_name}' not found.[/]")
                    return

            console.print(
                f"[bold]Benchmarking {len(tools)} tools ({iterations} iterations each)[/]\n"
            )

            table = Table(box=box.ROUNDED, show_lines=False)
            table.add_column("Tool", style="cyan", min_width=25)
            table.add_column("Min", justify="right", width=8)
            table.add_column("Avg", justify="right", width=8)
            table.add_column("Max", justify="right", width=8)
            table.add_column("P95", justify="right", width=8)
            table.add_column("Status", justify="center", width=8)

            for tool in tools:
                props, required = _schema_props(tool)

                # Skip tools with required args (can't auto-test)
                if required:
                    table.add_row(
                        tool.name, "-", "-", "-", "-",
                        "[yellow]SKIP[/]",
                    )
                    continue

                timings = []
                errors = 0
                for _ in range(iterations):
                    start = time.perf_counter()
                    try:
                        await session.call_tool(tool.name, arguments=None)
                        timings.append(time.perf_counter() - start)
                    except Exception:
                        errors += 1
                        timings.append(time.perf_counter() - start)

                if not timings:
                    table.add_row(tool.name, "-", "-", "-", "-", "[red]FAIL[/]")
                    continue

                ms = [t * 1000 for t in timings]
                mn = min(ms)
                avg = statistics.mean(ms)
                mx = max(ms)
                p95 = sorted(ms)[int(len(ms) * 0.95)] if len(ms) > 1 else mx

                status = "[green]OK[/]" if errors == 0 else f"[yellow]{errors}err[/]"
                table.add_row(
                    tool.name,
                    f"{mn:.0f}ms",
                    f"{avg:.0f}ms",
                    f"{mx:.0f}ms",
                    f"{p95:.0f}ms",
                    status,
                )

            console.print(table)
            console.print(f"\n[dim]Tools marked SKIP have required parameters.[/]")


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCTOR — validate MCP server for common issues
# ═══════════════════════════════════════════════════════════════════════════════


@click.command(**CMD_SETTINGS)
@click.argument("server_cmd", nargs=-1, type=click.UNPROCESSED, required=True)
def doctor(server_cmd):
    """Validate an MCP server for common issues and best practices.

    \b
    Example:
      mcptools doctor python -m my_server
    """
    asyncio.run(_doctor(server_cmd))


async def _doctor(server_cmd):
    command, args = parse_server_cmd(server_cmd)
    checks = []
    warnings = []
    errors = []

    def ok(msg):
        checks.append(("ok", msg))

    def warn(msg):
        checks.append(("warn", msg))
        warnings.append(msg)

    def fail(msg):
        checks.append(("fail", msg))
        errors.append(msg)

    # Check 1: Server starts
    console.print("[bold]Running diagnostics...[/]\n")
    try:
        async with connect(command, args) as session:
            ok("Server starts successfully")

            # Check 2: List tools
            try:
                tools_result = await session.list_tools()
                tools = tools_result.tools
                ok(f"Tools endpoint works ({len(tools)} tools found)")
            except Exception as e:
                fail(f"list_tools failed: {e}")
                tools = []

            if not tools:
                warn("No tools registered")
            else:
                # Check 3: Tool descriptions
                no_desc = [t.name for t in tools if not t.description]
                if no_desc:
                    warn(f"{len(no_desc)} tools without descriptions: {', '.join(no_desc[:5])}")
                else:
                    ok("All tools have descriptions")

                # Check 4: Parameter descriptions
                params_no_desc = []
                for t in tools:
                    props, _ = _schema_props(t)
                    for pname, pschema in props.items():
                        if not pschema.get("description"):
                            params_no_desc.append(f"{t.name}.{pname}")
                if params_no_desc:
                    warn(
                        f"{len(params_no_desc)} parameters without descriptions: "
                        + ", ".join(params_no_desc[:5])
                        + ("..." if len(params_no_desc) > 5 else "")
                    )
                else:
                    ok("All parameters have descriptions")

                # Check 5: Duplicate tool names
                names = [t.name for t in tools]
                dupes = [n for n in set(names) if names.count(n) > 1]
                if dupes:
                    fail(f"Duplicate tool names: {', '.join(dupes)}")
                else:
                    ok("No duplicate tool names")

                # Check 6: Naming conventions
                bad_names = [t.name for t in tools if not re.match(r"^[a-z][a-z0-9_]*$", t.name)]
                if bad_names:
                    warn(f"Non-standard tool names (use snake_case): {', '.join(bad_names[:5])}")
                else:
                    ok("All tool names follow snake_case convention")

                # Check 7: Tool schemas valid
                invalid = []
                for t in tools:
                    schema = t.inputSchema
                    if schema and not isinstance(schema, dict):
                        invalid.append(t.name)
                    elif schema:
                        if schema.get("type") != "object":
                            invalid.append(t.name)
                if invalid:
                    warn(f"Tools with non-standard schemas: {', '.join(invalid)}")
                else:
                    ok("All tool schemas are valid")

                # Check 8: Call a no-arg tool
                no_arg_tools = [
                    t for t in tools if not (t.inputSchema or {}).get("required")
                ]
                if no_arg_tools:
                    test_tool = no_arg_tools[0]
                    start = time.perf_counter()
                    try:
                        result = await session.call_tool(test_tool.name)
                        elapsed = time.perf_counter() - start
                        if elapsed > 5:
                            warn(f"Tool '{test_tool.name}' is slow ({elapsed:.1f}s)")
                        else:
                            ok(f"Tool call works ({test_tool.name}: {elapsed:.2f}s)")
                    except Exception as e:
                        fail(f"Tool call failed ({test_tool.name}): {e}")
                else:
                    warn("No tools without required parameters to test")

            # Check 9: Resources endpoint
            try:
                await session.list_resources()
                ok("Resources endpoint works")
            except Exception:
                warn("Resources endpoint not available")

            # Check 10: Prompts endpoint
            try:
                await session.list_prompts()
                ok("Prompts endpoint works")
            except Exception:
                warn("Prompts endpoint not available")

    except Exception as e:
        fail(f"Server failed to start: {e}")

    # Display results
    console.print()
    for status, msg in checks:
        if status == "ok":
            console.print(f"  [green]PASS[/] {msg}")
        elif status == "warn":
            console.print(f"  [yellow]WARN[/] {msg}")
        else:
            console.print(f"  [red]FAIL[/] {msg}")

    console.print()
    total = len(checks)
    passed = total - len(errors)
    color = "green" if not errors else "red" if len(errors) > 2 else "yellow"
    console.print(
        Panel(
            f"[{color}]{passed}/{total} checks passed[/]"
            + (f" ({len(warnings)} warnings)" if warnings else ""),
            title="[bold]Doctor Report",
            border_style=color,
        )
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCS — generate markdown documentation
# ═══════════════════════════════════════════════════════════════════════════════


@click.command(**CMD_SETTINGS)
@click.argument("server_cmd", nargs=-1, type=click.UNPROCESSED, required=True)
@click.option("--output", "-o", default=None, help="Output file (default: stdout).")
def docs(server_cmd, output):
    """Auto-generate markdown documentation from an MCP server's tools.

    \b
    Example:
      mcptools docs python -m my_server
      mcptools docs -o API.md python -m my_server
    """
    asyncio.run(_docs(server_cmd, output))


async def _docs(server_cmd, output):
    command, args = parse_server_cmd(server_cmd)

    with console.status("[bold blue]Connecting to server..."):
        async with connect(command, args) as session:
            tools_result = await session.list_tools()
            tools = tools_result.tools

    lines = ["# MCP Server Documentation", ""]
    lines.append(f"**{len(tools)} tools** available.", )
    lines.append("")
    lines.append("## Tools")
    lines.append("")

    for tool in tools:
        lines.append(f"### `{tool.name}`")
        lines.append("")
        if tool.description:
            lines.append(tool.description)
            lines.append("")

        props, required = _schema_props(tool)
        if props:
            lines.append("**Parameters:**")
            lines.append("")
            lines.append("| Name | Type | Required | Default | Description |")
            lines.append("|------|------|----------|---------|-------------|")
            for pname, pschema in props.items():
                req = "Yes" if pname in required else "No"
                default = pschema.get("default", "-")
                if default is not None and default != "-":
                    default = f"`{default}`"
                desc = pschema.get("description", "")
                type_s = _type_str(pschema)
                lines.append(f"| `{pname}` | `{type_s}` | {req} | {default} | {desc} |")
            lines.append("")
        else:
            lines.append("*No parameters.*")
            lines.append("")

        lines.append("---")
        lines.append("")

    md = "\n".join(lines)

    if output:
        Path(output).write_text(md, encoding="utf-8")
        console.print(f"[green]Documentation written to {output}[/] ({len(tools)} tools)")
    else:
        console.print(Syntax(md, "markdown", theme="monokai"))


# ═══════════════════════════════════════════════════════════════════════════════
#  INIT — scaffold a new MCP server project
# ═══════════════════════════════════════════════════════════════════════════════


INIT_SERVER_PY = '''"""{{name}} MCP Server."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{{name}}")


@mcp.tool()
def hello(name: str = "World") -> str:
    """Say hello.

    Args:
        name: Who to greet.
    """
    return f"Hello, {name}!"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: First number.
        b: Second number.
    """
    return a + b


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
'''

INIT_PYPROJECT = '''[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{{slug}}"
version = "0.1.0"
description = "{{description}}"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
]

[project.scripts]
{{slug}} = "{{module}}.server:main"

[tool.setuptools.packages.find]
where = ["src"]
'''

INIT_README = '''# {{name}}

{{description}}

## Installation

```bash
pip install -e .
```

## Usage with Claude Desktop

```json
{
  "mcpServers": {
    "{{slug}}": {
      "command": "python",
      "args": ["-m", "{{module}}.server"]
    }
  }
}
```

## Usage with Claude Code

```bash
claude mcp add {{slug}} -- python -m {{module}}.server
```

## Development

```bash
# Test with mcptools
mcptools inspect python -m {{module}}.server
mcptools test python -m {{module}}.server
mcptools doctor python -m {{module}}.server
```
'''

INIT_GITIGNORE = '''__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
.env
'''


@click.command()
@click.argument("name")
@click.option("--description", "-d", default=None, help="Project description.")
@click.option("--output-dir", "-o", default=".", help="Parent directory for the project.")
def init(name, description, output_dir):
    """Scaffold a new MCP server project.

    \b
    Example:
      mcptools init my-cool-server
      mcptools init my-server -d "Does amazing things"
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    module = slug.replace("-", "_")

    if not description:
        description = Prompt.ask("Description", default=f"{name} MCP server")

    project_dir = Path(output_dir) / slug
    src_dir = project_dir / "src" / module

    if project_dir.exists():
        console.print(f"[red]Directory '{project_dir}' already exists.[/]")
        return

    src_dir.mkdir(parents=True)

    ctx = {"name": name, "slug": slug, "module": module, "description": description}

    def render(template):
        result = template
        for key, val in ctx.items():
            result = result.replace("{{" + key + "}}", val)
        return result

    (src_dir / "__init__.py").write_text(f'"""{{name}} MCP Server."""\n\n__version__ = "0.1.0"\n'.replace("{name}", name))
    (src_dir / "server.py").write_text(render(INIT_SERVER_PY))
    (project_dir / "pyproject.toml").write_text(render(INIT_PYPROJECT))
    (project_dir / "README.md").write_text(render(INIT_README))
    (project_dir / ".gitignore").write_text(INIT_GITIGNORE)

    console.print(
        Panel(
            f"[green]Project created at [bold]{project_dir}[/bold][/]\n\n"
            f"  cd {slug}\n"
            f"  pip install -e .\n"
            f"  mcptools inspect python -m {module}.server\n",
            title="[bold]New MCP Server",
            border_style="green",
        )
    )
