# sift-mcp — status

> **Pre-session ritual:** `cat STATUS.md && gh pr list && gh issue list && cat BACKLOG.md`. See [CLAUDE.md](CLAUDE.md).

## Active focus

Just shipped **v0.1** — hybrid index + web_search comparison tool (`compare_outlets`) with a 26-outlet pool, smart selection (excludes outlets already in DB to avoid redundancy), and three fallback modes (`auto` / `always` / `never`). Index path runs in ~5–9s; with web fallback, ~10–15s. Preparing the Loom demo for Harish Desai (RealPage SVP) follow-up — `compare_outlets` is the centerpiece for bullet 3 ("MCP connecting AI to a real system / workflow / dataset") in his hiring ask.

## Open strategic question

**When does v0.5 become urgent — i.e., what trigger flips this from portfolio-demo posture to production-grade cost caps + auth + HTTP/SSE deploy?**

Candidate triggers worth watching:
- Harish (or any RealPage stakeholder) asks for a working URL they can hand to others
- A non-Kristen user signs up for access
- Anthropic monthly bill from this tool crosses $20 (today it's <$1)
- Mobile app project starts and needs an authenticated remote MCP

Until one of those fires, v0.1 is the right posture: solid demo, no production overhead.

## Next 3

Issues live in GitHub; this is the human-readable summary.

1. **Record + send Harish Loom** *(immediate, no issue — not engineering work)*. ~4-min walkthrough: reader surface → MCP tools via Claude Desktop → live `compare_outlets` demo → what I'd build at RealPage.
2. **[#2 Cost caps for compare_outlets](https://github.com/kristenmartino/sift-mcp/issues/2)** *(tier-v0.5, effort-week, blocked on demo)*. Per-call token budget, per-token daily cap (once HTTP/SSE ships), org-level daily ceiling. Surface remaining budget in tool response.
3. **[#4 HTTP/SSE transport + Railway deploy + Bearer auth](https://github.com/kristenmartino/sift-mcp/issues/4)** *(tier-v0.5, effort-week, blocked on demo)*. Deploy at `mcp.siftnews.kristenmartino.ai`. Bearer token auth. Demo + reviewer token tiers.

Also queued: **[#3 Cache web_search results](https://github.com/kristenmartino/sift-mcp/issues/3)** *(tier-v0.5, effort-day)* — natural follow-up to #2 once cost-cap data shows hot paths.

## Blocked-on

Nothing engineering-blocked. v0.5 work is gated on **demand signal**, not technical capacity. Open question above is the trigger to watch.

## Recent decisions

- **Hybrid index + web_search architecture for `compare_outlets`.** Considered three routing options (proxy sift-api / direct web_search in MCP / new sift-api endpoint). Chose direct in MCP because the alternative routes either hardcoded 3 sources (sift-api) or required cross-repo refactor scope creep (new endpoint). Smart conditional fallback (`auto` mode) avoids paying for web when DB has good coverage.
- **26-outlet pool with smart DB-exclusion selection.** Originally 4 hardcoded defaults; expanded to 26 (wires, broadsheets, political, financial, broadcast, longform/investigative) after validation showed the small pool produced poor fallback diversity. Selection per call excludes outlets already in the index result so web genuinely supplements rather than duplicates.
- **`load_dotenv(override=True)`.** `.env` always wins over shell env. Predictable for solo development; documented in BACKLOG as a sharp edge to revisit once CI / multi-env deployment matters.
- **Unified `claims` array tagged with `source: "index" | "web"`.** Considered separate sections; chose unified for one consistent shape that AI clients can filter on. Provenance is preserved without forcing two output schemas on every consumer.

## Where things live

- `src/sift_mcp/server.py` — five tools (`search_articles`, `get_article`, `get_dossier`, `search_dossiers`, `compare_outlets`)
- `src/sift_mcp/db.py` — asyncpg pool against shared Neon Postgres
- `src/sift_mcp/__init__.py` — `load_dotenv(override=True)` from package-relative path
- `scripts/inspect.sh` — launches MCP Inspector with bumped timeouts (compare_outlets exceeds Inspector's 10s default)
- `BACKLOG.md` — deferred items by version + bugs/quirks to revisit
- `README.md` — public-facing setup, tool table, architecture
