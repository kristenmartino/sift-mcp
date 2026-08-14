"""
asyncpg connection pool against the shared Neon Postgres.

Same DATABASE_URL as sift-api and the Next.js frontend — sift-mcp is a
read-only surface over the data the production product already serves.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    """Lazy-initialize the pool. Safe to call concurrently from any tool handler."""
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                raise RuntimeError(
                    "DATABASE_URL not set. Copy .env.example to .env and fill it in."
                )
            # Neon requires SSL; the URL should already include ?sslmode=require.
            #
            # min_size=0 and a short inactive lifetime so an MCP server left
            # running does not hold a connection against a Neon compute that is
            # trying to scale to zero. asyncpg's min_size is only the count
            # opened at init — no maintenance task refills the pool — so this
            # costs nothing but the first connect after an idle gap, and that
            # gap is the norm here: this server is queried by a human at a
            # keyboard, not on a schedule.
            #
            # Do NOT set the lifetime to 0; asyncpg reads a falsy value as
            # "never expire idle connections", which is the opposite.
            _pool = await asyncpg.create_pool(
                db_url,
                min_size=0,
                max_size=5,
                command_timeout=30,
                max_inactive_connection_lifetime=60.0,
            )
    return _pool


async def close_pool() -> None:
    """Close the pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
