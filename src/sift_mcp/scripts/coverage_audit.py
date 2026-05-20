"""
Coverage audit — measures dossier coverage against the entities Sift
actually extracts from articles.

Two columns matter (see sift-api/migrations/008_article_entity_links.sql):
  articles.entities      — raw mentions extracted from title + summary
                           (every named entity the extractor caught)
  articles.entity_links  — subset the linker matched to a dossier
                           shape: [{"type", "canonical_id", "surface_form"}]

The coverage question is: of all raw mentions, what fraction made it
into entity_links? And where they didn't, what specific names are missing?

Run:
  cd sift-mcp
  uv run python -m sift_mcp.scripts.coverage_audit
"""

from __future__ import annotations

import asyncio
import json
from textwrap import shorten
from typing import Any

from sift_mcp.db import close_pool, get_pool

# ─── Configurable: which JSON key holds the surface form in each column ──
# Section 0 prints sample shapes — adjust these if your extractor uses
# different field names (e.g. RAW_NAME_FIELD="text" instead of "name").
RAW_NAME_FIELD = "name"
RAW_TYPE_FIELD = "type"
LINKED_SURFACE_FIELD = "surface_form"  # documented in migration 008
LINKED_TYPE_FIELD = "type"


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def table(rows: list[Any], cols: list[str]) -> None:
    if not rows:
        print("(no rows)")
        return
    widths = []
    for c in cols:
        w = max(len(c), max(len(str(r[c])) for r in rows))
        widths.append(min(w, 60))
    print(" | ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(
            " | ".join(
                shorten(str(r[c]) if r[c] is not None else "—", w, placeholder="…").ljust(w)
                for c, w in zip(cols, widths)
            )
        )


async def section_0_samples(conn) -> None:
    section("0. Sample shapes — verify field-name constants in this script")
    # First: surface the column-level types so we know if entities is an array or object.
    typecheck = await conn.fetchrow(
        """
      SELECT
        jsonb_typeof(entities) AS entities_type,
        jsonb_typeof(entity_links) AS entity_links_type,
        COUNT(*) OVER () AS sample_size
      FROM articles
      WHERE entities IS NOT NULL OR entity_links IS NOT NULL
      LIMIT 1
    """
    )
    if typecheck:
        print(f"  articles.entities      JSONB typeof → {typecheck['entities_type']!r}")
        print(f"  articles.entity_links  JSONB typeof → {typecheck['entity_links_type']!r}")
        print()

    rows = await conn.fetch(
        """
      SELECT id, entities, entity_links FROM articles
      WHERE entities IS NOT NULL OR entity_links IS NOT NULL
      LIMIT 3
    """
    )
    if not rows:
        print("(no articles with entities or entity_links)")
        return
    for r in rows:
        ents = r["entities"]
        links = r["entity_links"]
        if isinstance(ents, str):
            try:
                ents = json.loads(ents)
            except json.JSONDecodeError:
                pass
        if isinstance(links, str):
            try:
                links = json.loads(links)
            except json.JSONDecodeError:
                pass
        print(f"\nArticle {r['id']!r}:")
        print(f"  entities      (type={type(ents).__name__})  = "
              f"{json.dumps(ents)[:300] if ents is not None else 'None'}")
        print(f"  entity_links  (type={type(links).__name__})  = "
              f"{json.dumps(links)[:300] if links is not None else 'None'}")


async def section_1_totals(conn) -> None:
    section("1. Aggregate coverage stats")
    # entities is a JSONB object with type-keyed arrays of strings:
    #   {"people": [...], "organizations": [...], "locations": [...], "event_description": "..."}
    # entity_links is a JSONB array of {type, canonical_id, surface_form} objects.
    # "raw mentions" = people + organizations (locations don't currently map to dossiers).
    row = await conn.fetchrow(
        """
      SELECT
        COUNT(*) AS total_articles,
        COUNT(*) FILTER (WHERE entities IS NOT NULL AND entities != '{}'::jsonb) AS articles_with_entities,
        COUNT(*) FILTER (WHERE entity_links IS NOT NULL AND entity_links != '[]'::jsonb) AS articles_with_links,
        SUM(CASE WHEN jsonb_typeof(entities->'people') = 'array'
                 THEN jsonb_array_length(entities->'people') ELSE 0 END) AS total_people_mentions,
        SUM(CASE WHEN jsonb_typeof(entities->'organizations') = 'array'
                 THEN jsonb_array_length(entities->'organizations') ELSE 0 END) AS total_org_mentions,
        SUM(CASE WHEN jsonb_typeof(entities->'locations') = 'array'
                 THEN jsonb_array_length(entities->'locations') ELSE 0 END) AS total_location_mentions,
        SUM(jsonb_array_length(COALESCE(entity_links, '[]'::jsonb))) AS total_linked
      FROM articles
    """
    )
    for k, v in dict(row).items():
        print(f"  {k:.<36} {v}")
    raw = (row["total_people_mentions"] or 0) + (row["total_org_mentions"] or 0)
    if raw:
        rate = 100.0 * (row["total_linked"] or 0) / raw
        print(f"  link_rate_pct (people+orgs)......... {rate:.1f}")
        print("  (locations excluded — currently no dossier coverage for places)")


