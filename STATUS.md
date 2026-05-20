# sift-mcp — status

> **Pre-session ritual:** `cat STATUS.md && gh pr list && gh issue list && cat BACKLOG.md`. See [CLAUDE.md](CLAUDE.md).

## Active focus

Just shipped **v0.1** — hybrid index + web_search comparison tool (`compare_outlets`) with a 26-outlet pool, smart selection (excludes outlets already in DB to avoid redundancy), and three fallback modes (`auto` / `always` / `never`). Index path runs in ~5–9s; with web fallback, ~10–15s. Preparing the Loom demo for Harish Desai (RealPage SVP) follow-up — `compare_outlets` is the centerpiece for bullet 3 ("MCP connecting AI to a real system / workflow / dataset") in his hiring ask.

## Open strategic questions

Three live unknowns. None block current work; all shape decisions in the next month.

### 1. When does v0.5 become urgent?

What trigger flips this from portfolio-demo posture to production-grade cost caps + auth + HTTP/SSE deploy?

Candidate triggers worth watching:
- Harish (or any RealPage stakeholder) asks for a working URL they can hand to others
- A non-Kristen user signs up for access
- Anthropic monthly bill from this tool crosses $20 (today it's <$1)
- Mobile app project starts and needs an authenticated remote MCP

Until one of those fires, v0.1 is the right posture: solid demo, no production overhead.

### 2. Is `sift-mcp` the right architectural shape?

Or should it eventually merge into `sift-api` as one service with two surfaces (HTTP for the frontend, MCP for AI clients)?

Today they're separate Python services that share a Neon Postgres but nothing else. Pros of merging:
- One deploy target, one set of env vars, one logging surface
- `compare_outlets`-style hybrid logic (DB + LLM) belongs next to the rest of sift-api's LangGraph workflows, not duplicated in two repos
- Easier to add features that span both (e.g., MCP tool that triggers an ingest)

Cons:
- MCP and HTTP have very different request/response shapes; bundling them in one service muddies the codebase
- Independent scaling: MCP traffic patterns will diverge from frontend
- The current separation is honest — they're different products

**What would resolve this:** ~3 months of usage data showing whether the duplication actually causes pain, or building a feature that genuinely needs both surfaces to share code.

### 3. Does the MCP belong inside Sift, or is it a separate product?

A standalone `sift-data-platform` positioning — Sift's curated news corpus + civic dossier graph, exposed as MCP, marketed as a research data layer for AI agents — is a real possibility. The MCP is more general-purpose than the reader UI it sits behind.

Arguments for spinning out:
- Different buyer (AI builders / research orgs vs news readers)
- Different pricing model (API tier vs ad-supported / freemium)
- Different go-to-market (developer relations vs SEO + social)

Arguments for keeping inside Sift:
- Single brand, single story, less surface area to maintain
- Most current value comes from the dossier graph, which only exists because of the reader product

**What would resolve this:** First two reviewer-token users from outside the news/media space (a researcher, a hedge fund, a startup) signals the data-platform angle has demand independent of the reader product.

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

### Code

- `src/sift_mcp/server.py` — five tools (`search_articles`, `get_article`, `get_dossier`, `search_dossiers`, `compare_outlets`)
- `src/sift_mcp/db.py` — asyncpg pool against shared Neon Postgres
- `src/sift_mcp/__init__.py` — `load_dotenv(override=True)` from package-relative path
- `scripts/inspect.sh` — launches MCP Inspector with bumped timeouts (compare_outlets exceeds Inspector's 10s default)
- `README.md` — public-facing setup, tool table, architecture

### Planning + state

- **STATUS.md** (this file) — top-of-mind: active focus, open questions, **Next 3** committed work, blockers, recent decisions
- **BACKLOG.md** — everything deferred, in prose: v0.5 items, stretch items, bugs/quirks to revisit. Items here can be promoted to GitHub issues when work is committed.
- **GitHub issues** — formally tracked work. The Next 3 in STATUS.md all have issues. Other work-worth-tracking that isn't yet committed also lives here. See [`gh issue list`](https://github.com/kristenmartino/sift-mcp/issues).
- **GitHub Project** ([Sift](https://github.com/users/kristenmartino/projects/3)) — board view spanning the 3 Sift repos (sift, sift-api, sift-mcp). Other product families (tenancy, valuate, regrag, portfolio-v2) get their own Projects as the template is replicated.

If you can't find something, search in this order: `gh issue list` → `cat BACKLOG.md` → `git log --oneline` → ask. The pre-session ritual in [CLAUDE.md](CLAUDE.md) hits all four.
