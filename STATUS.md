# sift-mcp — status

> **Pre-session ritual:** `cat STATUS.md && gh pr list && gh issue list && cat BACKLOG.md`. See [CLAUDE.md](CLAUDE.md).

## Active focus

**Pending merge into `sift-api`.** Architecture decision landed 2026-05-20; tracked in [`kristenmartino/sift-api#62`](https://github.com/kristenmartino/sift-api/issues/62). All v0.5 hardening work ([#2](https://github.com/kristenmartino/sift-mcp/issues/2) caps, [#4](https://github.com/kristenmartino/sift-mcp/issues/4) hosted transport) is being absorbed into the merge plan. This repo continues to serve stdio MCP tools to Claude Desktop / Code in the meantime.

**Post-merge, this repo's 5 tools will serve at least 3 LLM consumers** (per `sift-api/docs/MERGE_MCP_INTO_API.md` and `sift-api/docs/ASK_SIFT_PLAN.md`):
1. External MCP clients (Claude Desktop, Code, agent frameworks) — via sift-api's `/mcp` transport mount
2. Ask Sift internal agent loop (open-ended chat at `/api/ask`) — sift-api #63
3. Refined Compare internal agent loop (lens-driven structured compare at `/api/compare`) — sift-api #63

With multiple internal LLM clients, Pattern Y (unified MCP — see `MERGE_MCP_INTO_API.md`) becomes the more attractive shape: one tool registry, multiple agent loops, one external MCP transport, all in sift-api.

Just shipped **v0.1** — hybrid index + web_search comparison tool (`compare_outlets`) with a 26-outlet pool, smart selection (excludes outlets already in DB to avoid redundancy), and three fallback modes (`auto` / `always` / `never`). Index path runs in ~5–9s; with web fallback, ~10–15s. The Loom demo for Harish Desai (RealPage SVP) follow-up is still the unblock for any further work — `compare_outlets` is the centerpiece for bullet 3 ("MCP connecting AI to a real system / workflow / dataset") in his hiring ask.

## Open strategic questions

Two live unknowns (one resolved 2026-05-20 — moved to Recent decisions). None block current work; all shape decisions in the next month.

### 1. When does sift-mcp need to expand beyond stdio?

Original trigger: mobile-app project starting + need for hosted MCP. **That trigger is no longer valid** — per `sift-api/docs/MOBILE_PROTOCOL_DECISION.md`, the active Android v1 plan is REST-only and does not use MCP (even for Ask Sift + Refined Compare — those run server-side with MCP as internal plumbing). Remaining triggers worth watching:
- Harish (or any RealPage stakeholder) asks for a working URL they can hand to others
- A non-Kristen user signs up for access
- Anthropic monthly bill from this tool crosses $20 (today it's <$1)
- External agent / framework integration request (Claude.ai custom tool, Cursor, Cline, etc.)

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
2. **Track [`sift-api#62`](https://github.com/kristenmartino/sift-api/issues/62) — merge into sift-api.** Phase 1 absorbs **[#2 Cost caps](https://github.com/kristenmartino/sift-mcp/issues/2)** (per-call + per-user-day + global daily ceiling, applied uniformly across MCP and REST transports, and to both internal agent loops Ask Sift + Refined Compare). Phase 2 absorbs (or supersedes) **[#4 HTTP/SSE transport + Bearer auth](https://github.com/kristenmartino/sift-mcp/issues/4)** as a route mount on sift-api, not a separate Railway service. After cleanup, this repo gets archived with a redirect README.
3. **Standalone follow-ups that survive the merge:** [#3 Cache web_search results](https://github.com/kristenmartino/sift-mcp/issues/3), [#6 Per-outlet hit-rate tracking](https://github.com/kristenmartino/sift-mcp/issues/6), [#7 Longform outlet starvation](https://github.com/kristenmartino/sift-mcp/issues/7), [#8 Single-article comparison substitutes the topic](https://github.com/kristenmartino/sift-mcp/issues/8) — all migrate into sift-api during merge cleanup.

## Blocked-on

Nothing engineering-blocked. Work on this repo is paused pending the merge into sift-api; further changes here should be limited to bugfixes that need to ship before merge cleanup.

## Recent decisions

- **2026-08-10** — **`get_article` now returns `context_primer`** (fixed in place despite the pause). The README's tool table always advertised "full article + 'what you should know first' primer + linked entities", but the SELECT never fetched the column — the civic-literacy differentiator was silently missing from the agent surface, on the repo whose whole job is being the demo. Two-line fix (SELECT + returned dict). Carry-over note for the [#62 merge](https://github.com/kristenmartino/sift-api/issues/62): the merged `get_article` handler must include `context_primer` from day one.

- **2026-08-05** — **`judge` removed as an entity type; Justices are politicians.** Reverses the 2026-05-20 entry below. The upstream `judge_profiles` table it was built against turned out to exist **in production and in no repo** — it came from `sift-api` branch `state-mgmt-setup` (commit `9f44ba2`), which never merged, but whose seeders were run against prod by hand. `sift-api` migration 016 moves the nine Justices into `politician_profiles` under `id_source = 'scotus'` and drops the table, following migration 015, which had already reserved that value and already spelled out why a new entity type is not worth its cross-repo cost.

  **This repo was the only wired consumer, and what it served was the problem.** `sift/lib/entityLinks.ts` drops unknown types, so the 87 judge `entity_links` never rendered on the web — but `get_dossier(entity_type="judge")` returned each row's `notes`, which held uncited characterizations of living people ("Confirmed 50-48 after contested hearings", "Authored the Dobbs majority opinion (2022)") sourced to Wikipedia. `sift/docs/OPERATING_CONTEXT.md` §5 forbids exactly that. Sourced replacements — office title from 28 U.S.C. § 1, confirmation date/tally/roll-call from senate.gov — now live on the politician rows, reachable as `get_dossier("politician", "SCOTUS-ROBERTS-J")`.

  Tool surface change: `EntityType` drops `judge`; `get_dossier` and `search_dossiers` lose their `judge` branch. README updated.

- **2026-05-20** — **Merge `sift-mcp` into `sift-api` as one service with two transports.** Resolves the long-standing "open strategic question" on this repo's shape. Architecture spec in `sift-api/docs/MERGE_MCP_INTO_API.md`. Tracked as `sift-api` [#62](https://github.com/kristenmartino/sift-api/issues/62) with 4 phases. Drivers: existing duplication between `sift-api` `/analyze/compare` and this repo's `compare_outlets`; mobile is REST-only so no hosted-MCP demand from the active Android plan; Ask Sift agent loop + Refined Compare agent loop (sift-api [#63](https://github.com/kristenmartino/sift-api/issues/63)) need shared handlers.
- **2026-05-20** — **Tool surface gains multiple internal LLM consumers.** Ask Sift + Refined Compare are sibling specialized agents inside sift-api; they share this repo's 5 handlers (post-merge). Pattern Y (unified MCP) becomes the cleaner architectural choice over Pattern X with multiple internal LLM clients consuming the same registry. See `sift-api/docs/ASK_SIFT_PLAN.md` and `sift-api/docs/REFINED_COMPARE_PLAN.md`.
- **2026-05-20** — **Mobile app is REST-only, not MCP** — even agentic features (Ask Sift, Refined Compare) use REST/SSE from the app's perspective. The agent loops run server-side; MCP is internal plumbing. Removes the original "mobile app starts" trigger for v0.5 urgency. Stdio posture stays current for v0.1 until a different demand signal appears.
- ~~**2026-05-20** — **Added `judge` as a fifth entity type to `get_dossier` / `search_dossiers`.**~~ **Reversed 2026-08-05, see above.** Upstream sift-api Phase 3.J added a `judge_profiles` table (9 SCOTUS justices) separate from `politician_profiles` because the metadata shape diverges (court, nominating president, confirmation year vs party/state/chamber). MCP now exposes judges with `canonical_id` slugs like `SCOTUS-ROBERTS-J`. Same change closes the upstream linker's org/judge-blindness bug (post-backfill: 1,048 org links + 87 judge links across last 7 days, up from 0/0). — *The "upstream" it depended on was an unmerged branch; the org-linking half was later solved independently on `main` by sift-api #129's curated aliases, and the judge half never reached `main` at all.*
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
- **GitHub issues** — formally tracked work. See [`gh issue list`](https://github.com/kristenmartino/sift-mcp/issues). Note: most v0.5 issues are now rolled into / superseded by `sift-api#62`. The 5 tools also feed `sift-api#63` (Ask Sift + Refined Compare) as the internal agent loops' shared tool surface.
- **GitHub Project** ([Sift](https://github.com/users/kristenmartino/projects/3)) — board view spanning the 3 Sift repos (sift, sift-api, sift-mcp). Other product families (tenancy, valuate, regrag, portfolio-v2) get their own Projects as the template is replicated.

If you can't find something, search in this order: `gh issue list` → `cat BACKLOG.md` → `git log --oneline` → ask. The pre-session ritual in [CLAUDE.md](CLAUDE.md) hits all four.
