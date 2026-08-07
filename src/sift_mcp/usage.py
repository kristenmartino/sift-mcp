"""Cost telemetry for sift-mcp's paid calls.

WHY THIS EXISTS
---------------
sift-mcp had no usage logging, no ledger write and no budget check of any
kind. Its spend was not merely uncapped — it was invisible. `compare_outlets`
can fire two 4096-token Haiku completions plus up to `WEB_MAX_USES = 16`
server-side web searches at $0.010 each, so roughly **$0.16 of tool fees in a
single call**, and nothing anywhere recorded that it happened. The equivalent
path in the Next.js frontend caps at 2 searches and writes to the ledger.

That is the same shape as the failure that made this whole exercise
necessary: `sift-api`'s `ai_usage_daily` sat empty for months because
recording was gated behind a flag nobody had set, and `STATUS.md` carried a
cost figure ~20x below reality until someone read the Anthropic bill. A
number nobody can query is a number nobody checks.

sift-mcp shares the same Neon database as sift-api and the frontend, so its
spend belongs in the same `ai_usage_daily` table. Once it is there,
`sift-api/scripts/verify_cost_baseline.py` picks it up with no changes.

Recording is unconditional. Enforcement — `within_budget` — is the part that
can be switched off, mirroring the split sift-api settled on: the flag that
turns on *blocking* must never be the flag that turns on *measuring*.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from sift_mcp.db import get_pool

logger = logging.getLogger("sift-mcp.usage")

# Claude Haiku 4.5, USD per 1M tokens. Kept in step with
# sift-api/services/usage_tracker.py and sift/lib/usage-tracker.ts, which
# carry the same table; see the parity test there.
PRICE_INPUT_PER_M = 1.0
PRICE_OUTPUT_PER_M = 5.0
PRICE_CACHE_WRITE_5M_PER_M = 1.25
PRICE_CACHE_READ_PER_M = 0.10

# Server-side web_search: $10 per 1,000 searches.
PRICE_WEB_SEARCH_PER_CALL = 0.010

DAILY_AI_COST_LIMIT_USD = float(os.getenv("DAILY_AI_COST_LIMIT_USD", "10"))
COST_GUARD_ENABLED = os.getenv("AI_COST_GUARD_ENABLED", "false").lower() == "true"


def count_web_searches(response: Any) -> int:
    """Count billable server_tool_use blocks in a response.

    These are the expensive part — at WEB_MAX_USES=16 the search fees dwarf
    the token cost — and they are invisible in `usage`, so they have to be
    counted off the content blocks.
    """
    try:
        return sum(
            1
            for block in (getattr(response, "content", None) or [])
            if getattr(block, "type", None) == "server_tool_use"
            and getattr(block, "name", "") == "web_search"
        )
    except Exception:  # noqa: BLE001 — telemetry must not break a tool call
        return 0


def estimate_cost(response: Any, web_searches: int = 0) -> float:
    usage = getattr(response, "usage", None)

    def tok(name: str) -> int:
        return int(getattr(usage, name, 0) or 0) if usage else 0

    return (
        tok("input_tokens") * PRICE_INPUT_PER_M / 1_000_000
        + tok("output_tokens") * PRICE_OUTPUT_PER_M / 1_000_000
        + tok("cache_creation_input_tokens") * PRICE_CACHE_WRITE_5M_PER_M / 1_000_000
        + tok("cache_read_input_tokens") * PRICE_CACHE_READ_PER_M / 1_000_000
        + web_searches * PRICE_WEB_SEARCH_PER_CALL
    )


async def record(operation: str, response: Any, model: str) -> float:
    """Log a paid call and add it to the shared daily ledger.

    Unconditional: the cost-guard flag governs enforcement, not measurement.
    Never raises — a lost telemetry row must not fail a tool call, and the
    figure is logged before the write is attempted so it survives a DB blip.
    """
    searches = count_web_searches(response)
    cost = estimate_cost(response, searches)
    logger.info(
        "api_usage operation=%s model=%s web_searches=%d cost_usd=%.6f",
        operation, model, searches, cost,
    )
    if cost <= 0:
        return cost
    try:
        pool = await get_pool()
        await pool.execute(
            """
            INSERT INTO ai_usage_daily
                (usage_date, provider, model, operation, estimated_cost_usd,
                 call_count, updated_at)
            VALUES (CURRENT_DATE, 'anthropic', $1, $2, $3, 1, NOW())
            ON CONFLICT (usage_date, provider, model, operation) DO UPDATE SET
                estimated_cost_usd =
                    ai_usage_daily.estimated_cost_usd + EXCLUDED.estimated_cost_usd,
                call_count = ai_usage_daily.call_count + 1,
                updated_at = NOW()
            """,
            model, operation, cost,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("ai_usage_daily insert failed for %s: %s", operation, e)
    return cost


async def within_budget() -> bool:
    """May a paid call proceed under today's ceiling?

    True when the guard is off. Otherwise reads the shared ledger and
    **fails closed** on a read error, matching
    `sift-api/services/cost_guard.check_budget` and the frontend's topic
    route: an enabled ceiling that fails open would permit unlimited spend
    during exactly the failure mode where spend cannot be measured.

    Callers degrade rather than error — compare_outlets already has a
    DB-only mode, so a false here costs breadth, not the answer.
    """
    if not COST_GUARD_ENABLED:
        return True
    try:
        pool = await get_pool()
        spent = await pool.fetchval(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) "
            "FROM ai_usage_daily WHERE usage_date = CURRENT_DATE"
        )
        if float(spent or 0) >= DAILY_AI_COST_LIMIT_USD:
            logger.warning(
                "web fallback skipped: today's AI spend $%.2f >= limit $%.2f",
                float(spent or 0), DAILY_AI_COST_LIMIT_USD,
            )
            return False
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("AI budget unreadable; skipping paid path (fail-closed): %s", e)
        return False
