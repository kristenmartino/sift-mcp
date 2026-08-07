"""Tests for the pure, deterministic helpers in sift_mcp.server.

This repo previously had NO tests directory at all, while its CI test step was
guarded by `if: hashFiles('tests/**/*.py') != ''` — so ~920 lines carried a
green badge that could never go red. That guard is now removed; this file is
what makes the job mean something.

Scope is deliberately the pure functions: no DB, no Anthropic, no network.
Everything here runs in milliseconds.
"""

from __future__ import annotations

from datetime import date, datetime


from sift_mcp.server import (
    SPARSE_ARTICLES,
    SPARSE_OUTLETS,
    SPARSE_TOP_SCORE,
    WEB_OUTLET_BUDGET,
    _clean_claim,
    _coerce,
    _extract_json_object,
    _is_sparse,
    _row_to_dict,
    _select_web_outlets,
    gate_org_claims,
)


class TestIsSparse:
    """The highest-value target in this module.

    `_is_sparse` decides whether to spend money on a Claude web-search fallback.
    Its four constants sit under the comment "see commit history for the test
    that produced these" — and that test is not in the repo. These pin the exact
    boundaries so a future tweak is a deliberate act rather than a silent drift
    in what the tool costs to run.
    """

    # A comfortably-good result: strong score, plenty of outlets and articles.
    RICH = dict(top_score=0.90, outlet_count=10, article_count=20)

    def test_rich_result_is_not_sparse(self):
        assert _is_sparse(**self.RICH) is False

    def test_boundary_top_score(self):
        """`<` not `<=`: a score exactly at the threshold is good enough."""
        assert _is_sparse(**{**self.RICH, "top_score": SPARSE_TOP_SCORE}) is False
        assert _is_sparse(**{**self.RICH, "top_score": SPARSE_TOP_SCORE - 0.001}) is True

    def test_boundary_outlet_count(self):
        assert _is_sparse(**{**self.RICH, "outlet_count": SPARSE_OUTLETS}) is False
        assert _is_sparse(**{**self.RICH, "outlet_count": SPARSE_OUTLETS - 1}) is True

    def test_boundary_article_count(self):
        assert _is_sparse(**{**self.RICH, "article_count": SPARSE_ARTICLES}) is False
        assert _is_sparse(**{**self.RICH, "article_count": SPARSE_ARTICLES - 1}) is True

    def test_any_single_failing_dimension_makes_it_sparse(self):
        """The heuristic is an OR — all three must hold to be considered rich."""
        assert _is_sparse(top_score=0.10, outlet_count=10, article_count=20) is True
        assert _is_sparse(top_score=0.90, outlet_count=1, article_count=20) is True
        assert _is_sparse(top_score=0.90, outlet_count=10, article_count=1) is True

    def test_empty_result_is_sparse(self):
        assert _is_sparse(top_score=0.0, outlet_count=0, article_count=0) is True

    def test_constants_are_in_a_sane_range(self):
        """Guards against a typo like 42 for 0.42, which would make every query
        sparse and fan out a paid web search every time."""
        assert 0.0 < SPARSE_TOP_SCORE < 1.0
        assert SPARSE_OUTLETS >= 1
        assert SPARSE_ARTICLES >= 1


class TestSelectWebOutlets:
    """Decides which outlets get a paid web-search fan-out."""

    def test_explicit_user_outlets_win(self):
        out = _select_web_outlets(["Reuters", "  BBC  "], ["npr", "ap"])
        assert out == ["reuters", "bbc"]

    def test_user_outlets_are_normalized(self):
        assert _select_web_outlets(["  FOX News "], []) == ["fox news"]

    def test_excludes_outlets_already_covered_by_the_db(self):
        """The whole point: the web call must add NEW outlets, not re-query
        ones the index already answered."""
        out = _select_web_outlets(None, [])
        assert out, "expected a non-empty default pool"

        # Feed the first pool outlet back as an existing DB result.
        covered = _select_web_outlets(None, [out[0]])
        assert out[0] not in covered

    def test_respects_the_budget(self):
        assert len(_select_web_outlets(None, [])) <= WEB_OUTLET_BUDGET

    def test_substring_matching_handles_spelling_variants(self):
        """DB source_name spellings differ ('New York Times' vs 'the new york
        times'); matching is substring-based on purpose."""
        pool = _select_web_outlets(None, [])
        target = pool[0]
        # A longer DB name containing the pool name must still count as covered.
        assert target not in _select_web_outlets(None, [f"the {target} online"])

    def test_empty_user_list_falls_through_to_the_pool(self):
        # [] is falsy, so it must behave like None rather than returning [].
        assert _select_web_outlets([], []) == _select_web_outlets(None, [])


