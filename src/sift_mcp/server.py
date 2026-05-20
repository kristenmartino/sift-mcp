"""
Sift MCP server — exposes Sift's civic-literacy news reader to AI clients.

Tools:
  search_articles  — vector search over the pre-built article index
  get_article      — full article + primer + linked entities
  get_dossier      — politician / org / bill / outlet dossier with public-records citations
  search_dossiers  — find a dossier by name
  compare_outlets  — cross-outlet claim comparison over Sift's article index

Stdio transport. Claude Desktop / Claude Code launches this as a subprocess.

Local dev:
  uv run python -m sift_mcp.server

MCP Inspector (recommended for first-time testing):
  uv run mcp dev src/sift_mcp/server.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Literal, Optional

import anthropic
import voyageai
from mcp.server.fastmcp import FastMCP

from sift_mcp.db import get_pool

logger = logging.getLogger("sift-mcp")

mcp = FastMCP("sift")

EntityType = Literal["politician", "org", "bill", "outlet"]


# ─── Embedding helper ────────────────────────────────────────────────
# articles.embedding is VECTOR(512). Match dimensionality with voyage-3-lite
# (matches the model sift-api uses for index population).

_voyage_client: Optional[voyageai.AsyncClient] = None
_anthropic_client: Optional[anthropic.AsyncAnthropic] = None

# Model used for claim extraction in compare_outlets. Haiku is fast and good
# enough for structured-claim extraction over already-summarized articles
# AND for the web_search fan-out fallback.
COMPARE_MODEL = "claude-haiku-4-5-20251001"

# compare_outlets — sparsity + relevance constants. Tuned against the actual
# index distribution: see commit history for the test that produced these.
SCORE_FLOOR = 0.40             # cosine similarity below this isn't really on-topic
SPARSE_TOP_SCORE = 0.42        # if best match is weaker than this, treat as absent
SPARSE_OUTLETS = 3             # < 3 outlets = not enough for a real comparison
SPARSE_ARTICLES = 5            # < 5 articles = too thin to extract claims from

# Web-fallback outlet pool — drawn from sift-api's ALLOWED_SOURCES, roughly
# ordered by web_search hit rate (wires + public broadcast first, since they
# index reliably; subscription outlets and broadcast last).
WEB_OUTLET_POOL = [
    # Wires + public broadcast (highest hit rate)
    "associated press", "reuters", "agence france-presse",
    "bbc", "npr", "al jazeera",
    # National papers
    "the guardian", "the new york times", "the washington post",
    "the wall street journal",
    # Political/policy beat
    "politico", "axios", "the hill",
    # Financial
    "bloomberg", "cnbc", "financial times", "the economist",
    # Broadcast
    "cnn", "fox news", "cbs news", "abc news", "nbc news",
    "pbs newshour",
    # Longform / investigative
    "the atlantic", "national review", "propublica",
]
WEB_OUTLET_BUDGET = 8          # how many outlets to actually search per web call
WEB_TIMEOUT_S = 30             # hard ceiling on the web task — DB never blocked
WEB_MAX_USES = 16              # Claude web_search max_uses — ~2 attempts/outlet


def _select_web_outlets(
    user_outlets: Optional[list[str]],
    db_outlets: list[str],
) -> list[str]:
    """
    Choose which outlets the web fallback should search.

    - If the user passed `outlets` explicitly → use those (their intent wins).
    - Else: take WEB_OUTLET_POOL minus outlets already covered in the DB
      result, take the first WEB_OUTLET_BUDGET. This ensures the web call
      adds *new* outlets rather than re-querying ones the index already has.
    """
    if user_outlets:
        return [o.lower().strip() for o in user_outlets]

    db_lower = {o.lower().strip() for o in db_outlets}

    def _normalized_match(pool_outlet: str) -> bool:
        """True if pool_outlet matches anything already in DB results."""
        # DB source_name uses different spellings ('New York Times' vs 'the new
        # york times'); match by substring overlap on the canonical name.
        for db in db_lower:
            if pool_outlet in db or db in pool_outlet:
                return True
        return False

    fresh = [o for o in WEB_OUTLET_POOL if not _normalized_match(o)]
    return fresh[:WEB_OUTLET_BUDGET]


def _anthropic() -> anthropic.AsyncAnthropic:
    """Lazy Anthropic client; raises if ANTHROPIC_API_KEY is missing."""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set.")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2)
    return _anthropic_client


def _extract_json_object(text: str) -> Optional[dict]:
    """Pull a JSON object out of an LLM response that may have extra wrappers."""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"```json\n?", "", text)
    cleaned = re.sub(r"```\n?", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return None


async def embed_query(text: str) -> list[float]:
    """Embed a search query for vector similarity over the articles table."""
    global _voyage_client
    if _voyage_client is None:
        api_key = os.environ.get("VOYAGE_API_KEY")
        if not api_key:
            raise RuntimeError("VOYAGE_API_KEY not set.")
        _voyage_client = voyageai.AsyncClient(api_key=api_key)
    result = await _voyage_client.embed(
        [text], model="voyage-3-lite", input_type="query"
    )
    return result.embeddings[0]


# ─── Helpers for marshalling pgrows → dicts ──────────────────────────


def _coerce(value: Any) -> Any:
    """Make a single field JSON-friendly (dates → isoformat; JSONB-as-string → parsed)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return json.loads(s)
            except (json.JSONDecodeError, ValueError):
                return value
    return value


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {k: _coerce(v) for k, v in dict(row).items()}


