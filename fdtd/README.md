# lumerical-fdtd

统一入口是在插件根目录执行 `python -m sim_plugin fdtd`。使用说明见同目录的 `使用说明.md`，总说明见上一级的 `使用说明.md` 和 `README.md`。

MCP server that drives a local Ansys Lumerical FDTD install. Cursor, Claude Desktop, Claude Code, Codex, and any other MCP client can call the same tools. The server does not call a language model; the agent does.

This directory is the project to publish. Do not put the parent simulation folder, result files, or a virtual environment in the GitHub repository.

## Requirements

- Python 3.10 or newer for the MCP server.
- A separately installed and licensed copy of Ansys Lumerical. This package does not contain `lumapi.py`, the solver, or a license. See `NOTICE`.

## Install

```bash
pip install -e ".[dev]"
```

After this repository is on GitHub, an MCP client can also start it with `uvx --from git+https://github.com/OWNER/lumerical-fdtd lumerical-fdtd`.

## Find Lumerical

The server searches `Program Files\Lumerical\v*` on each Windows drive, and `/opt/lumerical` or `~/lumerical` on Linux. Override it when the install lives somewhere else:

| Variable | Meaning |
|---|---|
| `LUMERICAL_ROOT` | Version directory that contains `api/python/lumapi.py` |
| `LUMERICAL_PYTHON` | Python used to import `lumapi`. Defaults to Lumerical's bundled interpreter |
| `LUMERICAL_FDTD_RUNS` | Parent of the run folders. Defaults to `./runs` |

Windows paths in JSON can use forward slashes (`S:/Program Files/Lumerical/v241`). Linux paths are already forward slashes. A `script_file` passed to `fdtd_run` must be an absolute path. On the command line, a relative `script_file` is resolved next to the spec file.

Check the discovery result without launching the GUI:

```bash
python -m lumerical_fdtd.discover
```

## Tools

| Tool | License required | What it does |
|---|---|---|
| `fdtd_doctor` | no | Report the install path and runs directory |
| `fdtd_validate` | no | Check a spec |
| `fdtd_inspect` | yes | Open a `.fsp` and list objects |
| `fdtd_run` | yes | Build or open a simulation, run it, and return monitor data |

`fdtd_run` keeps the GUI hidden unless the spec sets `hide_gui` to false. A license dialog from Ansys can still appear. The solver writes `runs/<timestamp>_<name>/`, including a copy of the project. An existing `.fsp` passed in `project` is not modified. The project is saved again after `run()` and before results are read, so a failed export does not discard a finished solve.

`kind: "transmission"` calls `transmission(monitor)`. This Lumerical build does not accept a source argument. With several sources, the number is the fraction of total source power through that monitor.

## Spec

Units are metres and seconds. The schema is `src/lumerical_fdtd/schemas/fdtd-spec.schema.json`. Validate without a license:

```bash
python -m lumerical_fdtd.validate examples/smoke_2d.json
```

Material names must already exist in the Lumerical material database, for example `Si (Silicon) - Palik`, `SiO2 (Glass) - Palik`, and `Si3N4 (Silicon Nitride) - Luke`.

## Connect an agent

Use one command for every client: `lumerical-fdtd` after installation, or `python -m lumerical_fdtd` from this repository. Copy `agent/SKILL.md` into the client's skill directory so the agent knows when to call the tools. The model behind the agent can be any model that client supports.

| Client | Config |
|---|---|
| Cursor | `~/.cursor/mcp.json` |
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code | `.mcp.json` or `claude mcp add` |
| Codex | `~/.codex/config.toml` |

Snippets are in `agent/clients.md`. A client without MCP, including a normal web chat, cannot load this server.

## Tests

```bash
pytest
```

The licensed smoke simulation is off unless you set `LUMERICAL_FDTD_INTEGRATION=1`.

## 中文

这是一个本地 Lumerical FDTD 的 MCP 服务。Cursor、Claude、Codex，以及其他支持 MCP 的代理用同一套工具。插件不调用模型，模型通过工具调用插件。

发布到 GitHub 时，只上传本目录。不要上传上一级仿真目录、`runs`、`.fsp` 或虚拟环境。

使用者需要自己安装并授权 Ansys Lumerical。安装位置可以用 `LUMERICAL_ROOT` 指定。结果写在 `LUMERICAL_FDTD_RUNS` 或当前目录的 `runs` 下，默认不显示界面，也不会覆盖原来的 `.fsp`。