class TestExtractJsonObject:
    def test_bare_object(self):
        assert _extract_json_object('{"a": 1}') == {"a": 1}

    def test_object_wrapped_in_prose(self):
        assert _extract_json_object('Sure!\n{"a": 1}\nDone') == {"a": 1}

    def test_strips_json_code_fences(self):
        assert _extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}

    def test_strips_bare_code_fences(self):
        assert _extract_json_object('```\n{"a": 1}\n```') == {"a": 1}

    def test_reaches_into_an_array_and_returns_the_first_object(self):
        """Pinned because it is surprising, not because it is desirable.

        The final brace-scanning fallback finds the first '{' and last '}', so a
        response that is a JSON *array* silently yields its inner object rather
        than None. That means a model returning the wrong top-level shape is not
        detected here — it is quietly coerced. Callers that need array-vs-object
        strictness cannot rely on this function to enforce it.
        """
        assert _extract_json_object('[{"a": 1}]') == {"a": 1}

    def test_returns_none_on_unparseable_text(self):
        assert _extract_json_object("not json at all") is None

    def test_returns_none_on_empty(self):
        assert _extract_json_object("") is None

    def test_returns_none_on_a_json_scalar(self):
        assert _extract_json_object("42") is None


class TestCleanClaim:
    def test_rejects_non_dict(self):
        assert _clean_claim("nope", "index") is None

    def test_rejects_dict_without_a_claim_field(self):
        assert _clean_claim({"agreement": "unanimous"}, "index") is None

    def test_normalizes_an_invalid_agreement_to_unique(self):
        out = _clean_claim({"claim": "x", "agreement": "bogus"}, "index")
        assert out["agreement"] == "unique"

    def test_preserves_a_valid_agreement(self):
        out = _clean_claim({"claim": "x", "agreement": "disputed"}, "index")
        assert out["agreement"] == "disputed"

    def test_disputed_gains_outlets_against(self):
        out = _clean_claim(
            {"claim": "x", "agreement": "disputed", "outlets_against": ["npr"]}, "index"
        )
        assert out["outlets_against"] == ["npr"]

    def test_non_disputed_has_no_outlets_against(self):
        out = _clean_claim({"claim": "x", "agreement": "unanimous"}, "index")
        assert "outlets_against" not in out

    def test_source_is_recorded(self):
        assert _clean_claim({"claim": "x"}, "web")["source"] == "web"

    def test_default_outlets_are_used_when_absent(self):
        out = _clean_claim({"claim": "x"}, "index", ["reuters"])
        assert out["outlets"] == ["reuters"]

    def test_values_are_coerced_to_strings(self):
        out = _clean_claim({"claim": 42, "outlets": [1, 2], "article_ids": [3]}, "index")
        assert out["claim"] == "42"
        assert out["outlets"] == ["1", "2"]
        assert out["article_ids"] == ["3"]


class TestCoerce:
    """Silent-corruption surface: DB row values → JSON-safe output."""

    def test_none_passes_through(self):
        assert _coerce(None) is None

    def test_datetime_becomes_isoformat(self):
        assert _coerce(datetime(2026, 6, 4, 12, 0)) == "2026-06-04T12:00:00"

    def test_date_becomes_isoformat(self):
        assert _coerce(date(2026, 6, 4)) == "2026-06-04"

    def test_jsonb_as_string_is_parsed(self):
        assert _coerce('{"a": 1}') == {"a": 1}
        assert _coerce('[1, 2]') == [1, 2]

    def test_malformed_json_string_is_returned_verbatim(self):
        assert _coerce('{"a": ') == '{"a": '

    def test_plain_string_is_untouched(self):
        assert _coerce("hello") == "hello"

    def test_a_string_that_merely_starts_with_a_brace_is_safe(self):
        assert _coerce("{not json}") == "{not json}"

    def test_already_structured_values_pass_through(self):
        assert _coerce({"a": 1}) == {"a": 1}
        assert _coerce([1]) == [1]

    def test_numbers_pass_through(self):
        assert _coerce(5) == 5
        assert _coerce(1.5) == 1.5