# ─── Tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def search_articles(
    query: str,
    category: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Search Sift's article index by topic.

    Returns articles ranked by semantic relevance to the query. Use this
    first to find what's been happening in a topic area before drilling
    into specific articles or entities.

    Args:
      query: natural-language search (e.g., "energy policy this week").
      category: optional filter — one of top, technology, business, science,
        energy, world, health, politics, sports, entertainment.
      limit: max results, 1–50 (default 10).

    Returns:
      List of {id, title, summary, source, published, category,
      why_it_matters, importance_score, relevance_score}.
    """
    limit = max(1, min(50, limit))
    embedding = await embed_query(query)
    # asyncpg doesn't know how to send a Python list as a pgvector. Convert
    # to the text-literal form that the `::vector` cast in SQL will parse.
    embedding_str = "[" + ",".join(str(float(x)) for x in embedding) + "]"
    pool = await get_pool()

    sql = """
      SELECT
        id, title, summary, source_name, published_date, category,
        why_it_matters, importance_score,
        1 - (embedding <=> $1::vector) AS score
      FROM articles
      WHERE embedding IS NOT NULL
        AND ($2::text IS NULL OR category = $2)
      ORDER BY embedding <=> $1::vector
      LIMIT $3
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, embedding_str, category, limit)

    return [
        {
            "id": r["id"],
            "title": r["title"],
            "summary": r["summary"],
            "source": r["source_name"],
            "published": _coerce(r["published_date"]),
            "category": r["category"],
            "why_it_matters": r["why_it_matters"],
            "importance_score": r["importance_score"],
            "relevance_score": round(float(r["score"]), 3),
        }
        for r in rows
    ]


