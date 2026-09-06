# MCP Documentation Server

## Overview

This documentation is also served as an **MCP server**, so AI coding agents can query it
directly instead of you copy-pasting pages into a chat. Same markdown you are reading now,
exposed as three callable tools over the Model Context Protocol.

The server is read-only and versioned with the API release. At release `1.3.0`, it serves the
same source tree used by MkDocs, including release notes, API contracts, compatibility rules,
usage schema versions, migration commands, runtime-mode guidance, and container dependency
guidance. It cannot inspect your assistant records, provider account, Docker host, or current
deployment; answers about those must be qualified as deployment-specific.

Add the URL once to your agent and ask questions like "how do I trigger an outbound call
with this API?" — the agent searches the docs, reads the right page, and answers with the
real endpoint paths, fields and payloads.

## Endpoint

- **URL**: `https://api-livekit-vyom.indusnettechnologies.com/mcp`
- **Transport**: Streamable HTTP (`POST` JSON-RPC 2.0)
- **Authentication**: Not required — same public content as `/documentation`
- **Server name**: `livekit-api-docs`

## Tools

| Tool | Arguments | Returns |
| :--- | :--- | :--- |
| `list_docs` | — | Every page's path and title, grouped by section (table of contents). |
| `get_doc` | `path` (string) | One page as raw markdown. `.md` suffix optional, e.g. `api/calls/trigger`. |
| `search_docs` | `query` (string), `limit` (int, default `8`) | Ranked matches: path, title, score and a short snippet per hit. |

`search_docs` is keyword-based — it counts how often your words appear in each page and
weights title matches higher. Start there, then call `get_doc` on the most promising path.

## Reliable answer workflow

For an agent answering a user through MCP:

1. Call `search_docs` with the user's main nouns and endpoint/model/config names.
2. Call `get_doc` for the most specific API or reference page returned. Use `list_docs` when the
   question spans multiple areas.
3. Check `reference/compatibility.md`, `reference/models.md`, and the relevant create/update page
   for configuration questions. Check `reference/usage-accounting.md` for usage or cost questions.
4. Check `changelog.md` for release-specific behavior, breaking changes, and migrations, but do
   not use a changelog as the sole source for an endpoint contract.
5. Answer only from retrieved documentation. Never invent an endpoint, model ID, default, price,
   migration, or provider capability. If the pages do not establish an answer, say that the
   documentation does not establish it and identify the page or API information needed.
6. State version-sensitive facts, schema versions, nullable fields, and whether a cost is an
   estimate. Distinguish documented defaults from values supplied by the user's deployment.

## Add it to your agent

No install, no API key — one URL. Config key names differ per client, so pick your tab.

=== "Claude Code"

    ```bash
    claude mcp add --transport http livekit-docs https://api-livekit-vyom.indusnettechnologies.com/mcp
    ```

    Add `--scope project` to share it with your team via `.mcp.json`, or `--scope user`
    to make it available in every project on your machine.

    Verify with `claude mcp list`, or run `/mcp` inside a session to see the three tools.

=== "opencode"

    Add an `mcp` block with `"type": "remote"`. Project config is `opencode.json` in your
    repo root; global config is `~/.config/opencode/opencode.json`.

    ```json
    {
      "$schema": "https://opencode.ai/config.json",
      "mcp": {
        "livekit-docs": {
          "type": "remote",
          "url": "https://api-livekit-vyom.indusnettechnologies.com/mcp",
          "enabled": true
        }
      }
    }
    ```

    Restart opencode, then check it with:

    ```bash
    opencode mcp list
    ```

    `opencode mcp debug livekit-docs` diagnoses connection problems. No `headers` block is
    needed here — this endpoint is unauthenticated.

