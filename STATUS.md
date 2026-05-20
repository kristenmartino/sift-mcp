# sift-mcp — status

> **Pre-session ritual:** `cat STATUS.md && gh pr list && gh issue list && cat BACKLOG.md`. See [CLAUDE.md](CLAUDE.md).

## Active focus

**Pending merge into `sift-api`.** Architecture decision landed 2026-05-20; tracked in [`kristenmartino/sift-api#62`](https://github.com/kristenmartino/sift-api/issues/62). All v0.5 hardening work ([#2](https://github.com/kristenmartino/sift-mcp/issues/2) caps, [#4](https://github.com/kristenmartino/sift-mcp/issues/4) hosted transport) is being absorbed into the merge plan. This repo continues to serve stdio MCP tools to Claude Desktop / Code in the meantime.

Just shipped **v0.1** — hybrid index + web_search comparison tool (`compare_outlets`) with a 26-outlet pool, smart selection (excludes outlets already in DB to avoid redundancy), and three fallback modes (`auto` / `always` / `never`). Index path runs in ~5–9s; with web fallback, ~10–15s. The Loom demo for Harish Desai (RealPage SVP) follow-up is still the unblock for any further work — `compare_outlets` is the centerpiece for bullet 3 ("MCP connecting AI to a real system / workflow / dataset") in his hiring ask.

## Open strategic questions

Two live unknowns (one resolved 2026-05-20 — moved to Recent decisions). None block current work; all shape decisions in the next month.

### 1. When does sift-mcp need to expand beyond stdio?

Original trigger: mobile-app project starting + need for hosted MCP. **That trigger is no longer valid** — per `sift-api/docs/MOBILE_PROTOCOL_DECISION.md`, the active Android v1 plan is REST-only and does not use MCP. Remaining triggers worth watching:
- Harish (or any RealPage stakeholder) asks for a working URL they can hand to others
- A non-Kristen user signs up for access
- Anthropic monthly bill from this tool crosses $20 (today it's <$1)
- External agent / framework integration request (Claude.ai custom tool, etc.)

Until one of those fires, stdio-only is the right posture. When one does, it ships as Phase 2 of the merge ([`sift-api#62`](https://github.com/kristenmartino/sift-api/issues/62)) — Bearer auth on a `/mcp` mount inside `sift-api`, not a standalone Railway service.

### 2. Does the MCP belong inside Sift, or is it a separate product?

A standalone `sift-data-platform` positioning — Sift's curated news corpus + civic dossier graph, exposed as MCP, marketed as a research data layer for AI agents — is a real possibility. The MCP is more general-purpose than the reader UI it sits behind.

Arguments for spinning out:
- Different buyer (AI builders / research orgs vs news readers)
- Different pricing model (API tier vs ad-supported / freemium)
- Different go-to-market (developer relations vs SEO + social)

Arguments for keeping inside Sift:
- Single brand, single story, less surface area to maintain
- Most current value comes from the dossier graph, which only exists because of the reader product
- Post-merge into sift-api, the MCP surface is one transport mount, not a separate product

**What would resolve this:** First two reviewer-token users from outside the news/media space (a researcher, a hedge fund, a startup) signals the data-platform angle has demand independent of the reader product. Currently no demand signal.

## Next 3

Issues live in GitHub; this is the human-readable summary. Bullet 1 unchanged from prior STATUS; bullets 2 + 3 are now absorbed into the merge plan.

1. **Record + send Harish Loom** *(immediate, no issue — not engineering work)*. ~4-min walkthrough: reader surface → MCP tools via Claude Desktop → live `compare_outlets` demo → what I'd build at RealPage.
2. **Track [`sift-api#62`](https://github.com/kristenmartino/sift-api/issues/62) — merge into sift-api.** Phase 1 absorbs **[#2 Cost caps](https://github.com/kristenmartino/sift-mcp/issues/2)** (per-call + per-user-day + global daily ceiling, applied uniformly across MCP and REST transports). Phase 2 absorbs (or supersedes) **[#4 HTTP/SSE transport + Bearer auth](https://github.com/kristenmartino/sift-mcp/issues/4)** as a route mount on sift-api, not a separate Railway service. After cleanup, this repo gets archived with a redirect README.
3. **Standalone follow-ups that survive the merge:** [#3 Cache web_search results](https://github.com/kristenmartino/sift-mcp/issues/3), [#6 Per-outlet hit-rate tracking](https://github.com/kristenmartino/sift-mcp/issues/6), [#7 Longform outlet starvation](https://github.com/kristenmartino/sift-mcp/issues/7), [#8 Single-article comparison substitutes the topic](https://github.com/kristenmartino/sift-mcp/issues/8) — all migrate into sift-api during merge cleanup.

## Blocked-on

Nothing engineering-blocked. Work on this repo is paused pending the merge into sift-api; further changes here should be limited to bugfixes that need to ship before merge cleanup.

## Recent decisions

- **2026-05-20** — **Merge `sift-mcp` into `sift-api` as one service with two transports.** Resolves the long-standing "open strategic question" on this repo's shape. Architecture spec in `sift-api/docs/MERGE_MCP_INTO_API.md`. Tracked as `sift-api` [#62](https://github.com/kristenmartino/sift-api/issues/62) with 4 phases. Drivers: existing duplication between `sift-api` `/analyze/compare` and this repo's `compare_outlets`; mobile is REST-only so no hosted-MCP demand from the active Android plan; Ask Sift agent loop (`sift-api` [#63](https://github.com/kristenmartino/sift-api/issues/63)) needs shared handlers.
- **2026-05-20** — **Mobile app is REST-only, not MCP.** Removes the original "mobile app starts" trigger for v0.5 urgency. Stdio posture stays current for v0.1 until a different demand signal appears.
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
- **GitHub issues** — formally tracked work. See [`gh issue list`](https://github.com/kristenmartino/sift-mcp/issues). Note: most v0.5 issues are now rolled into / superseded by `sift-api#62`.
- **GitHub Project** ([Kristen Portfolio](https://github.com/users/kristenmartino/projects/3)) — board view of issues across repos.

If you can't find something, search in this order: `gh issue list` → `cat BACKLOG.md` → `git log --oneline` → ask. The pre-session ritual in [CLAUDE.md](CLAUDE.md) hits all four.