@mcp.tool()
async def get_article(article_id: str) -> dict[str, Any]:
    """
    Fetch a full article: title, summary, why-it-matters, source link, and the
    linked civic entities (politicians, organizations, bills, outlets) that
    appear in the story.

    Use this after `search_articles` to drill into a specific story. Each
    item in `linked_entities` has an `entity_type` and `slug` you can pass
    to `get_dossier` for the full structured record.

    Args:
      article_id: the article ID from `search_articles`.
    """
    pool = await get_pool()
    sql = """
      SELECT id, title, summary, source_url, source_name, category,
             published_date, why_it_matters, importance_score, entities
      FROM articles
      WHERE id = $1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, article_id)

    if row is None:
        return {"error": f"Article '{article_id}' not found."}

    entities = _coerce(row["entities"]) or []
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"],
        "source_url": row["source_url"],
        "source_name": row["source_name"],
        "category": row["category"],
        "published_date": _coerce(row["published_date"]),
        "why_it_matters": row["why_it_matters"],
        "importance_score": row["importance_score"],
        "linked_entities": entities,
    }


@mcp.tool()
async def get_dossier(entity_type: EntityType, slug: str) -> dict[str, Any]:
    """
    Fetch a structured dossier on a politician, organization, bill, or news outlet.
    Every field is sourced from public records — citations are in `external_links`
    (OpenSecrets, GovTrack, ProPublica Nonprofit Explorer, FARA, FEC, Vote Smart,
    Congress.gov, AllSides, MBFC). Sift surfaces these verbatim and never computes
    its own ratings.

    Slug conventions:
      politician: bioguide_id (e.g., 'S001181' for Schumer)
      org:        canonical slug (e.g., 'brookings-institution')
      bill:       bill_id (e.g., 'hr-5678-119')
      outlet:     canonical slug (e.g., 'reuters')

    Use `search_dossiers` first if you don't know the exact slug.
    """
    pool = await get_pool()

    queries: dict[str, str] = {
        "politician": """
            SELECT bioguide_id AS id, name, party, state, chamber,
                   committees, top_industries_current_cycle, interest_group_ratings,
                   external_links, notes, refreshed_at, updated_at
            FROM politician_profiles
            WHERE bioguide_id = $1
        """,
        "org": """
            SELECT slug AS id, name, type, political_lean, founded_year,
                   annual_budget_usd, major_funders, fara_registered, fara_countries,
                   external_links, notes, updated_at
            FROM org_profiles
            WHERE slug = $1
        """,
        "bill": """
            SELECT bill_id AS id, congress, title, short_title, sponsor_bioguide,
                   cosponsors, status, introduced_date,
                   lobbying_for_usd, lobbying_against_usd,
                   external_links, notes, refreshed_at, updated_at
            FROM bill_profiles
            WHERE bill_id = $1
        """,
        "outlet": """
            SELECT slug AS id, name, parent_company, parent_company_url, founded_year,
                   funding_model, major_funders,
                   allsides_rating, allsides_url, allsides_last_checked,
                   mbfc_factual, mbfc_url, mbfc_last_checked,
                   external_links, notes, updated_at
            FROM outlet_profiles
            WHERE slug = $1
        """,
    }

    sql = queries.get(entity_type)
    if sql is None:
        return {"error": f"Unknown entity_type: {entity_type}"}

    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, slug)

    if row is None:
        return {"error": f"{entity_type} '{slug}' not found."}

    result = _row_to_dict(row)
    result["entity_type"] = entity_type
    return result


@mcp.tool()
async def search_dossiers(
    entity_type: EntityType,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Find a politician, organization, bill, or outlet by name. Use this when an
    article mentions someone or something (e.g., 'Schumer', 'Heritage Foundation',
    'Inflation Reduction Act') and you need the canonical slug for `get_dossier`.

    Args:
      entity_type: 'politician' | 'org' | 'bill' | 'outlet'.
      query: free-text name (case-insensitive).
      limit: max results, 1–50 (default 10).
    """
    limit = max(1, min(50, limit))
    pool = await get_pool()
    pattern = f"%{query.lower()}%"

    queries: dict[str, str] = {
        "politician": """
            SELECT bioguide_id AS id, name, party, state, chamber
            FROM politician_profiles
            WHERE LOWER(name) LIKE $1
            ORDER BY name
            LIMIT $2
        """,
        "org": """
            SELECT slug AS id, name, type, political_lean
            FROM org_profiles
            WHERE LOWER(name) LIKE $1
            ORDER BY name
            LIMIT $2
        """,
        "bill": """
            SELECT bill_id AS id, short_title AS name, title, congress, status
            FROM bill_profiles
            WHERE LOWER(short_title) LIKE $1 OR LOWER(title) LIKE $1
            ORDER BY introduced_date DESC NULLS LAST
            LIMIT $2
        """,
        "outlet": """
            SELECT slug AS id, name, allsides_rating, mbfc_factual
            FROM outlet_profiles
            WHERE LOWER(name) LIKE $1
            ORDER BY name
            LIMIT $2
        """,
    }

    sql = queries.get(entity_type)
    if sql is None:
        return [{"error": f"Unknown entity_type: {entity_type}"}]

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, pattern, limit)

    return [_row_to_dict(r) for r in rows]