=== "Claude Desktop"

    Edit `claude_desktop_config.json` — `%APPDATA%\Claude\` on Windows,
    `~/Library/Application Support/Claude/` on macOS, `~/.config/Claude/` on Linux — then
    restart the app:

    ```json
    {
      "mcpServers": {
        "livekit-docs": {
          "type": "http",
          "url": "https://api-livekit-vyom.indusnettechnologies.com/mcp"
        }
      }
    }
    ```

=== "Cursor"

    Create `.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` for every project):

    ```json
    {
      "mcpServers": {
        "livekit-docs": {
          "type": "http",
          "url": "https://api-livekit-vyom.indusnettechnologies.com/mcp"
        }
      }
    }
    ```

=== "VS Code / Copilot"

    Create `.vscode/mcp.json` in your project — note the key is `servers`, not
    `mcpServers`. Commit the file to share it with your team; for a machine-wide install run
    the **MCP: Open User Configuration** command instead.

    ```json
    {
      "servers": {
        "livekit-docs": {
          "type": "http",
          "url": "https://api-livekit-vyom.indusnettechnologies.com/mcp"
        }
      }
    }
    ```

    Or one line from the terminal:

    ```bash
    code --add-mcp '{"name":"livekit-docs","type":"http","url":"https://api-livekit-vyom.indusnettechnologies.com/mcp"}'
    ```

    Then switch Copilot Chat to **Agent** mode and open the tools picker.

=== "Gemini CLI"

    Add to `~/.gemini/settings.json` (or `.gemini/settings.json` in your project). The
    streamable-HTTP key is `httpUrl`, not `url`:

    ```json
    {
      "mcpServers": {
        "livekit-docs": {
          "httpUrl": "https://api-livekit-vyom.indusnettechnologies.com/mcp",
          "timeout": 10000
        }
      }
    }
    ```

    List what got loaded with `/mcp` inside the CLI.

=== "Codex CLI"

    Direct HTTP needs the RMCP client turned on in `~/.codex/config.toml`:

    ```toml
    experimental_use_rmcp_client = true

    [mcp_servers.livekit-docs]
    url = "https://api-livekit-vyom.indusnettechnologies.com/mcp"
    startup_timeout_sec = 20
    tool_timeout_sec = 60
    ```

    Confirm with `codex mcp list`. On older Codex builds the flag lives under a `[features]`
    block instead — check `codex mcp list` output if the server does not appear.

=== "Zed"

    Zed's `context_servers` expects a command, so bridge through `mcp-remote`. Add to
    `~/.config/zed/settings.json` — Zed restarts the server process on save:

    ```json
    {
      "context_servers": {
        "livekit-docs": {
          "source": "custom",
          "command": "npx",
          "args": ["-y", "mcp-remote", "https://api-livekit-vyom.indusnettechnologies.com/mcp"],
          "env": {}
        }
      }
    }
    ```

=== "Any stdio-only client"

    Older clients that speak only stdio can reach the endpoint through the `mcp-remote`
    bridge (needs Node):

    ```json
    {
      "mcpServers": {
        "livekit-docs": {
          "command": "npx",
          "args": ["-y", "mcp-remote", "https://api-livekit-vyom.indusnettechnologies.com/mcp"]
        }
      }
    }
    ```

### Local development

Running the API yourself? Point at your own server — pages are read from the local `docs/`
directory, so your unpublished edits are visible immediately after a restart.

```bash
claude mcp add --transport http livekit-docs-local http://localhost:8000/mcp
```

Swap the URL in any of the configs above for `http://localhost:8000/mcp`.

### Try it

Once connected, ask your agent things like:

- "Using the livekit-docs MCP, how do I trigger an outbound call?"
- "What fields does `assistant_tts_config` take for Cartesia?"
- "Show me the end-of-call webhook payload."
- "Which STT providers are supported and how do I switch?"
- "What changed in 1.3.0, and which migrations are required?"
- "Which container owns this dependency, and does it affect runtime RAM or only image size?"

## Example Request

Raw JSON-RPC, if you want to check the endpoint by hand:

```bash
curl -sN -X POST "https://api-livekit-vyom.indusnettechnologies.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_docs",
      "arguments": { "query": "trigger outbound call payload", "limit": 3 }
    }
  }'
```

The response is a Server-Sent Events stream carrying one JSON-RPC message. A real MCP
client handles `initialize` and session headers for you.

## HTTP Status Codes

| Code | Description |
| :--- | :--- |
| 200 | JSON-RPC response returned (check the body for a JSON-RPC `error` object). |
| 400 | Malformed request — missing `Accept: text/event-stream`, or invalid JSON-RPC. |
| 406 | Client did not accept both `application/json` and `text/event-stream`. |

## Notes

- Serves **markdown**, not the rendered HTML at `/documentation` — markdown is what LLMs read best.
- Read-only. No tool here can create, update or delete anything in your account.
- Stateless HTTP: no session state to lose, so it works behind multiple Gunicorn workers.
- Pages are indexed in memory on first use and are fixed for the life of the process. A deploy
  that ships new docs picks them up on restart.
