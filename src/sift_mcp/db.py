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
            _pool = await asyncpg.create_pool(
                db_url,
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
    return _pool


async def close_pool() -> None:
    """Close the pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