# ─── compare_outlets helpers ─────────────────────────────────────────


VALID_AGREEMENTS = {"unanimous", "majority", "disputed", "unique"}


def _clean_claim(raw: Any, source: str, default_outlets: Optional[list[str]] = None) -> Optional[dict]:
    """Validate + normalize a single claim dict from LLM output."""
    if not isinstance(raw, dict) or "claim" not in raw:
        return None
    agreement = raw.get("agreement", "unique")
    if agreement not in VALID_AGREEMENTS:
        agreement = "unique"
    claim: dict = {
        "claim": str(raw["claim"]),
        "agreement": agreement,
        "outlets": [str(s) for s in raw.get("outlets", default_outlets or [])],
        "article_ids": [str(a) for a in raw.get("article_ids", [])],
        "source": source,  # "index" | "web"
    }
    if agreement == "disputed":
        claim["outlets_against"] = [str(s) for s in raw.get("outlets_against", [])]
    return claim


async def _vector_search_articles(topic: str, limit: int) -> list[dict[str, Any]]:
    """Vector search Sift's article index, return rows ≥ SCORE_FLOOR similarity."""
    embedding = await embed_query(topic)
    embedding_str = "[" + ",".join(str(float(x)) for x in embedding) + "]"
    pool = await get_pool()
    sql = """
      SELECT id, title, summary, source_name, source_url, published_date,
             why_it_matters, category,
             1 - (embedding <=> $1::vector) AS score
      FROM articles
      WHERE embedding IS NOT NULL
      ORDER BY embedding <=> $1::vector
      LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, embedding_str, limit)
    # Apply relevance floor — anything below this isn't really on-topic and
    # would just confuse the claim-extraction model.
    return [dict(r) for r in rows if float(r["score"]) >= SCORE_FLOOR]


def _is_sparse(top_score: float, outlet_count: int, article_count: int) -> bool:
    """Hybrid sparsity heuristic — see SPARSE_* constants for thresholds."""
    return (
        top_score < SPARSE_TOP_SCORE
        or outlet_count < SPARSE_OUTLETS
        or article_count < SPARSE_ARTICLES
    )


async def _extract_db_claims(topic: str, by_outlet: dict[str, list[dict]]) -> dict[str, Any]:
    """Run Haiku claim-extraction over articles already grouped by outlet."""
    outlets_block = ""
    for outlet, articles in by_outlet.items():
        outlets_block += f"\n--- {outlet.upper()} ---\n"
        for a in articles:
            outlets_block += f"[article_id: {a['id']}]\n"
            outlets_block += f"Title: {a['title']}\n"
            outlets_block += f"Summary: {a['summary']}\n"
            if a.get("why_it_matters"):
                outlets_block += f"Why it matters: {a['why_it_matters']}\n"
            outlets_block += "\n"

    outlet_names_list = json.dumps(list(by_outlet.keys()))

    prompt = f"""Compare how these outlets covered "{topic}".

{outlets_block}

