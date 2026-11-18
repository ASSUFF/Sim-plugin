# MCP client snippets

The command assumes `lumerical-fdtd` is on `PATH`. From a clone, use `python` and `-m lumerical-fdtd` instead. Set `LUMERICAL_ROOT` when auto-discovery is not enough.

## Cursor

`~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "lumerical-fdtd": {
      "command": "lumerical-fdtd",
      "env": {
        "LUMERICAL_ROOT": "C:/Program Files/Lumerical/v241"
      }
    }
  }
}
```

## Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json` on Windows, or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS.

```json
{
  "mcpServers": {
    "lumerical-fdtd": {
      "command": "lumerical-fdtd",
      "env": {
        "LUMERICAL_ROOT": "C:/Program Files/Lumerical/v241"
      }
    }
  }
}
```

## Claude Code

Project `.mcp.json`, or:

```bash
claude mcp add lumerical-fdtd -- lumerical-fdtd
```

```json
{
  "mcpServers": {
    "lumerical-fdtd": {
      "command": "lumerical-fdtd"
    }
  }
}
```

## Codex

`~/.codex/config.toml`

```toml
[mcp_servers.lumerical-fdtd]
command = "lumerical-fdtd"
```

## Any other MCP client

Start the stdio server with `lumerical-fdtd`. DeepSeek, Claude, or another model can use it when the surrounding agent exposes MCP tools. A web chat that cannot register a stdio server cannot use this package.
