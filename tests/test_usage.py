"""Tests for sift_mcp.usage.

sift-mcp had no usage logging, no ledger write and no budget check at all —
its spend was invisible, not merely uncapped. compare_outlets can fire two
4096-token completions plus up to WEB_MAX_USES=16 billable searches, roughly
$0.16 in one call, and nothing recorded it.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from sift_mcp import usage

ONE_M = 1_000_000


def _response(*, input_tokens=0, output_tokens=0, searches=0):
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        content=[
            SimpleNamespace(type="server_tool_use", name="web_search")
            for _ in range(searches)
        ],
    )


class TestWebSearchCounting:
    def test_counts_billable_search_blocks(self):
        assert usage.count_web_searches(_response(searches=16)) == 16

    def test_web_searches_dominate_the_cost_at_the_current_cap(self):
        """WEB_MAX_USES=16 at $0.010 is $0.16 — far more than the tokens, and
        invisible in `usage`, which is why they are counted off content."""
        cost = usage.estimate_cost(
            _response(input_tokens=4000, output_tokens=4000, searches=16), 16
        )
        tokens_only = usage.estimate_cost(
            _response(input_tokens=4000, output_tokens=4000), 0
        )
        assert round(cost - tokens_only, 4) == 0.16
        assert cost > tokens_only * 5

    def test_malformed_response_counts_zero_rather_than_raising(self):
        assert usage.count_web_searches(object()) == 0


class TestRecord:
    @pytest.mark.asyncio
    async def test_records_unconditionally_even_with_the_guard_off(self):
        """The flag that turns on blocking must never be the flag that turns
        on measuring — that is exactly how sift-api's ledger sat empty for
        months while STATUS.md quoted a figure ~20x below reality."""
        pool = AsyncMock()
        with patch.object(usage, "COST_GUARD_ENABLED", False), \
                patch.object(usage, "get_pool", AsyncMock(return_value=pool)):
            cost = await usage.record("compare.x", _response(input_tokens=ONE_M), "m")
        assert cost == 1.0
        pool.execute.assert_awaited_once()
        assert "ai_usage_daily" in pool.execute.call_args.args[0]

    @pytest.mark.asyncio
    async def test_a_write_failure_never_breaks_the_tool_call(self):
        pool = AsyncMock()
        pool.execute = AsyncMock(side_effect=RuntimeError("db down"))
        with patch.object(usage, "get_pool", AsyncMock(return_value=pool)):
            cost = await usage.record("compare.x", _response(input_tokens=ONE_M), "m")
        # Reached the write and swallowed a real failure, rather than
        # short-circuiting before it.
        pool.execute.assert_awaited_once()
        assert cost == 1.0


class TestWithinBudget:
    @pytest.mark.asyncio
    async def test_allows_everything_when_the_guard_is_off(self):
        with patch.object(usage, "COST_GUARD_ENABLED", False):
            assert await usage.within_budget() is True

    @pytest.mark.asyncio
    async def test_blocks_when_over_the_ceiling(self):
        pool = AsyncMock()
        pool.fetchval = AsyncMock(return_value=99.0)
        with patch.object(usage, "COST_GUARD_ENABLED", True), \
                patch.object(usage, "DAILY_AI_COST_LIMIT_USD", 10.0), \
                patch.object(usage, "get_pool", AsyncMock(return_value=pool)):
            assert await usage.within_budget() is False

    @pytest.mark.asyncio
    async def test_fails_closed_when_the_ledger_cannot_be_read(self):
        """An enabled ceiling that fails open permits unlimited spend during
        exactly the failure mode where spend cannot be measured. Matches
        sift-api's cost_guard.check_budget and the frontend's topic route."""
        pool = AsyncMock()
        pool.fetchval = AsyncMock(side_effect=RuntimeError("unreadable"))
        with patch.object(usage, "COST_GUARD_ENABLED", True), \
                patch.object(usage, "get_pool", AsyncMock(return_value=pool)):
            assert await usage.within_budget() is False