Your task:
1. Extract 3-8 specific factual claims that appear across the coverage.
2. For each claim, determine the agreement level:
   - "unanimous": all outlets that cover this point agree
   - "majority": most outlets agree, some don't cover it
   - "disputed": outlets contradict each other on this point
   - "unique": only one outlet reports this
3. For each claim, list the outlets that back it AND the article_ids that
   support it (so a reader can drill into the source).
4. Write a 2-3 sentence narrative summary describing how coverage differs
   or aligns across outlets.

Return ONLY a JSON object with this structure:
{{
  "comparison": "2-3 sentence summary of how the outlets compare...",
  "claims": [
    {{"claim": "...", "agreement": "unanimous", "outlets": [...], "article_ids": [...]}},
    {{"claim": "...", "agreement": "disputed", "outlets": [...], "outlets_against": [...], "article_ids": [...]}}
  ]
}}

Available outlets: {outlet_names_list}
Return ONLY the JSON, no other text."""

    response = await _anthropic().messages.create(
        model=COMPARE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    parsed = _extract_json_object(text)
    if not parsed:
        return {"comparison": "", "claims": [], "_parse_error": text[:300]}

    claims = [
        c for c in (_clean_claim(raw, source="index") for raw in parsed.get("claims", []))
        if c
    ]
    return {
        "comparison": parsed.get("comparison", "").strip(),
        "claims": claims,
    }


async def _extract_web_claims(topic: str, outlets_to_search: list[str]) -> dict[str, Any]:
    """
    Single Claude+web_search call: fan out across the given outlets, extract
    claims directly. One round-trip (vs the two-step pattern in sift-api).
    """
    # Map outlet names to site: filters where we know the domain. Falls back
    # to outlet name in the search if no mapping. Higher hit rate than open
    # queries.
    domains = {
        "associated press": "apnews.com",
        "reuters": "reuters.com",
        "agence france-presse": "afp.com",
        "bbc": "bbc.com",
        "npr": "npr.org",
        "al jazeera": "aljazeera.com",
        "the guardian": "theguardian.com",
        "the new york times": "nytimes.com",
        "the washington post": "washingtonpost.com",
        "the wall street journal": "wsj.com",
        "politico": "politico.com",
        "axios": "axios.com",
        "the hill": "thehill.com",
        "bloomberg": "bloomberg.com",
        "cnbc": "cnbc.com",
        "financial times": "ft.com",
        "the economist": "economist.com",
        "cnn": "cnn.com",
        "fox news": "foxnews.com",
        "cbs news": "cbsnews.com",
        "abc news": "abcnews.go.com",
        "nbc news": "nbcnews.com",
        "pbs newshour": "pbs.org",
        "the atlantic": "theatlantic.com",
        "national review": "nationalreview.com",
        "propublica": "propublica.org",
    }

    search_targets = []
    for outlet in outlets_to_search:
        domain = domains.get(outlet.lower().strip())
        if domain:
            search_targets.append(f'- {outlet}: search query `site:{domain} {topic}`')
        else:
            search_targets.append(f'- {outlet}: search query `"{outlet}" {topic}`')
    targets_block = "\n".join(search_targets)

    prompt = f"""Find recent news coverage of "{topic}" from these specific outlets:

{targets_block}

