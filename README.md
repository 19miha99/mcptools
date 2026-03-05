# mcptools

> The missing developer toolkit for the Model Context Protocol ecosystem.

[![PyPI version](https://img.shields.io/pypi/v/mcpdevkit?color=blue)](https://pypi.org/project/mcpdevkit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)

**Inspect, test, benchmark, validate, and document any MCP server from the command line.**

```bash
pip install mcpdevkit
```

```
$ mcptools inspect python -m my_server
+-------------------------------- MCP Server ---------------------------------+
| Tools:     12                                                               |
| Resources: 0                                                                |
| Prompts:   0                                                                |
+-----------------------------------------------------------------------------+
                                     Tools
+-----+----------------------+------------------------------------+----------+
| #   | Name                 | Description                        | Params   |
|-----+----------------------+------------------------------------+----------|
| 1   | get_weather          | Get current weather for a city     | 1req/1   |
| 2   | search_docs          | Search documentation               | 1req/2   |
| ... | ...                  | ...                                | ...      |
+-----+----------------------+------------------------------------+----------+
```

## Why mcptools?

Building MCP servers is the easy part. Testing, debugging, and documenting them isn't.

| Without mcptools | With mcptools |
|---|---|
| Write custom test scripts for each server | `mcptools test python -m my_server` |
| Manual protocol inspection via logs | `mcptools inspect python -m my_server` |
| Guess where performance bottlenecks are | `mcptools bench python -m my_server` |
| Hope your server follows best practices | `mcptools doctor python -m my_server` |
| Hand-write API documentation | `mcptools docs -o API.md python -m my_server` |
| Copy-paste boilerplate for new servers | `mcptools init my-new-server` |

- **`inspect`** — Instantly see what tools a server exposes, with parameter schemas
- **`test`** — Interactively call tools with guided parameter input and pretty output
- **`bench`** — Measure response times for every tool (min/avg/max/p95)
- **`doctor`** — 10-point health check for best practices and common bugs
- **`docs`** — Auto-generate markdown API documentation
- **`init`** — Scaffold a new MCP server project in seconds

Works with **any** MCP server — Python, TypeScript, Go, Rust. If it speaks stdio, mcptools can talk to it.

## Installation

```bash
pip install mcpdevkit
```

Or from source:

```bash
git clone https://github.com/19miha99/mcptools.git
cd mcptools
pip install -e .
```

## Quick Start

```bash
# See what tools a server has
mcptools inspect python -m my_server

# Test tools interactively
mcptools test python -m my_server

# Health check
mcptools doctor python -m my_server

# Generate API docs
mcptools docs -o API.md python -m my_server

# Benchmark
mcptools bench python -m my_server

# Start a new MCP server project
mcptools init my-awesome-server
```

## Commands

### `mcptools inspect`

Connect to an MCP server and display all available tools, resources, and prompts.

```bash
# Compact view
mcptools inspect python -m my_server

# Detailed view with full parameter schemas
mcptools inspect -d python -m my_server

# Works with any MCP server
mcptools inspect npx -y @anthropic/mcp-server-filesystem /tmp
```

### `mcptools test`

Interactively test tools with guided parameter input.

```bash
# Interactive mode — pick tools from a list
mcptools test python -m my_server

# Test a specific tool
mcptools test -t get_weather python -m my_server

# Pass arguments as JSON
mcptools test -t get_weather -j '{"city": "Tokyo"}' python -m my_server
```

Features:
- Auto-detects parameter types from JSON schema
- Shows required vs optional parameters with defaults
- Pretty-prints JSON responses
- Measures response time

### `mcptools bench`

Benchmark tool response times across multiple iterations.

```bash
# Benchmark all tools (5 iterations each)
mcptools bench python -m my_server

# Custom iterations
mcptools bench -n 20 python -m my_server

# Benchmark a specific tool
mcptools bench -t get_weather -n 50 python -m my_server
```

Output:
```
Benchmarking 8 tools (5 iterations each)
+-----------------------+--------+--------+--------+--------+--------+
| Tool                  |    Min |    Avg |    Max |    P95 | Status |
|-----------------------+--------+--------+--------+--------+--------|
| get_weather           |   45ms |   52ms |   68ms |   65ms |     OK |
| search_docs           |  120ms |  145ms |  190ms |  185ms |     OK |
| get_config            |    8ms |   12ms |   18ms |   17ms |     OK |
| update_record         |      - |      - |      - |      - |   SKIP |
+-----------------------+--------+--------+--------+--------+--------+
```

Tools with required parameters are skipped (can't auto-test without proper args).

### `mcptools doctor`

Run a 10-point health check that catches common issues.

```bash
mcptools doctor python -m my_server
```

Checks:
1. Server starts successfully
2. Tools endpoint responds
3. All tools have descriptions
4. All parameters have descriptions
5. No duplicate tool names
6. Names follow snake_case convention
7. Schemas are valid JSON Schema
8. A tool call succeeds within 5s
9. Resources endpoint works
10. Prompts endpoint works

Output:
```
  PASS Server starts successfully
  PASS Tools endpoint works (12 tools found)
  PASS All tools have descriptions
  WARN 3 parameters without descriptions
  PASS No duplicate tool names
  ...

+---- Doctor Report ----+
| 9/10 checks (1 warn)  |
+-----------------------+
```

### `mcptools docs`

Auto-generate markdown documentation from tool schemas.

```bash
# Print to stdout
mcptools docs python -m my_server

# Write to file
mcptools docs -o API.md python -m my_server
```

Generates a clean markdown document with:
- Tool names and descriptions
- Parameter tables (name, type, required, default, description)
- Ready to paste into your README

### `mcptools init`

Scaffold a new MCP server project with best practices.

```bash
mcptools init my-cool-server
mcptools init my-server -d "Does amazing things"
```

Generates:
```
my-cool-server/
├── pyproject.toml       # Ready for pip install -e .
├── README.md            # With Claude Desktop/Code setup instructions
├── .gitignore
└── src/my_cool_server/
    ├── __init__.py
    └── server.py        # Sample server with 2 example tools
```

## Works With Any MCP Server

mcptools connects via **stdio transport** — the standard way MCP servers communicate. It works with servers written in any language:

```bash
# Python servers
mcptools inspect python -m my_server

# TypeScript/Node servers
mcptools inspect npx -y @anthropic/mcp-server-filesystem /tmp

# Any executable
mcptools inspect ./my-rust-mcp-server
```

## Requirements

- Python 3.10+
- `mcp` — MCP SDK (client)
- `click` — CLI framework
- `rich` — Beautiful terminal output

## Contributing

Contributions welcome! Areas of interest:
- SSE/HTTP transport support
- More doctor checks
- Test fixtures and automated testing
- Shell completions
- Config file support (named server aliases)

## License

MIT
