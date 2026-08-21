# CLAUDE.md — orientation for Claude Code (and future-me)

Context to load before editing anything in `sift-mcp`. Keep this file **short**; if a section grows past one screen, split into a real doc.

## Pre-session ritual

Run these first, in order. Skip none.

```bash
head -c 4000 STATUS.md   # active focus, open questions, recent decisions — no current state beyond this
gh issue list             # the engineering queue — Next 3 lives here, not in STATUS.md
gh pr list                 # what's open, what's mid-flight
cat BACKLOG.md            # deferred work + bugs/quirks to revisit
```

STATUS.md holds no current state of its own past `Active focus` and `Open strategic questions` — reading the
head is enough; you don't need the full file (or its archive) for a normal session. The engineering queue and
what's blocked both live in GitHub now (`gh issue list`), not in hand-maintained STATUS.md sections.

The 30 seconds this takes saves hours of "wait, I thought we already decided…" later in the session.

## End-of-PR doc-impact check

Before opening a PR, ask three questions:

1. **Did this change shift the active focus or the open strategic question?** → update `STATUS.md` in the PR. (The engineering queue itself — what was "Next 3" — lives in GitHub issues; close/open/reprioritize there instead.)
2. **Did this add a deferred item, a v0.5+ idea, or surface a quirk worth tracking?** → update `BACKLOG.md` in the PR.
3. **Did this change the public tool surface (new tool, removed tool, changed args/return shape) or setup steps?** → update `README.md` in the PR.

Don't open PRs that change behavior without touching the doc that explains the behavior. Future-you will thank you.

## Production stance

**Pending.** Currently portfolio-grade — narrative clarity over operational rigor. Revisit when one of the v0.5 triggers in STATUS.md fires (an outside stakeholder needs a shareable URL, a non-Kristen user signs up, $20/mo Anthropic spend, or an external agent / framework integration request). The mobile-app trigger is void — Android v1 is REST-only per `sift-api/docs/MOBILE_PROTOCOL_DECISION.md`.

## Where to file new work (decision tree)

When you discover something during a session that's worth tracking, use this to decide where it goes. The goal: **never lose anything, but don't over-file** either.

| What you found | Where it goes |
|---|---|
| **Bug that's blocking current work** | Fix it in the active branch. Don't file. |
| **Concrete feature you're committing to in the next ~2 weeks** | GitHub issue with `tier-v0.5` / `tier-v1.0` + `effort-*` labels. That issue *is* the "Next 3" now — no separate STATUS.md list to update. |
| **Concrete feature you want eventually, no commitment** | BACKLOG.md under "Stretch / nice-to-have." Promote to issue later when you commit. |
| **Quirk or minor bug that's not urgent** | BACKLOG.md under "Bugs / quirks to revisit." |
| **Critical bug found but not fixed in this session** | GitHub issue with `bug` label *and* note in BACKLOG.md. (No `blocked` label exists in this repo yet — add one, and the note, once it does. Until then a plain `gh issue list --state open` is the blocked-work view.) |
| **Strategic question or open architectural decision** | STATUS.md "Open strategic questions" — never a GitHub issue. Questions get answered through usage/conversation, not engineering work. |
| **Architectural decision you've now made** | STATUS.md "Recent decisions (last 7 days)." See "Recent decisions window + archive" below — this replaces the old count-based trim rule. |
| **Out-of-scope idea that surfaced during work** | If it's tied to a specific file, use the spawned-task chip in your editor. Otherwise BACKLOG.md "Stretch." |

**The rule:** if it has a date or a committed scope, file an issue. If it's a half-formed thought, BACKLOG.md is fine — issues you'll never close are noise.

## Recent decisions window + archive

**This supersedes the prior rule** ("trim the oldest entry once the section grows past ~6 entries"). STATUS.md's
"Recent decisions" section is now date-windowed instead of count-windowed: it holds only entries from the last 7
days. When you add a new decision, also check the oldest entries already there — anything dated before the
7-day cutoff moves to [`docs/STATUS_ARCHIVE.md`](docs/STATUS_ARCHIVE.md), newest-first, verbatim, and is never
edited again once archived. If "Recent decisions" is empty because nothing landed in the window, say so explicitly
("Nothing in the last 7 days.") rather than leaving the section blank — a section with no content and no
explanation reads as broken, not as good news.

This is the same convention now applied across `sift`, `sift-api`, and this repo, for consistency — not because
count-based trimming had visibly failed here yet (it hadn't; this repo's STATUS.md is small). Applying it
uniformly means one mental model across all four repos instead of a different pruning rule per repo.

## Where things live

See the "Where things live" section in STATUS.md. Don't duplicate it here.

## Things I've tripped on

- **`load_dotenv(override=True)` makes `.env` always win over shell.** If a key in `.env` is empty / wrong, the shell value won't save you. Verify `.env` is what you think it is when env-related debugging starts.
- **MCP Inspector's 10s default request timeout** kills `compare_outlets`. Use `./scripts/inspect.sh` which sets `MCP_SERVER_REQUEST_TIMEOUT=120000`.
- **`compare_outlets` with `articles_compared == 1`** tends to substitute the topic in Haiku's claim extraction (e.g. asked about "FERC Order 1920," got claims about "Order 1000" because the one matching article was about Order 1000). See BACKLOG for the fix-it-later note. For demos, pick topics where you've confirmed `articles_compared >= 5`.