Use the web_search tool. Run ONE search per outlet using the exact query format shown above (the `site:` operator pins results to the outlet's domain — much higher hit rate than open queries). If a search returns no relevant results, move on; don't burn extra searches on outlets that aren't covering this topic.

After searching, extract 3-6 specific factual claims that appear across the coverage you found. For each claim:
- "agreement": "unanimous" (all outlets you found agree) | "majority" (most agree) | "disputed" (outlets contradict) | "unique" (only one reports)
- "outlets": list of outlet names that back the claim
- For "disputed": also include "outlets_against"

Also write a 2-3 sentence summary of how coverage differs or aligns.

Return ONLY a JSON object:
{{
  "comparison": "...",
  "outlets_found": ["outlet that actually returned coverage", ...],
  "claims": [
    {{"claim": "...", "agreement": "unanimous", "outlets": [...]}},
    {{"claim": "...", "agreement": "disputed", "outlets": [...], "outlets_against": [...]}}
  ]
}}

Available outlets: {json.dumps(outlets_to_search)}
Return ONLY the JSON, no other text or markdown."""

    response = await _anthropic().messages.create(
        model=COMPARE_MODEL,
        max_tokens=4096,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": WEB_MAX_USES,
        }],
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    parsed = _extract_json_object(text)
    if not parsed:
        return {
            "comparison": "",
            "outlets_found": [],
            "claims": [],
            "_parse_error": text[:300],
        }

    claims = [
        c for c in (_clean_claim(raw, source="web") for raw in parsed.get("claims", []))
        if c
    ]
    return {
        "comparison": parsed.get("comparison", "").strip(),
        "outlets_found": [str(o) for o in parsed.get("outlets_found", [])],
        "claims": claims,
    }


# ─── compare_outlets — the tool ──────────────────────────────────────


@mcp.tool()
async def compare_outlets(
    topic: str,
    outlets: Optional[list[str]] = None,
    article_limit: int = 20,
    web_fallback: Literal["auto", "always", "never"] = "auto",
) -> dict[str, Any]:
    """
    Compare how outlets covered a topic. Reads Sift's pre-built article index
    first (sub-second), runs Claude Haiku for claim extraction, and optionally
    falls back to a live Claude `web_search` fan-out when the index doesn't
    have enough coverage on the topic.

    Two paths, one tool:
      - **Index path** (always): vector-search Sift's articles for the topic,
        group matching articles by outlet, extract claims with agreement labels
        and `article_id` citations. ~5-9s.
      - **Web path** (conditional): Claude with the `web_search_20250305` tool,
        fans out across mainstream outlets to find fresh coverage, extracts
        claims in the same shape. ~15-25s, capped at 25s upstream.

    Args:
      topic: free-text topic, 3–500 chars. Be specific — broad topics produce
        mushy comparisons. Examples: "redistricting south carolina",
        "FERC Order 1920", "geothermal energy permitting".
      outlets: optional outlet filter for the INDEX path (case-insensitive
        substring match against `source_name`). If passed, also used as the
        sources list for the web path. Omit to compare across every outlet
        that has coverage.
      article_limit: how many top-ranked articles to pull from the index
        before grouping. 5–50 (default 20).
      web_fallback: "auto" (default) | "always" | "never".
        - "auto": only fire web if index coverage is sparse (top similarity
          score < 0.42, OR fewer than 3 outlets, OR fewer than 5 articles).
        - "always": run web alongside index every time (paired LLM cost).
        - "never": index-only, even if sparse.

    Returns:
      {
        topic: str,
        comparison: str,                         # narrative from the index path
        web_comparison: str | null,              # narrative from the web path, if it ran
        outlets_covered: list[str],              # outlets from the index
        web_outlets_found: list[str],            # outlets that web returned coverage from
        articles_compared: int,                  # index articles in the comparison
        web_status: "skipped" | "included" | "timed_out" | "errored" | "no_coverage",
        claims: list[{
          claim: str,
          agreement: "unanimous" | "majority" | "disputed" | "unique",
          outlets: list[str],
          outlets_against?: list[str],
          article_ids: list[str],                # populated for source="index"
          source: "index" | "web",               # which path produced this claim
        }],
      }

    On hard error returns {"error": "<message>"}.
    """
    topic = topic.strip()
    if len(topic) < 3:
        return {"error": "Topic must be at least 3 characters."}
    if web_fallback not in {"auto", "always", "never"}:
        return {"error": f"web_fallback must be 'auto', 'always', or 'never' (got {web_fallback!r})."}
    article_limit = max(5, min(50, article_limit))

    # ── 1. Index search ──────────────────────────────────────────────
    rows = await _vector_search_articles(topic, article_limit)

    # Apply outlet filter
    if outlets:
        needles = [o.lower().strip() for o in outlets]
        rows = [
            r for r in rows
            if any(n in (r["source_name"] or "").lower() for n in needles)
        ]

    # ── 2. Group by outlet ───────────────────────────────────────────
    by_outlet: dict[str, list[dict]] = {}
    for r in rows:
        outlet = r["source_name"] or "unknown"
        by_outlet.setdefault(outlet, []).append(
            {
                "id": r["id"],
                "title": r["title"],
                "summary": r["summary"],
                "why_it_matters": r["why_it_matters"],
            }
        )

    top_score = max((float(r["score"]) for r in rows), default=0.0)
    article_count = len(rows)
    outlet_count = len(by_outlet)
    is_sparse = _is_sparse(top_score, outlet_count, article_count)

    # ── 3. Decide whether to fire web ────────────────────────────────
    fire_web = (
        web_fallback == "always"
        or (web_fallback == "auto" and is_sparse)
    )

    # If web won't fire AND index is completely empty, bail with a useful error.
    if not fire_web and article_count == 0:
        return {
            "error": (
                f"No articles in Sift's index match '{topic}' (top similarity "
                f"{top_score:.2f} below {SCORE_FLOOR}). Try web_fallback='always' "
                f"to search fresh coverage, or 'auto' (default) which would have "
                f"fired the fallback."
            ),
        }

    # ── 4. Parallel: index claim extraction + (optional) web search ──
    db_task: Optional[asyncio.Task] = None
    if by_outlet:
        db_task = asyncio.create_task(_extract_db_claims(topic, by_outlet))

    web_task: Optional[asyncio.Task] = None
    selected_web_outlets: list[str] = []
    if fire_web:
        selected_web_outlets = _select_web_outlets(
            user_outlets=outlets,
            db_outlets=list(by_outlet.keys()),
        )
        if selected_web_outlets:
            web_task = asyncio.create_task(
                _extract_web_claims(topic, selected_web_outlets)
            )

    db_result: dict = {"comparison": "", "claims": []}
    if db_task is not None:
        try:
            db_result = await db_task
        except Exception as exc:
            logger.exception("DB claim extraction failed: %s", exc)
            db_result = {"comparison": "", "claims": [], "_error": str(exc)}

    web_result: Optional[dict] = None
    web_status = "skipped"
    if web_task is not None:
        try:
            web_result = await asyncio.wait_for(web_task, timeout=WEB_TIMEOUT_S)
            web_status = (
                "included"
                if (web_result and web_result.get("claims"))
                else "no_coverage"
            )
        except asyncio.TimeoutError:
            web_status = "timed_out"
            web_task.cancel()
        except Exception as exc:
            logger.exception("Web claim extraction failed: %s", exc)
            web_status = f"errored: {exc}"

    # ── 5. Merge ─────────────────────────────────────────────────────
    all_claims: list[dict] = list(db_result.get("claims", []))
    if web_result and web_result.get("claims"):
        all_claims.extend(web_result["claims"])

    return {
        "topic": topic,
        "comparison": db_result.get("comparison", ""),
        "web_comparison": (web_result.get("comparison") if web_result else None),
        "outlets_covered": list(by_outlet.keys()),
        "web_outlets_searched": selected_web_outlets,
        "web_outlets_found": (web_result.get("outlets_found", []) if web_result else []),
        "articles_compared": article_count,
        "top_relevance_score": round(top_score, 3),
        "web_status": web_status,
        "claims": all_claims,
    }


# ─── Entry point ─────────────────────────────────────────────────────


def main() -> None:
    """Stdio transport. Claude Desktop / Claude Code launches this as a subprocess."""
    mcp.run()


if __name__ == "__main__":
    main()