class TestRowToDict:
    def test_coerces_every_field(self):
        row = {"published_date": datetime(2026, 6, 4), "entities": '{"a": 1}', "title": "t"}
        out = _row_to_dict(row)
        assert out["published_date"] == "2026-06-04T00:00:00"
        assert out["entities"] == {"a": 1}
        assert out["title"] == "t"

    def test_empty_row(self):
        assert _row_to_dict({}) == {}


class TestGateOrgClaims:
    """This server has no parser between the database and the model's mouth.

    `sift/lib/org.ts` performs this gate for the web UI. An MCP client gets
    whatever the tool returns, citation links stripped, so a claim that
    reaches here unsourced is one a model will restate as fact.
    """

    BUDGET = {
        "annual_budget_usd": 107734507,
        "annual_budget_fy": "FY ending June 2025",
        "annual_budget_source": "https://projects.propublica.org/nonprofits/organizations/1",
    }

    def test_fully_sourced_budget_survives(self):
        assert gate_org_claims(dict(self.BUDGET)) == self.BUDGET

    def test_budget_without_source_is_nulled(self):
        out = gate_org_claims(dict(self.BUDGET, annual_budget_source=None))
        assert out["annual_budget_usd"] is None
        assert out["annual_budget_fy"] is None

    def test_budget_without_fiscal_year_is_nulled(self):
        """013's rule: a bare number is not checkable even with a filing URL."""
        assert gate_org_claims(dict(self.BUDGET, annual_budget_fy=None))["annual_budget_usd"] is None

    def test_non_url_source_does_not_count(self):
        row = dict(self.BUDGET, annual_budget_source="see the 990")
        assert gate_org_claims(row)["annual_budget_usd"] is None

    def test_epa_shape_is_withheld(self):
        """The live case: 23 of 103 prod rows look like this."""
        row = {"annual_budget_usd": 36973000000, "annual_budget_fy": None,
               "annual_budget_source": None}
        assert gate_org_claims(row)["annual_budget_usd"] is None

    def test_self_description_requires_its_source(self):
        row = {"self_description": "We are nonpartisan.", "self_description_source": None,
               "self_description_checked": "2026-07-01"}
        out = gate_org_claims(row)
        assert out["self_description"] is None
        assert out["self_description_checked"] is None

    def test_governance_requires_its_source(self):
        row = {"governance_structure": "Five commissioners.", "governance_source": None}
        assert gate_org_claims(row)["governance_structure"] is None

    def test_groups_are_independent(self):
        """A missing budget source must not strip a properly cited description."""
        out = gate_org_claims(dict(self.BUDGET, annual_budget_source=None,
                                   self_description="Our own words.",
                                   self_description_source="https://example.org/about"))
        assert out["annual_budget_usd"] is None
        assert out["self_description"] == "Our own words."

    def test_absent_claim_is_left_alone(self):
        assert gate_org_claims({"name": "X", "type": "agency"}) == {"name": "X", "type": "agency"}

    def test_identifying_fields_are_never_touched(self):
        """Withholding a claim must not withhold the dossier."""
        out = gate_org_claims({"id": "epa", "name": "EPA", "type": "agency",
                               "annual_budget_usd": 1, "annual_budget_fy": None,
                               "annual_budget_source": None})
        assert out["id"] == "epa" and out["name"] == "EPA" and out["type"] == "agency"

    def test_does_not_mutate_input(self):
        row = dict(self.BUDGET, annual_budget_source=None)
        gate_org_claims(row)
        assert row["annual_budget_usd"] == 107734507