async def section_2_by_category(conn) -> None:
    section("2. Coverage by article category (people + organizations only)")
    print("(low rates in sports/entertainment are expected — those categories\n"
          " don't have dossier coverage by design)\n")
    rows = await conn.fetch(
        """
      WITH per_article AS (
        SELECT
          category,
          (CASE WHEN jsonb_typeof(entities->'people') = 'array'
                THEN jsonb_array_length(entities->'people') ELSE 0 END)
          + (CASE WHEN jsonb_typeof(entities->'organizations') = 'array'
                  THEN jsonb_array_length(entities->'organizations') ELSE 0 END) AS raw,
          jsonb_array_length(COALESCE(entity_links, '[]'::jsonb)) AS linked
        FROM articles
      )
      SELECT
        category,
        SUM(raw) AS raw_mentions,
        SUM(linked) AS linked,
        ROUND(100.0 * SUM(linked)::numeric / NULLIF(SUM(raw), 0), 1) AS link_rate_pct
      FROM per_article
      GROUP BY category
      ORDER BY raw_mentions DESC NULLS LAST
    """
    )
    table(rows, ["category", "raw_mentions", "linked", "link_rate_pct"])


async def section_3_by_linked_type(conn) -> None:
    section("3. Resolved entities by type (what's actually getting linked)")
    sql = f"""
      WITH links AS (
        SELECT jsonb_array_elements(entity_links) AS l
        FROM articles
        WHERE entity_links IS NOT NULL AND entity_links != '[]'::jsonb
      )
      SELECT
        l->>'{LINKED_TYPE_FIELD}' AS entity_type,
        COUNT(*) AS resolved_mentions
      FROM links
      GROUP BY l->>'{LINKED_TYPE_FIELD}'
      ORDER BY resolved_mentions DESC NULLS LAST
    """
    rows = await conn.fetch(sql)
    table(rows, ["entity_type", "resolved_mentions"])


async def section_4_shopping_list(conn) -> None:
    section("4. Shopping list — names mentioned often but never linked to a dossier")
    print("(top of the list = most-mentioned. Filter by guessed_type and category\n"
          " mentally — athletes/actors won't have dossiers by design.)\n")
    sql = """
      WITH
        people_mentions AS (
          SELECT id, category,
                 jsonb_array_elements_text(entities->'people') AS name,
                 'person' AS guessed_type
          FROM articles
          WHERE jsonb_typeof(entities->'people') = 'array'
        ),
        org_mentions AS (
          SELECT id, category,
                 jsonb_array_elements_text(entities->'organizations') AS name,
                 'org' AS guessed_type
          FROM articles
          WHERE jsonb_typeof(entities->'organizations') = 'array'
        ),
        raw AS (
          SELECT id, category, name, guessed_type, LOWER(name) AS surface_lc
          FROM people_mentions
          UNION ALL
          SELECT id, category, name, guessed_type, LOWER(name) AS surface_lc
          FROM org_mentions
        ),
        resolved AS (
          SELECT id, LOWER(jsonb_array_elements(entity_links)->>'surface_form') AS surface_lc
          FROM articles
          WHERE entity_links IS NOT NULL AND entity_links != '[]'::jsonb
        )
      SELECT
        rn.name,
        rn.guessed_type,
        COUNT(*) AS unresolved_mentions,
        STRING_AGG(DISTINCT rn.category, ', ' ORDER BY rn.category) AS categories
      FROM raw rn
      LEFT JOIN resolved r ON r.id = rn.id AND r.surface_lc = rn.surface_lc
      WHERE r.surface_lc IS NULL
      GROUP BY rn.name, rn.guessed_type
      ORDER BY unresolved_mentions DESC
      LIMIT 50
    """
    try:
        rows = await conn.fetch(sql)
    except Exception as exc:
        print(f"  query failed: {exc}")
        return
    table(rows, ["name", "guessed_type", "unresolved_mentions", "categories"])


async def main() -> None:
    pool = await get_pool()
    sections = [
        ("0. samples", section_0_samples),
        ("1. totals", section_1_totals),
        ("2. by category", section_2_by_category),
        ("3. by linked type", section_3_by_linked_type),
        ("4. shopping list", section_4_shopping_list),
    ]
    try:
        async with pool.acquire() as conn:
            for label, fn in sections:
                try:
                    await fn(conn)
                except Exception as exc:
                    print(f"\n[{label}] FAILED: {type(exc).__name__}: {exc}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
