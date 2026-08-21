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

Two live unknowns (one resolved 2026-05-20 — archived in [`docs/STATUS_ARCHIVE.md`](docs/STATUS_ARCHIVE.md)). None block current work; all shape decisions in the next month.

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

## Next 3 — moved to GitHub

**This section is gone deliberately — preventively, not reactively.** Nothing in this repo's own history shows
a Next-3 entry going stale (the Loom-follow-up bullet that carried over unchanged from the prior STATUS was
still accurate, just still pending). This repo is small enough that the old convention wasn't broken here yet.
It's being retired anyway, for consistency with `sift` and `sift-api`, where the hand-maintained version did
rot — before this file grows to the point where it would too.

    gh issue list --state open            # the engineering queue
    gh pr list --state open               # in flight

Priority lives in issue labels and the [project board](https://github.com/users/kristenmartino/projects/3).
The Loom-recording task has no issue (it isn't engineering work) — it's tracked in Active focus above instead.

## Blocked-on — moved to GitHub

**Also gone deliberately, same reasoning.**

    gh issue list --state open

(No `blocked` label exists in this repo yet — add `--label blocked` to the command above once one does.)

### What this file is for

STATUS.md holds no current state of its own. Current state lives in GitHub issues/PRs, and in Active focus above
(bounded, current, rewritten not appended). What has no home in GitHub is the cross-issue record — we measured X,
it refuted Y, here is why we did not do Z. Architecture-level decisions promote further into
[`sift/docs/DECISIONS.md`](https://github.com/kristenmartino/sift/blob/main/docs/DECISIONS.md) in the sibling repo,
which is the cross-repo canonical decision log. An entry below describes what was true on its date and is never
edited to stay current.

## Recent decisions (last 7 days)

**Entries before 2026-08-13 are archived** in [`docs/STATUS_ARCHIVE.md`](docs/STATUS_ARCHIVE.md). This section
held 10 entries going back to 2026-05-20 (plus a handful of undated architecture-decision bullets from the same
v0.1 build period, archived alongside them) — all now archived.

Nothing in the last 7 days.

## Where things live

### Code

- `src/sift_mcp/server.py` — five tools (`search_articles`, `get_article`, `get_dossier`, `search_dossiers`, `compare_outlets`)
- `src/sift_mcp/db.py` — asyncpg pool against shared Neon Postgres
- `src/sift_mcp/__init__.py` — `load_dotenv(override=True)` from package-relative path
- `scripts/inspect.sh` — launches MCP Inspector with bumped timeouts (compare_outlets exceeds Inspector's 10s default)
- `README.md` — public-facing setup, tool table, architecture

### Planning + state

- **STATUS.md** (this file) — top-of-mind: active focus, open questions, recent decisions (last 7 days). Next 3 and Blocked-on live in GitHub issues/PRs now, not here.
- **BACKLOG.md** — everything deferred, in prose: v0.5 items, stretch items, bugs/quirks to revisit. Items here can be promoted to GitHub issues when work is committed.
- **GitHub issues** — formally tracked work. See [`gh issue list`](https://github.com/kristenmartino/sift-mcp/issues). Note: most v0.5 issues are now rolled into / superseded by `sift-api#62`. The 5 tools also feed `sift-api#63` (Ask Sift + Refined Compare) as the internal agent loops' shared tool surface.
- **GitHub Project** ([Sift](https://github.com/users/kristenmartino/projects/3)) — board view spanning the 3 Sift repos (sift, sift-api, sift-mcp). Other product families (tenancy, valuate, regrag, portfolio-v2) get their own Projects as the template is replicated.

If you can't find something, search in this order: `gh issue list` → `cat BACKLOG.md` → `git log --oneline` → ask. The pre-session ritual in [CLAUDE.md](CLAUDE.md) hits all four.
