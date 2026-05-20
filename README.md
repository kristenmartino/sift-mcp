# sift-mcp

MCP server exposing **[Sift](https://siftnews.kristenmartino.ai)** — a news aggregator with civic footnotes — to any MCP-compatible AI client (Claude Desktop, Claude Code, etc.).

Sift reads from ~50 outlets across the political spectrum, AI-summarizes today's stories across 10 categories, and on top of that links every politician, organization, bill, and outlet in an article to a structured dossier sourced from public records (OpenSecrets, GovTrack, ProPublica Nonprofit Explorer, FARA, FEC, Vote Smart, AllSides, MBFC).

This MCP makes that dossier graph queryable from an AI client.

- **Live product:** [siftnews.kristenmartino.ai](https://siftnews.kristenmartino.ai)
- **Case study:** [kristenmartino.ai/work/sift](https://kristenmartino.ai/work/sift)

---

## Tools

| Tool | What it does | Latency |
|---|---|---|
| `search_articles(query, category?, limit?)` | Vector search over the pre-built article index. Returns articles ranked by semantic relevance. | ~50 ms |
| `get_article(article_id)` | Full article + *"what you should know first"* primer + linked entities. | ~50 ms |
| `get_dossier(entity_type, slug)` | Politician / org / bill / outlet dossier with public-records citations. | ~50 ms |
| `search_dossiers(entity_type, query, limit?)` | Find a dossier by name. | ~50 ms |
| `compare_outlets(topic, outlets?, article_limit?, web_fallback?)` | Hybrid cross-outlet claim comparison. Always reads Sift's index (sub-second vector search + Haiku claim extraction with `article_id` citations). When index coverage is sparse (top score < 0.42, < 3 outlets, or < 5 articles) — and `web_fallback != "never"` — also runs Claude `web_search` in parallel across mainstream outlets and merges claims tagged with `source: "index" \| "web"`. | 5–9 s (index-only) · 15–25 s (with web) |

`entity_type` is one of `politician`, `org`, `bill`, `outlet`.

All five tools read from the same Neon Postgres that powers the live product. `compare_outlets` additionally makes one Claude Haiku call for claim extraction — no separate workflow service to deploy.

---

## Setup (local stdio)

Prereqs: Python 3.12+, [`uv`](https://github.com/astral-sh/uv).

```bash
cd sift-mcp
cp .env.example .env
# Fill in DATABASE_URL, VOYAGE_API_KEY, and ANTHROPIC_API_KEY (same values as sift-api).
uv sync
```

Verify the server works with the MCP Inspector (browser UI for poking tools):

```bash
./scripts/inspect.sh
```

This wraps `uv run mcp dev src/sift_mcp/server.py` and pre-sets `MCP_SERVER_REQUEST_TIMEOUT=120000` + `MCP_REQUEST_MAX_TOTAL_TIMEOUT=180000` so the `compare_outlets` tool (which runs live AI for ~15–60s) doesn't trip Inspector's 10s default. The four Postgres-backed tools work the same either way.

Then call each tool with sample inputs to confirm DB access + Voyage embeddings are wired correctly before connecting to a real client.

---

## Wire to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "sift": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/sift-mcp",
        "python",
        "-m",
        "sift_mcp.server"
      ],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host/db?sslmode=require",
        "VOYAGE_API_KEY": "pa-...",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

`ANTHROPIC_API_KEY` is only required for `compare_outlets`. Omit it and the other four tools still work.

Restart Claude Desktop. In a new conversation:

> What tools do you have from Sift?

You should see the five tools listed. Then try the canonical demos:

> Brief me on energy-policy news this week and walk me through who the major players are.

Claude will call `search_articles` → `get_article` → `get_dossier` and assemble a briefing grounded in Sift's data, with citations to the public records the dossiers come from.

> Compare how outlets are covering the South Carolina redistricting fight.

Claude will call `compare_outlets`, which pulls the top-ranked articles for that topic from Sift's index, groups them by outlet, and returns claims with `unanimous` / `disputed` / `unique` agreement labels plus `article_id` citations Claude can drill into via `get_article`.

---

## Wire to Claude Code

```bash
claude mcp add sift uv run --directory /absolute/path/to/sift-mcp python -m sift_mcp.server
```

Configure env vars via your shell profile or by editing `~/.claude.json` to add an `env` block on the server entry.

---

## Architecture

- **One surface, one DB.** All five tools read from the same Neon Postgres that powers sift-api + the Next.js frontend. No separate workflow service, no separate cache, no separate DB.
- **Tool-per-handler**: each tool is one async function with one or two SQL queries against the canonical tables (`articles`, `politician_profiles`, `org_profiles`, `bill_profiles`, `outlet_profiles`).
- **`compare_outlets` is a hybrid two-path tool.** Index path = vector search + Claude Haiku claim extraction over articles Sift has already curated. Web path = Claude with the `web_search_20250305` tool, fans out across mainstream outlets for fresh coverage. Both paths run in parallel when the web path fires; claims are merged into a single array tagged with `source: "index" | "web"`. Web fires when index coverage falls below a sparsity threshold (`top_score < 0.42`, `< 3 outlets`, or `< 5 articles`) — or always/never if the caller overrides via the `web_fallback` arg.
- **Stdio transport** for v0.1: subprocess of the MCP client; nothing to deploy.
- **`asyncpg` connection pool**, lazy-initialized; safe under concurrent tool calls.

## Roadmap

- **v0**: stdio + 4 read-only Postgres tools.
- **v0.1 (current)**: `compare_outlets(topic, outlets?, article_limit?, web_fallback?)` — hybrid index + web_search comparison. Index always primary; web auto-fires when index is sparse. Unified claims output with provenance tags.
- **v0.5**: HTTP/SSE transport, Bearer token auth, per-token + global Anthropic cost caps, Railway deploy at `mcp.siftnews.kristenmartino.ai`. Issue read-only `demo` tokens publicly and `reviewer` tokens to specific contacts.

## Why this exists

Sift's civic-literacy layer is the part of the product worth surfacing to AI clients — anyone (or any AI assistant) can do a useful thing with *"give me the structured dossier for Senator X"* or *"what did outlets emphasize about this Senate vote."* The MCP turns Sift from "a news app you read" into "a civic-context layer any AI client can call."

## License

MIT.
