# sift-mcp — backlog

Items deferred from v0.1. Not blocking the demo; track here so they don't get lost.

## v0.5 (production hardening)

- **Cost caps for `compare_outlets`.** Today every call can issue up to 20 web_searches (~$0.20). No per-token cap, no global daily cap, no per-tool cap.
  - Per-call cap: budget tokens in/out, error out if exceeded.
  - Per-token cap: each issued auth token (when v0.5 ships HTTP/SSE) gets a daily $ cap. `demo` tokens get $1/day, `reviewer` tokens get $20/day.
  - Global cap: org-level daily ceiling so a bad prompt loop can't burn the Anthropic bill.
  - Surface remaining budget in the response (e.g., `cost_remaining_today_usd`).
- **Cache web results.** A `compare_outlets` call with the same `(topic, outlets, web_fallback)` tuple within the last hour should return the cached web payload — index path always re-runs (cheap, fresh).
- **Track per-outlet web_search hit rate.** Log `web_outlets_searched` vs `web_outlets_found` per call so we can see which outlets actually return content. After enough data, drop outlets with consistent <5% hit rate from `WEB_OUTLET_POOL`. Likely drop candidates already suspected: hard-paywall outlets (WSJ, FT, Economist) and AFP (English web presence is thin; AFP content mostly syndicates through partners). Keep all of them reachable via explicit `outlets` param, just not in the smart-selection defaults. Pairs naturally with the cost-cap work above (informs which outlets are budget-worthy).
- **Pool ordering tradeoff: longform outlets get starved.** Current order prioritizes wires first, longform/investigative (Atlantic, National Review, ProPublica) last. For political topics where wires aren't all in DB, the 8-outlet budget often fills before reaching longform. Fix options: (a) interleave longform with wires in pool order, (b) reserve 1-2 budget slots for longform, (c) add a `prefer_longform: bool` arg. Worth doing once we have data on which topic types benefit from longform.
- **HTTP/SSE transport** + Bearer token auth. Railway deploy at `mcp.siftnews.kristenmartino.ai`. Issue read-only `demo` tokens publicly, `reviewer` tokens to specific contacts.

## Stretch / nice-to-have

- **Disputed-claim prioritization.** Sort `claims` so `disputed` items appear first in the array. The cross-spectrum framing is the whole demo; surface it at the top, not buried mid-list.
- **`web_outlet_budget` parameter.** Expose budget as a tool arg for callers who need broader / narrower fan-out without passing the full `outlets` list. Default stays 8.
- **Topic-type-aware outlet pools.** Separate pools for `politics`, `international`, `finance`, `tech`. Auto-select pool from category, or expose `pool: "politics" | "international" | ...` param. Mainstream pool isn't optimal for everything.
- **International expansion.** Current pool is Anglo-heavy (BBC, Guardian, Reuters, FT, Economist — all UK). If the topic mix shifts toward international coverage, add AFP, Al Jazeera, Deutsche Welle, Le Monde, NHK, SCMP.
- **Wire / paywall reality check in response.** Note in `web_status` or a sibling field when outlets in `web_outlets_searched` consistently fail to return (wire services often underperform `site:` queries; paywalled outlets often aren't in Claude's web_search index). Surface the pattern so callers know it's a tool limitation, not a coverage gap.
- **Link web-found claims back to dossiers when possible.** Web claims today have no `article_ids`. If a web claim references a politician / org / bill that exists in Sift's dossier graph, populate a new `dossier_links` field so callers can chain `compare_outlets → get_dossier`.

## Bugs / quirks to revisit

- **Single-article comparisons substitute the topic.** When `articles_compared == 1` and the article isn't precisely on-topic (top score in the 0.40–0.50 band), Haiku tends to extract claims about whatever the article *was* about. Example: FERC Order 1920 query → got claims about FERC Order 1000 because the one matched article was about Order 1000.
  - Fix idea: when `articles_compared == 1`, either (a) suppress claims entirely with a "thin coverage" status, or (b) tighten the prompt to refuse claims that don't match the topic.
- **`load_dotenv(override=True)` is a sharp edge.** Today the `.env` always wins over the shell, which is the right default for a demo but could surprise someone running in CI with explicit env vars. Document the precedence in the README.
