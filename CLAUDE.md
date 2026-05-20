# CLAUDE.md — orientation for Claude Code (and future-me)

Context to load before editing anything in `sift-mcp`. Keep this file **short**; if a section grows past one screen, split into a real doc.

## Pre-session ritual

Run these first, in order. Skip none.

```bash
cat STATUS.md            # active focus, open question, next 3, recent decisions
gh pr list               # what's open, what's mid-flight
gh issue list            # what's committed but not started
cat BACKLOG.md           # deferred work + bugs/quirks to revisit
```

The 30 seconds this takes saves hours of "wait, I thought we already decided…" later in the session.

## End-of-PR doc-impact check

Before opening a PR, ask three questions:

1. **Did this change shift the active focus, the next 3, or the open strategic question?** → update `STATUS.md` in the PR.
2. **Did this add a deferred item, a v0.5+ idea, or surface a quirk worth tracking?** → update `BACKLOG.md` in the PR.
3. **Did this change the public tool surface (new tool, removed tool, changed args/return shape) or setup steps?** → update `README.md` in the PR.

Don't open PRs that change behavior without touching the doc that explains the behavior. Future-you will thank you.

## Production stance

**Pending.** Currently portfolio-grade — narrative clarity over operational rigor. Revisit when one of the v0.5 triggers in STATUS.md fires (Harish hands the URL to anyone, non-Kristen user signs up, $20/mo Anthropic spend, mobile app project starts).

## Where to file new work (decision tree)

When you discover something during a session that's worth tracking, use this to decide where it goes. The goal: **never lose anything, but don't over-file** either.

| What you found | Where it goes |
|---|---|
| **Bug that's blocking current work** | Fix it in the active branch. Don't file. |
| **Concrete feature you're committing to in the next ~2 weeks** | GitHub issue with `tier-v0.5` / `tier-v1.0` + `effort-*` labels. Add to STATUS.md "Next 3" if it bumps something. |
| **Concrete feature you want eventually, no commitment** | BACKLOG.md under "Stretch / nice-to-have." Promote to issue later when you commit. |
| **Quirk or minor bug that's not urgent** | BACKLOG.md under "Bugs / quirks to revisit." |
| **Critical bug found but not fixed in this session** | GitHub issue with `bug` label *and* note in BACKLOG.md. Mention in STATUS.md "Blocked-on" if it blocks Next 3. |
| **Strategic question or open architectural decision** | STATUS.md "Open strategic questions" — never a GitHub issue. Questions get answered through usage/conversation, not engineering work. |
| **Architectural decision you've now made** | STATUS.md "Recent decisions." Trim the oldest one if the section grows past ~6 entries. |
| **Out-of-scope idea that surfaced during work** | If it's tied to a specific file, use the spawned-task chip in your editor. Otherwise BACKLOG.md "Stretch." |

**The rule:** if it has a date or a committed scope, file an issue. If it's a half-formed thought, BACKLOG.md is fine — issues you'll never close are noise.

## Where things live

See the "Where things live" section in STATUS.md. Don't duplicate it here.

## Things I've tripped on

- **`load_dotenv(override=True)` makes `.env` always win over shell.** If a key in `.env` is empty / wrong, the shell value won't save you. Verify `.env` is what you think it is when env-related debugging starts.
- **MCP Inspector's 10s default request timeout** kills `compare_outlets`. Use `./scripts/inspect.sh` which sets `MCP_SERVER_REQUEST_TIMEOUT=120000`.
- **`compare_outlets` with `articles_compared == 1`** tends to substitute the topic in Haiku's claim extraction (e.g. asked about "FERC Order 1920," got claims about "Order 1000" because the one matching article was about Order 1000). See BACKLOG for the fix-it-later note. For demos, pick topics where you've confirmed `articles_compared >= 5`.
